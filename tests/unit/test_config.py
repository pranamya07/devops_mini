"""Unit tests for settings read from environment variables."""

import importlib

import pytest

import app.config as config
from app.config import normalize_database_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # Render hands out URLs in these two shapes.
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # Already-correct and non-Postgres URLs are left alone.
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///./tasks.db", "sqlite:///./tasks.db"),
    ],
)
def test_normalize_database_url(given, expected):
    assert normalize_database_url(given) == expected


@pytest.fixture
def reload_config():
    """Reload app.config with the patched environment, then restore it."""
    yield lambda: importlib.reload(config)
    importlib.reload(config)


def test_defaults_when_environment_is_empty(monkeypatch, reload_config):
    for name in ("APP_NAME", "APP_ENV", "APP_VERSION", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)

    settings = reload_config()

    assert settings.APP_NAME == "Task Management API"
    assert settings.APP_ENV == "development"
    assert settings.APP_VERSION == "1.0.0"
    assert settings.DATABASE_URL == settings.DEFAULT_DATABASE_URL


def test_environment_overrides_defaults(monkeypatch, reload_config):
    monkeypatch.setenv("APP_NAME", "Prod API")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_VERSION", "1.2.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db.render.com/tasks")

    settings = reload_config()

    assert settings.APP_NAME == "Prod API"
    assert settings.APP_ENV == "production"
    assert settings.APP_VERSION == "1.2.0"
    assert settings.DATABASE_URL == "postgresql+psycopg://u:p@db.render.com/tasks"
