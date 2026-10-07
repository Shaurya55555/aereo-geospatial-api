from app import config

from .helpers import kml_document, kml_point, kml_polygon, make_zip, to_wgs84, utm_box, write_shapefile_zip


def square_kml() -> bytes:
    gdf = to_wgs84([utm_box(0, 0, 1000, 1000)])
    return kml_document([kml_polygon("Plot", list(gdf.geometry.iloc[0].exterior.coords))])


def square_zip() -> bytes:
    return write_shapefile_zip(to_wgs84([utm_box(0, 0, 1000, 1000)], Name=["Plot"]))


def test_upload_kml(upload):
    response = upload("survey.kml", square_kml())
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "survey.kml"
    assert body["feature_count"] == 1
    assert body["crs"] == "EPSG:4326"
    assert body["measurement_crs"] == "EPSG:32643"
    assert body["status"] == "COMPLETED"
    assert body["successful_count"] == 1
    assert body["failed_count"] == 0


def test_upload_shapefile_zip(upload):
    response = upload("parcels.zip", square_zip())
    assert response.status_code == 201
    assert response.json()["feature_count"] == 1
    assert response.json()["crs"] == "EPSG:4326"


def test_get_file_returns_what_was_stored(client, upload):
    created = upload("survey.kml", square_kml()).json()
    fetched = client.get(f"/api/files/{created['id']}/")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_unknown_id_returns_404(client):
    assert client.get("/api/files/does-not-exist/").status_code == 404
    assert client.get("/api/files/does-not-exist/measurements/").status_code == 404


def test_wrong_extension_returns_400(upload):
    response = upload("notes.txt", b"hello")
    assert response.status_code == 400


def test_empty_file_returns_400(upload):
    assert upload("empty.kml", b"").status_code == 400


def test_missing_file_field_is_rejected(client):
    assert client.post("/api/files/").status_code == 422


def test_garbage_kml_returns_422(upload):
    assert upload("bad.kml", b"this is not xml at all").status_code == 422


def test_kml_without_features_returns_422(upload):
    assert upload("none.kml", kml_document([])).status_code == 422


def test_fake_zip_returns_422(upload):
    assert upload("fake.zip", b"definitely not a zip").status_code == 422


def test_oversized_upload_returns_400(upload, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE", 100)
    response = upload("big.kml", square_kml())
    assert response.status_code == 400
    assert "larger" in response.json()["detail"]


def test_directory_is_stripped_from_filename(upload):
    response = upload("../../etc/passwd/survey.kml", square_kml())
    assert response.status_code == 201
    assert response.json()["filename"] == "survey.kml"


def test_uppercase_extension_is_accepted(upload):
    assert upload("SURVEY.KML", square_kml()).status_code == 201


def test_point_only_file_is_completed(upload):
    response = upload("pts.kml", kml_document([kml_point("a", 75.8, 26.9)]))
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["failed_count"] == 0


def test_zip_without_shapefile_returns_422(upload):
    assert upload("empty.zip", make_zip({"readme.txt": "hi"})).status_code == 422
