"""CRS handling: choose the single projected CRS used to measure a dataset.

Area and length are never computed on latitude/longitude degrees. Every dataset is
measured in one UTM zone chosen from the centre of its extent. Projected inputs are
re-projected too, because a projected CRS is not automatically accurate (Web Mercator
inflates areas heavily away from the equator). Inputs already in a UTM zone are kept.
"""
import math
from dataclasses import dataclass, field

import geopandas as gpd
from pyproj import CRS

from app import config


@dataclass
class MeasurementPlan:
    crs: CRS | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    check_latitude: bool = False  # True when a UTM CRS was derived, so each feature must fit it


def crs_label(crs: CRS) -> str:
    authority = crs.to_authority()
    if authority:
        return f"{authority[0]}:{authority[1]}"
    return crs.name


def utm_zone(lon: float) -> int:
    return min(60, max(1, int((lon + 180) // 6) + 1))


def utm_crs(lon: float, lat: float) -> CRS:
    base = 32600 if lat >= 0 else 32700
    return CRS.from_epsg(base + utm_zone(lon))


def is_utm(crs: CRS) -> bool:
    epsg = crs.to_epsg()
    return epsg is not None and (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760)


def plan_measurement_crs(gdf_wgs84: gpd.GeoDataFrame, source_crs: CRS) -> MeasurementPlan:
    """`gdf_wgs84` is the dataset in EPSG:4326, used only to find where it is on Earth."""
    geoms = gdf_wgs84.geometry
    geoms = geoms[geoms.notna() & ~geoms.is_empty]
    if geoms.empty:
        return MeasurementPlan(crs=None, error="Dataset has no usable geometry.")

    minx, miny, maxx, maxy = geoms.total_bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        return MeasurementPlan(crs=None, error="Dataset coordinates could not be transformed to WGS 84.")

    warnings: list[str] = []
    if utm_zone(minx) != utm_zone(maxx):
        warnings.append(
            f"Dataset spans UTM zones {utm_zone(minx)} to {utm_zone(maxx)}. All features are "
            "measured in a single zone, so accuracy decreases for features far from its central meridian."
        )

    if is_utm(source_crs):
        return MeasurementPlan(crs=source_crs, warnings=warnings)

    lon, lat = (minx + maxx) / 2, (miny + maxy) / 2
    if not config.UTM_MIN_LAT <= lat <= config.UTM_MAX_LAT:
        return MeasurementPlan(
            crs=None,
            warnings=warnings,
            error=(
                f"Dataset is centred at latitude {lat:.2f}, outside the range covered by UTM "
                f"({config.UTM_MIN_LAT:g} to {config.UTM_MAX_LAT:g}). Measurements were not calculated."
            ),
        )
    return MeasurementPlan(crs=utm_crs(lon, lat), warnings=warnings, check_latitude=True)
