import io
import zipfile

from app import config

from .helpers import make_zip, to_wgs84, utm_box, write_shapefile_zip


def good_zip(**kwargs) -> bytes:
    return write_shapefile_zip(to_wgs84([utm_box(0, 0, 100, 100)], Name=["a"]), **kwargs)


def test_zip_slip_entry_is_rejected(upload):
    content = good_zip(extra={"../evil.shp": b"x"})
    response = upload("slip.zip", content)
    assert response.status_code == 422
    assert "unsafe" in response.json()["detail"]


def test_absolute_path_entry_is_rejected(upload):
    response = upload("abs.zip", good_zip(extra={"/etc/evil.shp": b"x"}))
    assert response.status_code == 422


def test_windows_drive_path_is_rejected(upload):
    response = upload("drive.zip", good_zip(extra={"C:/evil.shp": b"x"}))
    assert response.status_code == 422


def test_too_many_entries_is_rejected(upload, monkeypatch):
    monkeypatch.setattr(config, "MAX_ARCHIVE_FILES", 3)
    response = upload("many.zip", make_zip({f"f{i}.txt": "x" for i in range(10)}))
    assert response.status_code == 422
    assert "too many" in response.json()["detail"]


def test_zip_bomb_is_rejected(upload, monkeypatch):
    monkeypatch.setattr(config, "MAX_EXTRACTED_SIZE", 10_000)
    bomb = make_zip({"data.shp": b"\0" * 1_000_000})  # compresses to a few hundred bytes
    response = upload("bomb.zip", bomb)
    assert response.status_code == 422
    assert "allowed size" in response.json()["detail"]


def test_symlink_entry_is_rejected(upload):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link.shp")
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "/etc/passwd")
    response = upload("link.zip", buf.getvalue())
    assert response.status_code == 422
    assert "symbolic link" in response.json()["detail"]


def test_missing_shx_returns_422(upload):
    response = upload("p.zip", good_zip(drop_suffixes=(".shx",)))
    assert response.status_code == 422
    assert ".shx" in response.json()["detail"]


def test_missing_dbf_returns_422(upload):
    response = upload("p.zip", good_zip(drop_suffixes=(".dbf",)))
    assert response.status_code == 422
    assert ".dbf" in response.json()["detail"]


def test_two_shapefiles_return_422(upload):
    first = good_zip()
    with zipfile.ZipFile(io.BytesIO(first)) as zf:
        members = {f"a/{n}": zf.read(n) for n in zf.namelist()}
        members.update({f"b/{n}": zf.read(n) for n in zf.namelist()})
    response = upload("two.zip", make_zip(members))
    assert response.status_code == 422
    assert "exactly one" in response.json()["detail"]


def test_zip_with_no_shp_returns_422(upload):
    response = upload("none.zip", make_zip({"a.dbf": b"x", "a.shx": b"x"}))
    assert response.status_code == 422
    assert ".shp" in response.json()["detail"]


def test_unrelated_files_in_zip_are_ignored(upload):
    response = upload("extra.zip", good_zip(extra={"notes.txt": "hello", "run.exe": b"MZ"}))
    assert response.status_code == 201
    assert response.json()["feature_count"] == 1


def test_shapefile_in_subfolder_is_found(upload):
    with zipfile.ZipFile(io.BytesIO(good_zip())) as zf:
        members = {f"folder/{n}": zf.read(n) for n in zf.namelist()}
    assert upload("nested.zip", make_zip(members)).status_code == 201
