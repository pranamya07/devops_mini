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


def test_greeting_endpoint(client):
    response = client.get("/api/v1/greet/Pranamya")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Pranamya!"}


def test_greeting_endpoint_with_another_name(client):
    response = client.get("/api/v1/greet/Alex")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Alex!"}


def test_deployment_info_endpoint(client):
    response = client.get("/api/v1/deployment-info")

    assert response.status_code == 200

    data = response.json()
    assert data["app_name"] == "Task Management API"
    assert data["environment"] == "development"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


def test_task_crud_round_trip(client):
    created = client.post("/api/v1/tasks", json={"title": "Set up PostgreSQL"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    assert client.get(f"/api/v1/tasks/{task_id}").json()["title"] == "Set up PostgreSQL"

    updated = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert updated.json()["status"] == "done"

    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 404
