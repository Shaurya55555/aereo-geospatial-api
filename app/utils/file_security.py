"""Defensive handling of uploaded files: names, sizes and zip archives."""
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app import config
from app.exceptions import IngestionError

# Only these members of a shapefile archive are ever written to disk.
SHAPEFILE_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}

_CHUNK = 1024 * 1024


def clean_filename(name: str | None) -> str:
    """Keep only the final path component. Used for display only, never to build paths."""
    base = (name or "").replace("\\", "/").split("/")[-1].strip()
    return base[:255]


def save_upload(upload: UploadFile, dest: Path) -> int:
    """Stream the upload to `dest`, enforcing the size limit. Returns the byte count."""
    size = 0
    with open(dest, "wb") as out:
        while chunk := upload.file.read(_CHUNK):
            size += len(chunk)
            if size > config.MAX_UPLOAD_SIZE:
                raise IngestionError(
                    f"File is larger than the {config.MAX_UPLOAD_SIZE // (1024 * 1024)} MB upload limit.",
                    status_code=400,
                )
            out.write(chunk)
    if size == 0:
        raise IngestionError("Uploaded file is empty.", status_code=400)
    return size


def _is_unsafe(member: str) -> bool:
    name = member.replace("\\", "/")
    path = PurePosixPath(name)
    return (
        path.is_absolute()
        or ".." in path.parts
        or (len(name) > 1 and name[1] == ":")  # Windows drive letter
    )


def safe_extract_shapefile(zip_path: Path, dest: Path) -> list[Path]:
    """Extract the shapefile components of a zip archive into `dest`.

    Protects against zip-slip (path traversal), symlink entries, too many entries and
    zip bombs. Sizes are enforced on the bytes actually read, not on the sizes the
    archive claims, because the archive headers can lie.
    """
    if not zipfile.is_zipfile(zip_path):
        raise IngestionError("File is not a valid zip archive.")

    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            if len(infos) > config.MAX_ARCHIVE_FILES:
                raise IngestionError(
                    f"Archive contains too many entries (limit {config.MAX_ARCHIVE_FILES})."
                )
            if sum(i.file_size for i in infos) > config.MAX_EXTRACTED_SIZE:
                raise IngestionError("Archive expands to more than the allowed size.")

            for info in infos:
                if _is_unsafe(info.filename):
                    raise IngestionError(f"Archive contains an unsafe path: {info.filename!r}.")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise IngestionError("Archive contains a symbolic link, which is not allowed.")

            written: list[Path] = []
            total = 0
            for info in infos:
                if info.is_dir():
                    continue
                relative = PurePosixPath(info.filename.replace("\\", "/"))
                if relative.suffix.lower() not in SHAPEFILE_EXTENSIONS:
                    continue
                target = dest.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    while chunk := src.read(_CHUNK):
                        total += len(chunk)
                        if total > config.MAX_EXTRACTED_SIZE:
                            raise IngestionError("Archive expands to more than the allowed size.")
                        out.write(chunk)
                written.append(target)
            return written
    except zipfile.BadZipFile as exc:
        raise IngestionError("Zip archive is corrupt.") from exc
    except (RuntimeError, NotImplementedError) as exc:  # encrypted / unsupported compression
        raise IngestionError("Zip archive cannot be read (encrypted or unsupported).") from exc
