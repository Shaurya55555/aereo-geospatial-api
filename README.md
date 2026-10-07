# Geospatial File Measurement API

A FastAPI service that accepts a **KML** file or a **zipped Shapefile**, extracts every feature, and returns
**area (m2)** for polygons and **length (m)** for lines. Measurements are never calculated on latitude/longitude
degrees: every dataset is first transformed to a projected CRS (UTM) and measured there.

## Setup

Requires Python 3.11+ (developed on 3.14).

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows. On Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload     # then open http://localhost:8000/docs
pytest                            # run the tests
```

With Docker:

```bash
docker compose up --build         # then open http://localhost:8000/docs
```

Ready-made inputs are in [`sample_data/`](sample_data/README.md), each with its expected result.
Optional settings (database URL, upload limits) are in `.env.example`; the defaults work as they are.

## API

Interactive documentation: `/docs`.

### `POST /api/files/`: upload and process

Multipart form with a `file` field: a `.kml`, or a `.zip` containing exactly one Shapefile
(`.shp`, `.shx`, `.dbf`, `.prj`). Processing is synchronous, so the response already describes the finished result.

```bash
curl -F "file=@sample_data/survey.kml" http://localhost:8000/api/files/
```

```json
{
  "id": "6fcc6241d7bd4dd8906695cd8901eaa3",
  "filename": "survey.kml",
  "feature_count": 6,
  "crs": "EPSG:4326",
  "status": "COMPLETED_WITH_ERRORS",
  "successful_count": 5,
  "failed_count": 1,
  "measurement_crs": "EPSG:32643",
  "warnings": []
}
```

| Code | Meaning |
| --- | --- |
| 201 | Processed. |
| 400 | Wrong extension, empty file, or file over the size limit. |
| 422 | Content is invalid: corrupt zip, missing `.shp/.shx/.dbf/.prj`, unreadable KML, no features, unsafe zip entries. |

### `GET /api/files/{id}/`: file information

Returns the same body as the upload response. `404` if the id is unknown.

### `GET /api/files/{id}/measurements/`: per-feature results

Each feature includes its GeoJSON `geometry` by default. Add `?include_geometry=false` for a smaller response without it.

```json
{
  "file_id": "6fcc6241d7bd4dd8906695cd8901eaa3",
  "source_crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "warnings": [],
  "measurements": [
    {
      "feature_id": 1,
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "area_m2": 750000.0,
      "length_m": null,
      "status": "SUCCESS",
      "error": null,
      "properties": { "Name": "Plot with hole", "_layer": "survey" },
      "geometry": { "type": "Polygon", "coordinates": ["..."] }
    },
    {
      "feature_id": 5,
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "area_m2": null,
      "length_m": null,
      "status": "FAILED",
      "error": "Invalid geometry: Self-intersection[77.518215696181 26.92890044529].",
      "properties": { "Name": "Bad bowtie polygon", "_layer": "survey" },
      "geometry": { "type": "Polygon", "coordinates": ["..."] }
    }
  ]
}
```

(`properties` and `coordinates` are shortened here; `properties` holds every attribute found in the file.)

**Feature status values**

| Status | Geometry | Result |
| --- | --- | --- |
| `SUCCESS` | Polygon, MultiPolygon, LineString, MultiLineString | `area_m2` (holes subtracted, parts summed) or `length_m` |
| `NO_MEASUREMENT_REQUIRED` | Point, MultiPoint | no numbers |
| `UNSUPPORTED` | GeometryCollection and anything else | `error` explains |
| `FAILED` | Invalid, empty or unprojectable geometry | `error` explains |

File status is `COMPLETED`, or `COMPLETED_WITH_ERRORS` when any feature is `FAILED` or `UNSUPPORTED`.

## Architecture

```
app/
  main.py                  FastAPI app, /health
  config.py                limits and settings (env overridable)
  database.py              SQLAlchemy engine and session
  exceptions.py            IngestionError (a client-fixable problem, maps to 4xx)
  api/routes/files.py      the three endpoints, thin: validate, call service, shape response
  schemas/file.py          Pydantic response models
  models/file.py           files and features tables
  services/
    ingestion.py           KML / Shapefile zip -> GeoDataFrame + source CRS
    crs.py                 choose the measurement CRS
    measurement.py         classify and measure one geometry
    processing.py          orchestrates one upload end to end, persists results
  utils/file_security.py   filename cleaning, upload size limit, safe zip extraction
tests/                     pytest suite (API tests with an in-memory SQLite database)
scripts/make_samples.py    regenerates sample_data/
```

### File-processing flow

1. The route checks the extension (`.kml` / `.zip`) and streams the upload to a temp file, enforcing the size limit.
2. `ingestion` reads it. KML is read layer by layer (every folder), always as EPSG:4326. A zip is extracted
   safely, must contain exactly one Shapefile with `.shx`, `.dbf` and `.prj`, and is read with pyogrio.
   Z (altitude) values are dropped because measurements are on the ground plane.
3. `processing` plans the CRS, projects the dataset, then measures each feature independently.
4. One `files` row and one `features` row per feature are stored; the temp files are deleted.

### Measurement flow

For each feature: no geometry -> `FAILED`; Point/MultiPoint -> `NO_MEASUREMENT_REQUIRED`; other non-area,
non-line types -> `UNSUPPORTED`; otherwise validity is checked on the geometry as authored (invalid -> `FAILED`
with the reason), then the **projected** copy is measured with Shapely (`.area` or `.length`) and rounded to
4 decimals. One bad feature never fails the file.

### CRS handling

- The measurement CRS is **one UTM zone for the whole dataset**, taken from the centre of its WGS 84 extent
  (EPSG:326xx north, 327xx south). Both the source CRS and the measurement CRS are in every response.
- Input already in a UTM zone keeps its own CRS.
- Other projected input, notably **Web Mercator (EPSG:3857)**, is **re-projected to UTM**. A projected CRS is not
  automatically accurate: Mercator inflates area by about 1/cos2(latitude), roughly 25% at 27 degrees north.
- A Shapefile with no `.prj` is rejected with 422. The CRS is never guessed.
- If the dataset spans several UTM zones it is still measured in one zone and `warnings` says so.
- If the dataset is centred outside 80 S to 84 N (where UTM is not defined) its features are `FAILED` with a clear
  error and **no numbers are produced**.

## Design Decisions

| Decision | Chosen | Alternatives considered | Why |
| --- | --- | --- | --- |
| One CRS per dataset vs per feature | One UTM zone per dataset | A UTM zone per feature centroid | A single, explainable CRS keeps results comparable and the response simple. The multi-zone limitation is surfaced as a warning rather than hidden. |
| Where `pyproj.Geod` is used | Tests only | Use geodesic maths in the service | The service has one authoritative method. Geod is an independent reference that proves the UTM results are within 0.2% (`tests/test_accuracy.py`). |
| Re-project Web Mercator | Yes, to UTM | Trust any projected CRS | Mercator area is badly inflated away from the equator. |
| Processing model | Synchronous | Background queue (Celery/Redis) | The assignment says the upload "processes" the file, the response is immediately useful, and there is no queue to operate. Limits on size bound the work. |
| Database | SQLite via SQLAlchemy | PostgreSQL/PostGIS | Zero setup for a reviewer. SQLAlchemy keeps the move to Postgres to a connection string. Geometries are stored as GeoJSON, since the API never queries spatially. |
| Missing CRS | Reject with 422 | Assume EPSG:4326 | Guessing a CRS silently produces wrong numbers, which is worse than a clear error. |
| Multi-geometries | Measured (sum of parts) | Mark unsupported | They are common in real survey data. GeometryCollection stays `UNSUPPORTED` because a single area/length is ambiguous. |
| Failures | Per feature | Fail the whole upload | A bad polygon should not hide 500 good ones. File-level counts and status make partial success visible. |
| Zip handling | Allow-list of extensions, entry limit, size limit counted on bytes read, no symlinks, no path traversal | Extract everything | Uploaded archives are untrusted input (zip-slip, zip bombs). |

## Limitations

- UTM distortion grows toward the edges of a zone (about 0.04% scale error at the edge) and datasets spanning
  zones are measured in a single one.
- Latitudes beyond 80 S / 84 N are refused rather than approximated.
- Very long lines (hundreds of kilometres) lose accuracy in any single projection.
- Only the first Shapefile in a zip is read, and exactly one is required.
- No authentication, pagination or deletion endpoint. Whole results are returned in one response.
- Files are processed inside the request, so a very large file blocks that request until done.

## Learning

- A latitude/longitude pair is an angle, not a distance. `polygon.area` on EPSG:4326 returns square degrees, so the
  CRS step is the heart of the problem, not an add-on. The tests build shapes with known metre sizes to prove it.
- A projected CRS is not automatically a correct one. Web Mercator is projected and still wrong for area.
- Validating the result against an independent method (`pyproj.Geod`) is a better test than re-checking the same formula.
- Treating uploads as hostile (zip-slip, zip bombs, forged archive sizes) changes the design of the extraction code.
- Deciding what *not* to build (queues, PostGIS, auth, per-feature zones) made the remaining code easier to defend.

## Future Scope

- Background processing with a job queue and a progress endpoint for very large files, with chunked or streamed reads.
- PostgreSQL/PostGIS, which would also allow spatial queries and bounding-box filters.
- Per-feature or per-zone measurement for datasets that span many UTM zones, or a documented equal-area fallback
  (for example a local Lambert azimuthal equal-area CRS) for polar data.
- Pagination and filtering on the measurements endpoint, plus CSV and GeoJSON export.
- More input formats (GeoJSON, KMZ, GeoPackage).
- Authentication and per-user file ownership, with deletion and retention rules.
