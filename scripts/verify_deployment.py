"""Post-deployment check: wait for a version to go live, then smoke test it.

1. Poll /api/v1/deployment-info until it reports the expected version
   (Render switches traffic to the new version once it passes its health check).
2. Smoke test the live API: /health, list tasks, create -> read -> delete a task.
3. Re-check /health a few times to catch a version that crashes shortly after start.

Exits 0 if every check passes, 1 otherwise (CI then rolls back).

Usage:
    python scripts/verify_deployment.py \
        --base-url https://your-app.onrender.com --expected-version 1.1.0
    python scripts/verify_deployment.py --base-url http://localhost:8000 --expected-version 1.0.0

Uses only the Python standard library.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable


def call(base_url: str, method: str, path: str, body=None, timeout: float = 60):
    """Return (status, parsed JSON or None). Network errors return status 0."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(  # noqa: S310 (URL comes from the CLI)
        base_url + path, data=data, method=method, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        return 0, {"error": str(error)}
    try:
        return status, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return status, None


def wait_for_version(base_url, expected, timeout, interval, log) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        status, info = call(base_url, "GET", "/api/v1/deployment-info")
        live = (info or {}).get("version") if status == 200 else None
        if live == expected:
            log(f"✓ version {expected} is live")
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log(f"✗ timed out: live version is {live or f'unreachable (HTTP {status})'}")
            return False
        log(f"… live version: {live or f'unreachable (HTTP {status})'}, waiting for {expected}")
        time.sleep(min(interval, remaining))


def smoke_test(base_url, version, log) -> list[str]:
    failures = []

    def check(name, ok, detail=""):
        log(f"{'✓' if ok else '✗'} {name}{f' ({detail})' if detail and not ok else ''}")
        if not ok:
            failures.append(f"{name}: {detail}")
        return ok

    status, body = call(base_url, "GET", "/health")
    check("GET /health returns 200", status == 200, f"HTTP {status} {body}")
    check(
        "database is connected",
        (body or {}).get("database") == "connected",
        f"got {(body or {}).get('database')}",
    )

    status, body = call(base_url, "GET", "/api/v1/tasks?limit=1")
    check("GET /api/v1/tasks returns 200", status == 200, f"HTTP {status} {body}")

    title = f"Post-deploy check for {version}"
    status, task = call(base_url, "POST", "/api/v1/tasks", {"title": title})
    if check("POST /api/v1/tasks creates a task", status == 201, f"HTTP {status} {task}"):
        task_url = f"/api/v1/tasks/{task['id']}"
        status, body = call(base_url, "GET", task_url)
        check(
            "the new task can be read back",
            status == 200 and (body or {}).get("title") == title,
            f"HTTP {status}",
        )
        status, _ = call(base_url, "DELETE", task_url)
        check("the test task is deleted again", status == 204, f"HTTP {status}")

    return failures


def stays_healthy(base_url, checks, interval, log) -> bool:
    for attempt in range(1, checks + 1):
        status, _ = call(base_url, "GET", "/health")
        if status != 200:
            log(f"✗ /health returned HTTP {status} on stability check {attempt}/{checks}")
            return False
        if attempt < checks:
            time.sleep(interval)
    log(f"✓ still healthy after {checks} checks")
    return True


def verify(
    base_url: str,
    expected_version: str,
    timeout: float = 900,
    interval: float = 15,
    stability_checks: int = 3,
    log: Callable[[str], None] = print,
) -> bool:
    base_url = base_url.rstrip("/")
    log(f"Verifying {base_url} is running version {expected_version}")
    if not wait_for_version(base_url, expected_version, timeout, interval, log):
        return False
    failures = smoke_test(base_url, expected_version, log)
    if failures:
        log(f"Deployment of {expected_version} FAILED {len(failures)} check(s)")
        return False
    if not stays_healthy(base_url, stability_checks, interval, log):
        return False
    log(f"Deployment of {expected_version} verified")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--timeout",
        type=float,
        default=900,
        help="seconds to wait for the version to go live (default 900: Render deploys and "
        "free-plan cold starts are slow)",
    )
    parser.add_argument("--interval", type=float, default=15, help="seconds between polls")
    parser.add_argument("--stability-checks", type=int, default=3)
    args = parser.parse_args(argv)

    ok = verify(
        args.base_url,
        args.expected_version,
        timeout=args.timeout,
        interval=args.interval,
        stability_checks=args.stability_checks,
        log=lambda line: print(line, flush=True),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
