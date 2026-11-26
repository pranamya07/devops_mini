"""API tests for monitoring and logging: /metrics, request IDs, error handling, logs."""

import logging
import re

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from sqlalchemy.exc import OperationalError

from app import crud
from app.main import app

TASKS = "/api/v1/tasks"


def sample(name, **labels):
    """Current value of a metric series (0 if it has not been recorded yet)."""
    return REGISTRY.get_sample_value(name, labels) or 0.0


def requests_count(method, path, status):
    return sample("http_requests_total", method=method, path=path, status=str(status))


def database_down(*args, **kwargs):
    raise OperationalError("SELECT 1", {}, ConnectionRefusedError("connection refused"))


class TestMetricsEndpoint:
    def test_serves_prometheus_text_format(self, client):
        response = client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "# TYPE http_requests_total counter" in response.text

    def test_reports_running_version(self, client):
        body = client.get("/metrics").text

        assert (
            'app_info{app_name="Task Management API",environment="development",version="1.0.0"} 1.0'
            in body
        )

    def test_includes_process_cpu_and_memory_on_linux(self, client):
        body = client.get("/metrics").text
        # prometheus_client only reports process metrics where /proc exists (Linux,
        # i.e. CI and Docker), so only check them there.
        if "process_cpu_seconds_total" not in body:
            pytest.skip("process metrics need Linux /proc")
        assert "process_resident_memory_bytes" in body

    def test_is_hidden_from_api_docs(self, client):
        assert "/metrics" not in client.get("/openapi.json").json()["paths"]

    def test_scrapes_are_not_counted_as_traffic(self, client):
        before = requests_count("GET", "/metrics", 200)
        client.get("/metrics")
        assert requests_count("GET", "/metrics", 200) == before


class TestRequestMetrics:
    def test_counts_requests_by_route_pattern_not_raw_url(self, client):
        before = requests_count("GET", "/api/v1/tasks/{task_id}", 404)

        client.get(f"{TASKS}/111")
        client.get(f"{TASKS}/222")

        assert requests_count("GET", "/api/v1/tasks/{task_id}", 404) == before + 2

    def test_unknown_urls_share_one_series(self, client):
        before = requests_count("GET", "unmatched", 404)

        client.get("/no/such/page")
        client.get("/another/missing/page")

        assert requests_count("GET", "unmatched", 404) == before + 2

    def test_records_latency(self, client):
        labels = {"method": "GET", "path": "/health"}
        before = sample("http_request_duration_seconds_count", **labels)

        client.get("/health")

        assert sample("http_request_duration_seconds_count", **labels) == before + 1
        assert sample("http_request_duration_seconds_sum", **labels) > 0

    def test_in_progress_returns_to_zero(self, client):
        client.get(TASKS)
        assert sample("http_requests_in_progress") == 0

    def test_counts_task_operations(self, client, make_task):
        ops = ("create", "replace", "update", "delete")
        before = {op: sample("task_operations_total", operation=op) for op in ops}

        task = make_task()
        client.put(f"{TASKS}/{task['id']}", json={"title": "Replaced"})
        client.patch(f"{TASKS}/{task['id']}", json={"status": "done"})
        client.delete(f"{TASKS}/{task['id']}")

        for op in ops:
            assert sample("task_operations_total", operation=op) == before[op] + 1

    def test_failed_validation_is_not_counted_as_an_operation(self, client):
        before = sample("task_operations_total", operation="create")
        client.post(TASKS, json={"title": ""})
        assert sample("task_operations_total", operation="create") == before


class TestRequestId:
    def test_generated_when_missing(self, client):
        request_id = client.get("/health").headers["x-request-id"]
        assert re.fullmatch(r"[0-9a-f]{16}", request_id)

    def test_each_request_gets_its_own(self, client):
        first = client.get("/health").headers["x-request-id"]
        second = client.get("/health").headers["x-request-id"]
        assert first != second

    def test_callers_id_is_kept(self, client):
        response = client.get("/health", headers={"X-Request-ID": "demo-123"})
        assert response.headers["x-request-id"] == "demo-123"

    @pytest.mark.parametrize("unsafe", ["has spaces", "x" * 65, "new\tline", 'quote"d'])
    def test_unsafe_id_is_replaced(self, client, unsafe):
        response = client.get("/health", headers={"X-Request-ID": unsafe})
        assert response.headers["x-request-id"] != unsafe


class TestRequestLogs:
    def request_logs(self, caplog):
        return [r for r in caplog.records if r.name == "app.requests"]

    def test_successful_request_is_logged_at_info(self, client, caplog):
        caplog.set_level(logging.INFO)

        response = client.get(TASKS, headers={"X-Request-ID": "log-test-1"})

        [record] = self.request_logs(caplog)
        assert record.levelno == logging.INFO
        assert re.fullmatch(
            r"GET /api/v1/tasks 200 \d+\.\dms request_id=log-test-1", record.getMessage()
        )
        assert response.headers["x-request-id"] == "log-test-1"

    def test_client_errors_are_logged_at_warning(self, client, caplog):
        caplog.set_level(logging.INFO)

        client.get(f"{TASKS}/9999")

        [record] = self.request_logs(caplog)
        assert record.levelno == logging.WARNING
        assert " 404 " in record.getMessage()

    def test_task_changes_are_logged(self, client, caplog, make_task):
        caplog.set_level(logging.INFO)

        task = make_task(priority="high")
        client.delete(f"{TASKS}/{task['id']}")

        messages = [r.getMessage() for r in caplog.records if r.name == "app.tasks"]
        assert messages == [
            f"Task created id={task['id']} priority=high",
            f"Task deleted id={task['id']}",
        ]


class TestDatabaseOutage:
    def test_task_endpoints_return_503(self, client, monkeypatch):
        monkeypatch.setattr(crud, "list_tasks", database_down)

        response = client.get(TASKS)

        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable, please try again shortly"}

    def test_outage_is_logged_as_error_and_counted(self, client, monkeypatch, caplog):
        monkeypatch.setattr(crud, "list_tasks", database_down)
        before = requests_count("GET", TASKS, 503)
        caplog.set_level(logging.INFO)

        client.get(TASKS)

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("Database error on GET /api/v1/tasks" in r.getMessage() for r in errors)
        assert requests_count("GET", TASKS, 503) == before + 1


class TestUnhandledErrors:
    @pytest.fixture
    def crashing_client(self, monkeypatch):
        def crash(*args, **kwargs):
            raise RuntimeError("unexpected bug")

        monkeypatch.setattr(crud, "list_tasks", crash)
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client

    def test_returns_500(self, crashing_client):
        assert crashing_client.get(TASKS).status_code == 500

    def test_is_counted_and_logged_with_traceback(self, crashing_client, caplog):
        before = sample("http_exceptions_total", path=TASKS, exception="RuntimeError")
        caplog.set_level(logging.INFO)

        crashing_client.get(TASKS)

        assert sample("http_exceptions_total", path=TASKS, exception="RuntimeError") == before + 1
        assert requests_count("GET", TASKS, 500) >= 1
        crash_logs = [r for r in caplog.records if r.exc_info and r.name == "app.requests"]
        assert crash_logs and "Unhandled error on GET /api/v1/tasks" in crash_logs[0].getMessage()
