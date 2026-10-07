from typing import Any

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "8c3f1d0e5a7b4c2d9e6f0a1b2c3d4e5f",
                "filename": "survey.kml",
                "feature_count": 4,
                "crs": "EPSG:4326",
                "status": "COMPLETED_WITH_ERRORS",
                "successful_count": 3,
                "failed_count": 1,
                "measurement_crs": "EPSG:32643",
                "warnings": [],
            }
        },
    )

    id: str
    filename: str
    feature_count: int
    crs: str
    status: str
    successful_count: int
    failed_count: int
    measurement_crs: str | None
    warnings: list[str]


class MeasurementOut(BaseModel):
    feature_id: int
    geometry_type: str | None
    crs: str
    area_m2: float | None
    length_m: float | None
    status: str
    error: str | None
    properties: dict[str, Any]
    geometry: dict[str, Any] | None = None


class MeasurementsOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "8c3f1d0e5a7b4c2d9e6f0a1b2c3d4e5f",
                "source_crs": "EPSG:4326",
                "measurement_crs": "EPSG:32643",
                "warnings": [],
                "measurements": [
                    {
                        "feature_id": 0,
                        "geometry_type": "Polygon",
                        "crs": "EPSG:4326",
                        "area_m2": 15234.7213,
                        "length_m": None,
                        "status": "SUCCESS",
                        "error": None,
                        "properties": {"Name": "Plot A"},
                    },
                    {
                        "feature_id": 1,
                        "geometry_type": "LineString",
                        "crs": "EPSG:4326",
                        "area_m2": None,
                        "length_m": 824.3104,
                        "status": "SUCCESS",
                        "error": None,
                        "properties": {"Name": "Road"},
                    },
                    {
                        "feature_id": 2,
                        "geometry_type": "Point",
                        "crs": "EPSG:4326",
                        "area_m2": None,
                        "length_m": None,
                        "status": "NO_MEASUREMENT_REQUIRED",
                        "error": None,
                        "properties": {"Name": "Gate"},
                    },
                ],
            }
        }
    )

    file_id: str
    source_crs: str
    measurement_crs: str | None
    warnings: list[str]
    measurements: list[MeasurementOut]
