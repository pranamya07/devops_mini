"""Unit tests for scripts/verify_deployment.py, the post-deployment check that
decides whether a release stays live or gets rolled back.

A fake API server plays the deployed app, so each failure mode can be simulated.
"""

import pytest

from tests.unit.conftest import load_script

verify_deployment = load_script("verify_deployment")


class FakeDeployedApi:
    """Behaves like the deployed API; tests switch individual endpoints to failing."""

    def __init__(self, server, versions=("1.1.0",)):
        self.versions = list(versions)  # one per poll; the last one repeats
        self.health = (200, {"status": "healthy", "database": "connected"})
        self.list_status = 200
        self.create_status = 201
        self.tasks = {}
        self.deleted = []
        server.routes.update(
            {
                ("GET", "/api/v1/deployment-info"): self.deployment_info,
                ("GET", "/health"): lambda _: self.health,
                ("GET", "/api/v1/tasks"): lambda _: (self.list_status, []),
                ("POST", "/api/v1/tasks"): self.create,
                ("GET", "/api/v1/tasks/1"): lambda _: (200, self.tasks.get(1)),
                ("DELETE", "/api/v1/tasks/1"): self.delete,
            }
        )

    def deployment_info(self, _):
        version = self.versions.pop(0) if len(self.versions) > 1 else self.versions[0]
        return 200, {"version": version, "status": "running"}

    def create(self, body):
        if self.create_status != 201:
            return self.create_status, {"detail": "Internal Server Error"}
        self.tasks[1] = {"id": 1, **body}
        return 201, self.tasks[1]

    def delete(self, _):
        self.deleted.append(1)
        return 204, None


def run(server, version="1.1.0", **options):
    logs = []
    settings = {"timeout": 5, "interval": 0.01, "stability_checks": 2, **options}
    ok = verify_deployment.verify(server.url, version, log=logs.append, **settings)
    return ok, logs


def test_healthy_release_passes(fake_server):
    api = FakeDeployedApi(fake_server)

    ok, logs = run(fake_server)

    assert ok
    assert logs[-1] == "Deployment of 1.1.0 verified"
    assert api.deleted == [1], "the smoke-test task must be cleaned up"


def test_waits_until_render_switches_to_the_new_version(fake_server):
    FakeDeployedApi(fake_server, versions=["1.0.0", "1.0.0", "1.1.0"])

    ok, logs = run(fake_server)

    assert ok
    assert sum("waiting for 1.1.0" in line for line in logs) == 2


def test_fails_if_new_version_never_goes_live(fake_server):
    FakeDeployedApi(fake_server, versions=["1.0.0"])

    ok, logs = run(fake_server, timeout=0.2)

    assert not ok
    assert "timed out: live version is 1.0.0" in logs[-1]


def test_fails_if_app_is_unreachable():
    logs = []
    ok = verify_deployment.verify(
        "http://127.0.0.1:9", "1.1.0", timeout=0.1, interval=0.01, log=logs.append
    )
    assert not ok
    assert "unreachable (HTTP 0)" in logs[-1]


@pytest.mark.parametrize(
    ("break_it", "failed_check"),
    [
        (
            lambda api: setattr(api, "health", (503, {"database": "unreachable"})),
            "GET /health returns 200",
        ),
        (lambda api: setattr(api, "list_status", 500), "GET /api/v1/tasks returns 200"),
        (lambda api: setattr(api, "create_status", 500), "POST /api/v1/tasks creates a task"),
    ],
    ids=["database-down", "listing-tasks-crashes", "creating-tasks-crashes"],
)
def test_live_version_with_a_broken_endpoint_fails(fake_server, break_it, failed_check):
    api = FakeDeployedApi(fake_server)
    break_it(api)

    ok, logs = run(fake_server)

    assert not ok
    assert any(line.startswith(f"✗ {failed_check}") for line in logs)
    assert "Deployment of 1.1.0 FAILED" in logs[-1]


def test_fails_if_app_becomes_unhealthy_shortly_after_start(fake_server):
    api = FakeDeployedApi(fake_server)
    health_calls = []

    def flaky_health(_):
        health_calls.append(1)
        # Healthy during the smoke test, then crashes on the 2nd stability check.
        return api.health if len(health_calls) <= 2 else (502, None)

    fake_server.routes[("GET", "/health")] = flaky_health

    ok, logs = run(fake_server, stability_checks=3)

    assert not ok
    assert "stability check 2/3" in logs[-1]


def test_command_line_exit_codes(fake_server):
    FakeDeployedApi(fake_server, versions=["1.1.0"])
    common = ["--base-url", fake_server.url, "--interval", "0.01", "--stability-checks", "1"]

    assert verify_deployment.main([*common, "--expected-version", "1.1.0"]) == 0
    assert verify_deployment.main([*common, "--expected-version", "9.9.9", "--timeout", "0.1"]) == 1
