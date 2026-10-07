"""Per-feature measurement, given geometries that are already in a projected CRS."""
import math
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

SUCCESS = "SUCCESS"
NO_MEASUREMENT = "NO_MEASUREMENT_REQUIRED"
UNSUPPORTED = "UNSUPPORTED"
FAILED = "FAILED"

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


@dataclass
class Measurement:
    status: str
    area_m2: float | None = None
    length_m: float | None = None
    error: str | None = None


def classify(geom: BaseGeometry | None) -> Measurement | None:
    """Return a terminal result if the geometry cannot or need not be measured, else None."""
    if geom is None or geom.is_empty:
        return Measurement(FAILED, error="Feature has no geometry.")
    gtype = geom.geom_type
    if gtype in POINT_TYPES:
        return Measurement(NO_MEASUREMENT)
    if gtype not in AREA_TYPES | LENGTH_TYPES:
        return Measurement(UNSUPPORTED, error=f"Measurement is not supported for {gtype}.")
    return None


def measure(source_geom: BaseGeometry, projected_geom: BaseGeometry) -> Measurement:
    """Validity is checked on the geometry as authored; the projected copy is what gets measured."""
    if not source_geom.is_valid:
        return Measurement(FAILED, error=f"Invalid geometry: {explain_validity(source_geom)}.")

    if source_geom.geom_type in AREA_TYPES:
        value = projected_geom.area  # holes are subtracted by Shapely
        key = "area_m2"
    else:
        value = projected_geom.length
        key = "length_m"

    if not math.isfinite(value):
        return Measurement(FAILED, error="Projection produced invalid coordinates.")
    return Measurement(SUCCESS, **{key: round(value, 4)})
