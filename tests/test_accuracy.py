"""Compare API results with pyproj.Geod, an independent ellipsoidal reference.

Geod is used here only. The service itself measures in a projected (UTM) CRS.
UTM scale error is under about 0.1% near a zone's central meridian, so 2e-3 is a safe bound.
"""
import geopandas as gpd
import pytest
from shapely.geometry import LineString

from .helpers import (
    geodesic_area,
    geodesic_length,
    geodesic_square,
    kml_document,
    kml_line,
    kml_polygon,
    write_shapefile_zip,
)

LATITUDES = [0.5, 26.9, 60.0, -33.9]
TOLERANCE = 2e-3


@pytest.mark.parametrize("lat", LATITUDES)
def test_area_matches_geodesic_reference(measurements, lat):
    square = geodesic_square(75.8, lat, 2000)
    reference = geodesic_area(square)
    assert reference == pytest.approx(4_000_000, rel=1e-3)  # sanity check on the builder

    content = kml_document([kml_polygon("sq", list(square.exterior.coords))])
    _, result = measurements("sq.kml", content)
    assert result["measurements"][0]["area_m2"] == pytest.approx(reference, rel=TOLERANCE)


@pytest.mark.parametrize("lat", LATITUDES)
def test_length_matches_geodesic_reference(measurements, lat):
    line = LineString([(75.8, lat), (75.85, lat + 0.03), (75.9, lat)])
    reference = geodesic_length(line)

    content = kml_document([kml_line("l", list(line.coords))])
    _, result = measurements("l.kml", content)
    assert result["measurements"][0]["length_m"] == pytest.approx(reference, rel=TOLERANCE)


@pytest.mark.parametrize("lat", LATITUDES)
def test_shapefile_area_matches_geodesic_reference(measurements, lat):
    square = geodesic_square(75.8, lat, 1500)
    gdf = gpd.GeoDataFrame({"Name": ["sq"]}, geometry=[square], crs=4326)
    _, result = measurements("sq.zip", write_shapefile_zip(gdf))
    assert result["measurements"][0]["area_m2"] == pytest.approx(geodesic_area(square), rel=TOLERANCE)


def test_degree_arithmetic_would_have_been_wrong():
    """Why this service exists: 'area' in degrees is not square metres."""
    square = geodesic_square(75.8, 26.9, 1000)
    assert square.area < 0.001  # a few 1e-5 'square degrees', nonsense as metres
