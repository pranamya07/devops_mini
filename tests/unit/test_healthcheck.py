"""Unit tests for the Docker HEALTHCHECK script (the network call is faked)."""

import urllib.error

import pytest

from app import healthcheck


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def calls(monkeypatch):
    """Record the URLs the health check requests."""
    seen = []

    def install(result):
        def fake_urlopen(url, timeout):
            seen.append(url)
            if isinstance(result, Exception):
                raise result
            return FakeResponse(result)

        monkeypatch.setattr(healthcheck.urllib.request, "urlopen", fake_urlopen)
        return seen

    return install


def test_healthy_api_exits_zero(calls):
    calls(200)
    assert healthcheck.main() == 0


def test_uses_port_from_environment(calls, monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    seen = calls(200)

    healthcheck.main()

    assert seen == ["http://127.0.0.1:10000/health"]


def test_defaults_to_port_8000(calls, monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    seen = calls(200)

    healthcheck.main()

    assert seen == ["http://127.0.0.1:8000/health"]


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.HTTPError("http://x/health", 503, "Service Unavailable", {}, None),
        urllib.error.URLError("connection refused"),
        TimeoutError("timed out"),
    ],
    ids=["unhealthy-503", "api-not-running", "timeout"],
)
def test_failures_exit_non_zero(calls, failure):
    calls(failure)
    assert healthcheck.main() == 1
