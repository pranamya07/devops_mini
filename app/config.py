import os

APP_NAME = os.getenv("APP_NAME", "Task Management API")
APP_ENV = os.getenv("APP_ENV", "development")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Local runs without Docker fall back to a SQLite file so the API still starts.
# Docker Compose, CI and Render always set DATABASE_URL to PostgreSQL.
DEFAULT_DATABASE_URL = "sqlite:///./tasks.db"


def normalize_database_url(url: str) -> str:
    """Make provider URLs usable by SQLAlchemy with the psycopg 3 driver.

    Render and most hosts hand out ``postgres://`` or ``postgresql://`` URLs,
    which SQLAlchemy would pair with the old psycopg2 driver.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
