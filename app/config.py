"""Application settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}")

# Upload limits (bytes / counts).
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 50 * 1024 * 1024))
MAX_EXTRACTED_SIZE = int(os.getenv("MAX_EXTRACTED_SIZE", 200 * 1024 * 1024))
MAX_ARCHIVE_FILES = int(os.getenv("MAX_ARCHIVE_FILES", 100))

ALLOWED_EXTENSIONS = {".kml", ".zip"}

# UTM is defined between 80 degrees S and 84 degrees N.
UTM_MIN_LAT = -80.0
UTM_MAX_LAT = 84.0
