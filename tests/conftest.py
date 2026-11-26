import os
from pathlib import Path

# Must be set before the app is imported. CI overrides this with a real
# PostgreSQL URL; locally the tests use an in-memory SQLite database.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402, F401  (registers the tables)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

TESTS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items):
    """Mark each test by its folder, so `pytest -m unit` (or api, db) works."""
    for item in items:
        folder = Path(item.fspath).relative_to(TESTS_DIR).parts[0]
        if folder in {"unit", "api", "db"}:
            item.add_marker(folder)


def pytest_report_header():
    return f"database under test: {engine.url.render_as_string(hide_password=True)}"


@pytest.fixture(autouse=True)
def clean_database(request):
    """Give every test that may touch the database empty tables."""
    if request.node.get_closest_marker("unit"):
        yield
        return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_task(client):
    """Create a task through the API and return its JSON."""

    def _make_task(**fields):
        payload = {"title": "Sample task", **fields}
        response = client.post("/api/v1/tasks", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make_task
