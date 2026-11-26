"""API tests for the non-task endpoints: root, health, greeting, deployment info, docs."""

import json
import os
import subprocess
import sys
import textwrap

import app.main as main


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "FastAPI CI/CD project is running"
    assert "app_name" in data
    assert "environment" in data


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}


def test_health_returns_503_when_database_is_down(client, monkeypatch):
    monkeypatch.setattr(main, "database_is_reachable", lambda: False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "unreachable"}


def test_greeting_endpoint(client):
    response = client.get("/api/v1/greet/Pranamya")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Pranamya!"}


def test_greeting_endpoint_with_another_name(client):
    response = client.get("/api/v1/greet/Alex")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Alex!"}


def test_greeting_decodes_spaces_in_name(client):
    response = client.get("/api/v1/greet/Ada%20Lovelace")
    assert response.json() == {"message": "Hello, Ada Lovelace!"}


def test_deployment_info_endpoint(client):
    response = client.get("/api/v1/deployment-info")

    assert response.status_code == 200

    data = response.json()
    assert data["app_name"] == "Task Management API"
    assert data["environment"] == "development"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


def test_deployment_info_reflects_production_settings():
    """Start the app in a fresh process with Render-style settings."""
    script = textwrap.dedent(
        """
        import json
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            print(json.dumps(client.get("/api/v1/deployment-info").json()))
        """
    )
    env = {
        **os.environ,
        "APP_NAME": "Task Management API (prod)",
        "APP_ENV": "production",
        "APP_VERSION": "1.1.0",
        "DATABASE_URL": "sqlite:///:memory:",
    }

    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
    )

    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "app_name": "Task Management API (prod)",
        "environment": "production",
        "version": "1.1.0",
        "status": "running",
    }


def test_unknown_route_returns_404(client):
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_swagger_docs_are_served(client):
    assert client.get("/docs").status_code == 200


def test_openapi_schema_lists_task_routes(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths["/api/v1/tasks"]) == {"get", "post"}
    assert set(paths["/api/v1/tasks/{task_id}"]) == {"get", "put", "patch", "delete"}
