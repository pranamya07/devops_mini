
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "FastAPI CI/CD project is running"
    assert "app_name" in data
    assert "environment" in data


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_greeting_endpoint():
    response = client.get("/api/v1/greet/Pranamya")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Pranamya!"}


def test_greeting_endpoint_with_another_name():
    response = client.get("/api/v1/greet/Alex")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Alex!"}
