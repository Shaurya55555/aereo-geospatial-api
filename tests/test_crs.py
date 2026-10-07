import pytest
from pyproj import CRS
from shapely.geometry import Point, box

from app.services.crs import is_utm, utm_crs, utm_zone

from .helpers import X0, Y0, geodesic_square, to_wgs84, utm_box, write_shapefile_zip
import geopandas as gpd


@pytest.mark.parametrize(
    "lon, zone",
    [(-180, 1), (-177.1, 1), (-174, 2), (0, 31), (75.8, 43), (77.6, 43), (179.9, 60), (180, 60)],
)
def test_utm_zone(lon, zone):
    assert utm_zone(lon) == zone


def test_utm_crs_hemispheres():
    assert utm_crs(75.8, 26.9).to_epsg() == 32643
    assert utm_crs(18.4, -33.9).to_epsg() == 32734


def test_is_utm():
    assert is_utm(CRS.from_epsg(32643))
    assert is_utm(CRS.from_epsg(32734))
    assert not is_utm(CRS.from_epsg(4326))
    assert not is_utm(CRS.from_epsg(3857))


def test_wgs84_zip_is_measured_in_utm(measurements):
    gdf = to_wgs84([utm_box(0, 0, 1000, 1000)], Name=["a"])
    info, result = measurements("p.zip", write_shapefile_zip(gdf))
    assert info["crs"] == "EPSG:4326"
    assert result["measurement_crs"] == "EPSG:32643"
    assert result["measurements"][0]["area_m2"] == pytest.approx(1_000_000, rel=1e-6)


def test_utm_source_crs_is_kept(measurements):
    gdf = gpd.GeoDataFrame({"Name": ["a"]}, geometry=[utm_box(0, 0, 1000, 1000)], crs="EPSG:32643")
    info, result = measurements("p.zip", write_shapefile_zip(gdf))
    assert info["crs"] == "EPSG:32643"
    assert result["source_crs"] == "EPSG:32643"
    assert result["measurement_crs"] == "EPSG:32643"
    assert result["measurements"][0]["area_m2"] == pytest.approx(1_000_000, rel=1e-9)


def test_web_mercator_is_reprojected_before_measuring(measurements):
    """Web Mercator inflates areas by 1/cos^2(lat); at 27 N that is about 25%."""
    gdf = to_wgs84([utm_box(0, 0, 1000, 1000)], Name=["a"]).to_crs(3857)
    naive_area = gdf.geometry.iloc[0].area
    assert naive_area > 1_200_000  # the trap: measuring in 3857 directly is wrong

    info, result = measurements("merc.zip", write_shapefile_zip(gdf))
    assert info["crs"] == "EPSG:3857"
    assert result["measurement_crs"] == "EPSG:32643"
    assert result["measurements"][0]["area_m2"] == pytest.approx(1_000_000, rel=1e-4)


def test_missing_prj_returns_422_and_does_not_guess(upload):
    gdf = to_wgs84([utm_box(0, 0, 100, 100)], Name=["a"])
    response = upload("noprj.zip", write_shapefile_zip(gdf, drop_suffixes=(".prj",)))
    assert response.status_code == 422
    assert ".prj" in response.json()["detail"]


def test_southern_hemisphere_uses_327xx(measurements):
    # Cape Town, 33.9 S, 18.4 E -> UTM 34S (EPSG:32734)
    square = geodesic_square(18.4, -33.9, 1000)
    gdf = gpd.GeoDataFrame({"Name": ["a"]}, geometry=[square], crs=4326)
    _, result = measurements("south.zip", write_shapefile_zip(gdf))
    assert result["measurement_crs"] == "EPSG:32734"


def test_multi_zone_dataset_warns_but_measures(measurements):
    # Two points of interest 12+ degrees of longitude apart, joined by plots at each end.
    west = geodesic_square(70.0, 20.0, 500)
    east = geodesic_square(82.0, 20.0, 500)
    gdf = gpd.GeoDataFrame({"Name": ["w", "e"]}, geometry=[west, east], crs=4326)
    info, result = measurements("wide.zip", write_shapefile_zip(gdf))
    assert result["warnings"]
    assert "UTM zones" in result["warnings"][0]
    assert info["warnings"] == result["warnings"]
    assert all(m["status"] == "SUCCESS" for m in result["measurements"])


def test_single_zone_dataset_has_no_warnings(measurements):
    gdf = to_wgs84([utm_box(0, 0, 100, 100)], Name=["a"])
    _, result = measurements("p.zip", write_shapefile_zip(gdf))
    assert result["warnings"] == []


def test_polar_dataset_fails_safely_with_no_numbers(measurements):
    gdf = gpd.GeoDataFrame({"Name": ["a"]}, geometry=[box(10, 85.0, 10.1, 85.1)], crs=4326)
    info, result = measurements("polar.zip", write_shapefile_zip(gdf))
    feature = result["measurements"][0]
    assert feature["status"] == "FAILED"
    assert "UTM" in feature["error"]
    assert feature["area_m2"] is None
    assert result["measurement_crs"] is None
    assert info["status"] == "COMPLETED_WITH_ERRORS"


def test_feature_crs_is_the_source_crs(measurements):
    gdf = to_wgs84([utm_box(0, 0, 100, 100)], Name=["a"])
    _, result = measurements("p.zip", write_shapefile_zip(gdf))
    assert result["measurements"][0]["crs"] == "EPSG:4326"
