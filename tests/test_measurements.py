import pytest
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon

from .helpers import (
    X0,
    Y0,
    kml_document,
    kml_line,
    kml_point,
    kml_polygon,
    to_wgs84,
    utm_box,
    write_shapefile_zip,
)


def lonlat(coords):
    """Convert UTM 43N metre offsets-from-origin coords to lon/lat tuples."""
    gdf = to_wgs84([LineString([(X0 + x, Y0 + y) for x, y in coords])])
    return list(gdf.geometry.iloc[0].coords)


def by_name(result, key="Name"):
    return {m["properties"][key]: m for m in result["measurements"]}


def test_known_area_and_length_in_one_kml(measurements):
    square = lonlat([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)])
    road = lonlat([(0, -500), (3000, -500), (3000, -1500)])
    content = kml_document([kml_polygon("plot", square), kml_line("road", road)])
    _, result = measurements("s.kml", content)
    found = by_name(result, "Name")
    assert found["plot"]["area_m2"] == pytest.approx(1_000_000, rel=1e-5)
    assert found["plot"]["length_m"] is None
    assert found["road"]["length_m"] == pytest.approx(4_000, rel=1e-5)
    assert found["road"]["area_m2"] is None


def test_polygon_hole_is_subtracted(measurements):
    outer = lonlat([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)])
    hole = lonlat([(250, 250), (750, 250), (750, 750), (250, 750), (250, 250)])
    _, result = measurements("h.kml", kml_document([kml_polygon("holey", outer, holes=[hole])]))
    assert result["measurements"][0]["area_m2"] == pytest.approx(750_000, rel=1e-5)


def test_multipolygon_total_area(measurements):
    gdf = to_wgs84([MultiPolygon([utm_box(0, 0, 100, 100), utm_box(500, 0, 100, 100)])], Name=["m"])
    _, result = measurements("m.zip", write_shapefile_zip(gdf))
    feature = result["measurements"][0]
    assert feature["geometry_type"] == "MultiPolygon"
    assert feature["status"] == "SUCCESS"
    assert feature["area_m2"] == pytest.approx(20_000, rel=1e-5)


def test_multilinestring_total_length(measurements):
    lines = MultiLineString(
        [[(X0, Y0), (X0 + 100, Y0)], [(X0, Y0 + 500), (X0, Y0 + 800)]]
    )
    gdf = to_wgs84([lines], Name=["ml"])
    _, result = measurements("ml.zip", write_shapefile_zip(gdf))
    feature = result["measurements"][0]
    assert feature["geometry_type"] == "MultiLineString"
    assert feature["length_m"] == pytest.approx(400, rel=1e-5)


def test_point_needs_no_measurement(measurements):
    _, result = measurements("p.kml", kml_document([kml_point("gate", 75.8, 26.9)]))
    feature = result["measurements"][0]
    assert feature["geometry_type"] == "Point"
    assert feature["status"] == "NO_MEASUREMENT_REQUIRED"
    assert feature["area_m2"] is None and feature["length_m"] is None
    assert feature["error"] is None


def test_multipoint_needs_no_measurement(measurements):
    gdf = to_wgs84([MultiPoint([(X0, Y0), (X0 + 10, Y0)])], Name=["mp"])
    _, result = measurements("mp.zip", write_shapefile_zip(gdf))
    assert result["measurements"][0]["status"] == "NO_MEASUREMENT_REQUIRED"


def test_geometry_collection_is_unsupported_not_a_crash(measurements, client):
    collection = (
        "<Placemark><name>mixed</name><MultiGeometry>"
        "<Point><coordinates>75.8,26.9</coordinates></Point>"
        "<LineString><coordinates>75.8,26.9 75.81,26.91</coordinates></LineString>"
        "</MultiGeometry></Placemark>"
    )
    info, result = measurements("gc.kml", kml_document([collection, kml_point("ok", 75.8, 26.9)]))
    found = by_name(result)
    assert found["mixed"]["geometry_type"] == "GeometryCollection"
    assert found["mixed"]["status"] == "UNSUPPORTED"
    assert "not supported" in found["mixed"]["error"]
    assert found["ok"]["status"] == "NO_MEASUREMENT_REQUIRED"
    assert info["status"] == "COMPLETED_WITH_ERRORS"
    assert info["failed_count"] == 1
    assert info["successful_count"] == 1


def test_invalid_polygon_fails_but_other_features_continue(measurements):
    good = lonlat([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    bowtie = lonlat([(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)])
    content = kml_document([kml_polygon("bad", bowtie), kml_polygon("good", good)])
    info, result = measurements("b.kml", content)
    found = by_name(result)
    assert found["bad"]["status"] == "FAILED"
    assert "Self-intersection" in found["bad"]["error"]
    assert found["bad"]["area_m2"] is None
    assert found["good"]["status"] == "SUCCESS"
    assert found["good"]["area_m2"] == pytest.approx(10_000, rel=1e-5)
    assert info["status"] == "COMPLETED_WITH_ERRORS"
    assert (info["successful_count"], info["failed_count"]) == (1, 1)


def test_clean_file_has_completed_status(measurements):
    good = lonlat([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    info, _ = measurements("g.kml", kml_document([kml_polygon("good", good)]))
    assert info["status"] == "COMPLETED"
    assert (info["successful_count"], info["failed_count"]) == (1, 0)
    assert info["feature_count"] == 1


def test_properties_are_returned(measurements):
    gdf = to_wgs84([utm_box(0, 0, 100, 100)], Name=["Parcel A"], owner=["Asha"], acres=[2.5], count=[7])
    _, result = measurements("p.zip", write_shapefile_zip(gdf))
    props = result["measurements"][0]["properties"]
    assert props["Name"] == "Parcel A"
    assert props["owner"] == "Asha"
    assert props["acres"] == 2.5
    assert props["count"] == 7


def test_feature_ids_are_sequential_indexes(measurements):
    gdf = to_wgs84([utm_box(i * 200, 0, 100, 100) for i in range(3)], Name=["a", "b", "c"])
    _, result = measurements("p.zip", write_shapefile_zip(gdf))
    assert [m["feature_id"] for m in result["measurements"]] == [0, 1, 2]


def test_geometry_hidden_by_default_and_shown_on_request(measurements):
    gdf = to_wgs84([utm_box(0, 0, 100, 100)], Name=["a"])
    content = write_shapefile_zip(gdf)

    _, hidden = measurements("p.zip", content)
    assert hidden["measurements"][0]["geometry"] is None

    _, shown = measurements("p.zip", content, include_geometry="true")
    geometry = shown["measurements"][0]["geometry"]
    assert geometry["type"] == "Polygon"
    assert len(geometry["coordinates"][0]) == 5


def test_measurement_response_shape(measurements):
    gdf = to_wgs84([utm_box(0, 0, 100, 100)], Name=["a"])
    info, result = measurements("p.zip", write_shapefile_zip(gdf))
    assert result["file_id"] == info["id"]
    assert set(result) == {"file_id", "source_crs", "measurement_crs", "warnings", "measurements"}
    assert {
        "feature_id", "geometry_type", "crs", "area_m2", "length_m", "status", "error", "properties", "geometry"
    } == set(result["measurements"][0])


def test_multi_folder_kml_reads_every_folder(measurements):
    square = lonlat([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    content = (
        '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<Folder><name>A</name>{kml_polygon('one', square)}</Folder>"
        f"<Folder><name>B</name>{kml_point('two', 75.8, 26.9)}</Folder>"
        "</Document></kml>"
    ).encode()
    info, _ = measurements("f.kml", content)
    assert info["feature_count"] == 2
