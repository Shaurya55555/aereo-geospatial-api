"""Read an uploaded KML or zipped Shapefile into a GeoDataFrame."""
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely
from pyproj import CRS

from app.exceptions import IngestionError
from app.utils.file_security import safe_extract_shapefile

# KML is defined to use WGS 84 longitude/latitude, so it carries no CRS tag of its own.
KML_CRS = CRS.from_epsg(4326)


@dataclass
class IngestedData:
    gdf: gpd.GeoDataFrame
    crs: CRS
    file_type: str  # "kml" | "shapefile"


def ingest(path: Path, extension: str, workdir: Path) -> IngestedData:
    if extension == ".kml":
        return _read_kml(path)
    if extension == ".zip":
        return _read_shapefile_zip(path, workdir)
    raise IngestionError("Only .kml and .zip (Shapefile) uploads are supported.", status_code=400)


def _read_kml(path: Path) -> IngestedData:
    try:
        layers = [row[0] for row in pyogrio.list_layers(path)]
    except Exception as exc:
        raise IngestionError("File could not be parsed as KML.") from exc

    frames = []
    for layer in layers:
        try:
            frame = pyogrio.read_dataframe(path, layer=layer)
        except Exception as exc:
            raise IngestionError(f"KML layer {layer!r} could not be read.") from exc
        if len(frame) == 0:
            continue
        frame["_layer"] = layer
        frames.append(frame)

    if not frames:
        raise IngestionError("KML file contains no features.")

    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry")
    gdf = gdf.set_crs(KML_CRS, allow_override=True)
    gdf = _drop_z(gdf)
    return IngestedData(gdf=gdf, crs=KML_CRS, file_type="kml")


def _read_shapefile_zip(path: Path, workdir: Path) -> IngestedData:
    extracted = safe_extract_shapefile(path, workdir)

    shapefiles = [p for p in extracted if p.suffix.lower() == ".shp"]
    if not shapefiles:
        raise IngestionError("Zip archive does not contain a .shp file.")
    if len(shapefiles) > 1:
        raise IngestionError("Zip archive must contain exactly one Shapefile.")

    shp = shapefiles[0]
    siblings = {p.suffix.lower() for p in extracted if p.with_suffix("") == shp.with_suffix("")}
    missing = [ext for ext in (".shx", ".dbf") if ext not in siblings]
    if missing:
        raise IngestionError(f"Shapefile is incomplete, missing: {', '.join(missing)}.")
    if ".prj" not in siblings:
        raise IngestionError(
            "Shapefile has no .prj file, so its coordinate system is unknown. "
            "Measurements are not calculated on an assumed CRS."
        )

    try:
        gdf = pyogrio.read_dataframe(shp)
    except Exception as exc:
        raise IngestionError("Shapefile could not be read; the files may be corrupt.") from exc

    if gdf.crs is None:
        raise IngestionError("The .prj file could not be interpreted as a coordinate system.")
    if len(gdf) == 0:
        raise IngestionError("Shapefile contains no features.")

    gdf = _drop_z(gdf)
    return IngestedData(gdf=gdf, crs=CRS.from_user_input(gdf.crs), file_type="shapefile")


def _drop_z(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Measurements are planar on the ground, so any altitude (Z) values are discarded."""
    gdf = gdf.copy()
    gdf["geometry"] = gpd.GeoSeries(shapely.force_2d(gdf.geometry.values), index=gdf.index, crs=gdf.crs)
    return gdf
