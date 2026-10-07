"""Generate the small sample files in sample_data/ (run: python scripts/make_samples.py).

Geometries are built in metres around Jaipur (UTM zone 43N) so their true sizes are known,
then converted to longitude/latitude. Expected results are listed in sample_data/README.md.
"""
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

OUT = Path(__file__).resolve().parent.parent / "sample_data"
UTM = "EPSG:32643"
X0, Y0 = 750000.0, 2977000.0  # near Jaipur, India


def utm_square(x, y, side):
    return box(X0 + x, Y0 + y, X0 + x + side, Y0 + y + side)


def to_wgs84(geoms, names):
    return gpd.GeoDataFrame({"Name": names}, geometry=geoms, crs=UTM).to_crs(4326)


def make_kml():
    square = utm_square(0, 0, 1000)  # exactly 1 km x 1 km = 1,000,000 m2
    with_hole = Polygon(
        utm_square(2000, 0, 1000).exterior.coords,
        [utm_square(2250, 250, 500).exterior.coords],  # 500 m x 500 m hole
    )  # 1,000,000 - 250,000 = 750,000 m2
    multi = MultiPolygon([utm_square(0, 2000, 100), utm_square(500, 2000, 100)])  # 20,000 m2
    road = LineString([(X0, Y0 - 500), (X0 + 3000, Y0 - 500), (X0 + 3000, Y0 - 1500)])  # 4,000 m
    gate = Point(X0 + 500, Y0 + 500)
    bowtie = Polygon([(X0, Y0 + 4000), (X0 + 100, Y0 + 4100), (X0 + 100, Y0 + 4000), (X0, Y0 + 4100)])
    gdf = to_wgs84(
        [square, with_hole, multi, road, gate, bowtie],
        ["Plot 1km square", "Plot with hole", "Two small plots", "Road", "Gate", "Bad bowtie polygon"],
    )
    # The KML driver writes one layer; Name becomes the placemark name.
    path = OUT / "survey.kml"
    path.unlink(missing_ok=True)
    gdf.to_file(path, driver="KML")


def make_shapefile_zip(name, gdf):
    with tempfile.TemporaryDirectory() as tmp:
        shp = Path(tmp) / f"{name}.shp"
        gdf.to_file(shp)
        archive = OUT / f"{name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in Path(tmp).iterdir():
                zf.write(part, part.name)


def main():
    OUT.mkdir(exist_ok=True)
    make_kml()

    parcels = to_wgs84(
        [utm_square(0, 0, 1000), utm_square(1500, 0, 500), utm_square(0, 1500, 200)],
        ["Parcel A", "Parcel B", "Parcel C"],
    )
    make_shapefile_zip("parcels_wgs84", parcels)  # 1,000,000 / 250,000 / 40,000 m2

    # Same parcels already in a projected CRS (UTM 43N), to show projected input handling.
    projected = gpd.GeoDataFrame(
        {"Name": ["Parcel A", "Parcel B", "Parcel C"]},
        geometry=[utm_square(0, 0, 1000), utm_square(1500, 0, 500), utm_square(0, 1500, 200)],
        crs=UTM,
    )
    make_shapefile_zip("parcels_utm", projected)

    # Web Mercator input: must be re-projected before measuring (Mercator inflates area).
    make_shapefile_zip("parcels_webmercator", parcels.to_crs(3857))

    # Shapefile with the .prj removed: the API must refuse to guess a CRS.
    with tempfile.TemporaryDirectory() as tmp:
        shp = Path(tmp) / "no_prj.shp"
        parcels.to_file(shp)
        with zipfile.ZipFile(OUT / "no_prj.zip", "w") as zf:
            for part in Path(tmp).iterdir():
                if part.suffix != ".prj":
                    zf.write(part, part.name)

    print("sample files written to", OUT)


if __name__ == "__main__":
    main()
