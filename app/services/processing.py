"""Orchestrates one upload: ingest, plan the CRS, measure every feature, persist."""
import datetime
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app import config
from app.exceptions import IngestionError
from app.models.file import FeatureRecord, FileRecord
from app.services import measurement as m
from app.services.crs import crs_label, plan_measurement_crs
from app.services.ingestion import ingest

COMPLETED = "COMPLETED"
COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"


def process_upload(db: Session, filename: str, extension: str, path: Path) -> FileRecord:
    with TemporaryDirectory() as workdir:
        data = ingest(path, extension, Path(workdir))

    gdf, source_crs = data.gdf, data.crs
    source_label = crs_label(source_crs)

    try:
        gdf_wgs84 = gdf.to_crs(4326)
    except Exception as exc:
        raise IngestionError("Coordinates could not be transformed; check the file's CRS.") from exc

    plan = plan_measurement_crs(gdf_wgs84, source_crs)
    gdf_projected = None
    if plan.crs is not None:
        try:
            gdf_projected = gdf.to_crs(plan.crs)
        except Exception as exc:
            raise IngestionError("Coordinates could not be projected for measurement.") from exc

    property_columns = [c for c in gdf.columns if c != gdf.geometry.name]
    records: list[FeatureRecord] = []

    for index, (geom, props) in enumerate(zip(gdf.geometry, gdf[property_columns].to_dict("records"))):
        result = m.classify(geom)
        if result is None:
            result = _measure_feature(index, geom, gdf_wgs84, gdf_projected, plan)
        records.append(
            FeatureRecord(
                feature_index=index,
                geometry_type=None if geom is None else geom.geom_type,
                geometry=None if geom is None or geom.is_empty else mapping(geom),
                crs=source_label,
                properties={str(k): _json_safe(v) for k, v in props.items()},
                status=result.status,
                area_m2=result.area_m2,
                length_m=result.length_m,
                error=result.error,
            )
        )

    unmeasured = {m.FAILED, m.UNSUPPORTED}
    failed = sum(1 for r in records if r.status in unmeasured)
    file_record = FileRecord(
        filename=filename,
        file_type=data.file_type,
        source_crs=source_label,
        measurement_crs=crs_label(plan.crs) if plan.crs is not None else None,
        feature_count=len(records),
        successful_count=len(records) - failed,
        failed_count=failed,
        status=COMPLETED_WITH_ERRORS if failed else COMPLETED,
        warnings=plan.warnings,
        features=records,
    )
    db.add(file_record)
    db.commit()
    return file_record


def _measure_feature(
    index: int,
    geom,
    gdf_wgs84: gpd.GeoDataFrame,
    gdf_projected: gpd.GeoDataFrame | None,
    plan,
) -> m.Measurement:
    if gdf_projected is None:
        return m.Measurement(m.FAILED, error=plan.error)
    if plan.check_latitude:
        _, miny, _, maxy = gdf_wgs84.geometry.iloc[index].bounds
        if not (config.UTM_MIN_LAT <= miny and maxy <= config.UTM_MAX_LAT):
            return m.Measurement(m.FAILED, error="Feature lies outside the latitude range covered by UTM.")
    return m.measure(geom, gdf_projected.geometry.iloc[index])


def _json_safe(value):
    """Convert pandas/numpy values from attribute tables into plain JSON types."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
