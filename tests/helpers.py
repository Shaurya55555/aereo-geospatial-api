"""Builders for test inputs with known, exact sizes."""
import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from pyproj import Geod
from shapely.geometry import Polygon, box

GEOD = Geod(ellps="WGS84")

# A point in UTM zone 43N (near Jaipur) used to place metre-based shapes on the Earth.
X0, Y0 = 750000.0, 2977000.0
UTM_43N = "EPSG:32643"


def utm_box(x: float, y: float, w: float, h: float):
    """Rectangle in UTM 43N metres, offset from (X0, Y0). Area is exactly w * h."""
    return box(X0 + x, Y0 + y, X0 + x + w, Y0 + y + h)


def to_wgs84(geoms, crs: str = UTM_43N, **columns) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(columns, geometry=list(geoms), crs=crs).to_crs(4326)


def geodesic_square(lon: float, lat: float, side_m: float) -> Polygon:
    """Square whose sides are `side_m` metres along the ellipsoid, as lon/lat vertices."""
    corners = [(lon, lat)]
    azimuths = [90, 180, 270]  # east, south, west; the fourth corner closes the ring
    lo, la = lon, lat
    for az in azimuths:
        lo, la, _ = GEOD.fwd(lo, la, az, side_m)
        corners.append((lo, la))
    return Polygon(corners)


def geodesic_area(polygon: Polygon) -> float:
    return abs(GEOD.geometry_area_perimeter(polygon)[0])


def geodesic_length(line) -> float:
    return GEOD.geometry_length(line)


def write_shapefile_zip(gdf: gpd.GeoDataFrame, name: str = "data", drop_suffixes=(), extra=None) -> bytes:
    """Zip a GeoDataFrame as a Shapefile. `drop_suffixes` removes components (e.g. '.prj')."""
    with tempfile.TemporaryDirectory() as tmp:
        gdf.to_file(Path(tmp) / f"{name}.shp")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in sorted(Path(tmp).iterdir()):
                if part.suffix.lower() not in drop_suffixes:
                    zf.write(part, part.name)
            for member, content in (extra or {}).items():
                zf.writestr(member, content)
    return buf.getvalue()


def make_zip(members: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def kml_document(placemarks: list[str]) -> bytes:
    body = "\n".join(placemarks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>\n'
        f"{body}\n</Document></kml>"
    ).encode()


def ring(coords) -> str:
    return " ".join(f"{x},{y}" for x, y in coords)


def kml_polygon(name: str, coords, holes=()) -> str:
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{ring(h)}</coordinates></LinearRing></innerBoundaryIs>"
        for h in holes
    )
    return (
        f"<Placemark><name>{name}</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{ring(coords)}</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon></Placemark>"
    )


def kml_line(name: str, coords) -> str:
    return (
        f"<Placemark><name>{name}</name><LineString><coordinates>{ring(coords)}"
        "</coordinates></LineString></Placemark>"
    )


def kml_point(name: str, lon: float, lat: float) -> str:
    return f"<Placemark><name>{name}</name><Point><coordinates>{lon},{lat}</coordinates></Point></Placemark>"
