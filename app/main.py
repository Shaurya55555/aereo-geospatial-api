from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import files
from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    description=(
        "Upload a KML or a zipped Shapefile and get area and length measurements for every "
        "feature, calculated in a projected CRS (never on latitude/longitude degrees)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(files.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
