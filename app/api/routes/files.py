import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.exceptions import IngestionError
from app.models.file import FileRecord
from app.schemas.file import FileOut, MeasurementOut, MeasurementsOut
from app.services.processing import process_upload
from app.utils.file_security import clean_filename, save_upload

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_out(record: FileRecord) -> FileOut:
    return FileOut(
        id=record.id,
        filename=record.filename,
        feature_count=record.feature_count,
        crs=record.source_crs,
        status=record.status,
        successful_count=record.successful_count,
        failed_count=record.failed_count,
        measurement_crs=record.measurement_crs,
        warnings=record.warnings or [],
    )


def _get_or_404(db: Session, file_id: str) -> FileRecord:
    record = db.get(FileRecord, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


@router.post(
    "/",
    response_model=FileOut,
    status_code=201,
    summary="Upload and process a geospatial file",
    description=(
        "Accepts a `.kml` file or a `.zip` containing one Shapefile (`.shp`, `.shx`, `.dbf`, `.prj`). "
        "The file is processed synchronously. Features that cannot be measured are reported "
        "individually and do not fail the upload."
    ),
    responses={
        400: {"description": "Wrong extension, empty file or file too large"},
        422: {"description": "File content is invalid (corrupt zip, missing .prj, unreadable KML, ...)"},
    },
)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)) -> FileOut:
    filename = clean_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .kml and .zip (Shapefile) files are accepted.")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / f"upload{extension}"
            save_upload(file, saved)
            record = process_upload(db, filename, extension, saved)
    except IngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _file_out(record)


@router.get("/{file_id}/", response_model=FileOut, summary="Get information about an uploaded file")
def get_file(file_id: str, db: Session = Depends(get_db)) -> FileOut:
    return _file_out(_get_or_404(db, file_id))


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementsOut,
    summary="Get per-feature measurements",
    description="Areas are in square metres and lengths in metres, calculated in `measurement_crs`.",
)
def get_measurements(
    file_id: str,
    include_geometry: bool = Query(False, description="Include each feature's GeoJSON geometry."),
    db: Session = Depends(get_db),
) -> MeasurementsOut:
    record = _get_or_404(db, file_id)
    items = [
        MeasurementOut(
            feature_id=f.feature_index,
            geometry_type=f.geometry_type,
            crs=f.crs,
            area_m2=f.area_m2,
            length_m=f.length_m,
            status=f.status,
            error=f.error,
            properties=f.properties or {},
            geometry=f.geometry if include_geometry else None,
        )
        for f in record.features
    ]
    return MeasurementsOut(
        file_id=record.id,
        source_crs=record.source_crs,
        measurement_crs=record.measurement_crs,
        warnings=record.warnings or [],
        measurements=items,
    )
