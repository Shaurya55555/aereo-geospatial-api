import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    from app.models import file  # noqa: F401  (registers the tables)

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # No `with`: skip the lifespan so the on-disk database is never created.
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def upload(client):
    """upload(name, content) -> response"""

    def _upload(filename: str, content: bytes, content_type: str = "application/octet-stream"):
        return client.post("/api/files/", files={"file": (filename, content, content_type)})

    return _upload


@pytest.fixture()
def measurements(client, upload):
    """measurements(name, content, **query) -> (upload response, measurements JSON)"""

    def _measure(filename: str, content: bytes, **query):
        response = upload(filename, content)
        assert response.status_code == 201, response.text
        result = client.get(f"/api/files/{response.json()['id']}/measurements/", params=query)
        assert result.status_code == 200
        return response.json(), result.json()

    return _measure
