# Testing

Testing happens at seven levels, from fast unit tests up to checks against the live site
after every release. All of them run automatically in CI.

| Level | What | Tool | When it runs |
|---|---|---|---|
| 1. Unit tests | Validation rules, settings, logging, health-check script, release scripts | pytest | Every push and PR |
| 2. API tests | Every endpoint over HTTP, including errors, edge cases, metrics and logs | pytest + FastAPI TestClient | Every push and PR |
| 3. Database tests | Data layer on a real PostgreSQL 17 | pytest + PostgreSQL service container | Every push and PR |
| 4. Alert-rule tests | Each alert fires at the right time, and not too early | `promtool test rules` | Every push and PR |
| 5. Static checks | Python lint and security rules, formatting, Dockerfile lint | Ruff, hadolint | Every push and PR |
| 6. Container smoke test | The real image with PostgreSQL: health, non-root user, data survives a restart | `scripts/smoke_test.sh` | Every push and PR, before anything is published |
| 7. Post-deployment checks | The live site on Render after a release; a failure triggers rollback | `scripts/verify_deployment.py` | Every release |

The pipeline fails if any test fails or if code coverage drops below **90%**.

## Latest results

Local run on PostgreSQL 17, 26 Nov 2026, with the same command CI uses:

| Suite | Tests | Result |
|---|---|---|
| Unit (`tests/unit/`) | 58 | ✅ all passed |
| API (`tests/api/`) | 88 | ✅ 87 passed, 1 skipped on macOS (CPU/memory metrics only exist on Linux; this test runs in CI and Docker) |
| Database (`tests/db/`) | 13 | ✅ all passed |
| **Total** | **159** | **✅ 158 passed, 1 platform skip, 0 failed** |
| Code coverage | | **97.4%** (statements and branches; minimum 90%) |
| Alert-rule tests | 4 | ✅ all passed |
| Container smoke test | 6 checks | ✅ passed |

Every CI run publishes its own results:
- **Run page:** a test results table and a coverage table, in the summary.
- **Artifacts:** `test-reports` contains `junit.xml`, `coverage.xml` and a browsable HTML coverage report.

## What each suite covers

### Unit tests: `tests/unit/` (58)

| File | Tests | Covers |
|---|---|---|
| `test_schemas.py` | 23 | Defaults; trimming; boundary lengths (200/201 characters); missing, blank, null and wrong-type titles; invalid status, priority and dates; unknown fields; PATCH null rules |
| `test_config.py` | 6 | Render's `postgres://` URLs are converted; defaults; environment variables override defaults |
| `test_healthcheck.py` | 6 | The Docker health check passes on 200, fails on 503, connection refused or timeout, and uses `$PORT` |
| `test_logging_config.py` | 6 | Timestamp format, INFO to stdout and ERROR to stderr, `LOG_LEVEL` respected |
| `test_verify_deployment.py` | 9 | Post-deployment check against a fake live site: waits for the new version, times out, catches a database outage, crashing endpoints, and an app that dies after starting |
| `test_release_scripts.py` | 8 | Deploy hook gets the exact image tag (URL-encoded); a rejected deploy fails; the rollback target skips failed releases and handles the first release |

### API tests: `tests/api/` (88)

| File | Tests | Covers |
|---|---|---|
| `test_tasks_api.py` | 52 | Create (201, `Location` header, 9 invalid bodies → 422, malformed JSON), list (order, filters, pagination, 6 invalid queries), get (404 message, invalid IDs), PUT (replaces all fields), PATCH (partial update, `updated_at` moves forward, clear description, 5 invalid bodies), DELETE (204, twice gives 404), 405, full lifecycle |
| `test_observability.py` | 25 | `/metrics` format; route patterns used as labels (`/tasks/{task_id}`, not one series per ID); latency; task-operation counters; request IDs (generated, kept, unsafe ones replaced); log levels per status; **database outage → 503 + error log + metric**; **crash → 500 + traceback logged + counted** |
| `test_system_endpoints.py` | 11 | `/`, `/health` (200 and 503), greeting, deployment info, production settings applied in a fresh process, unknown route 404, Swagger and OpenAPI schema |

### Database tests: `tests/db/` (13)

Saved data is visible from a new session; enums are stored as readable text; ordering,
filters and pagination; `updated_at` changes and `created_at` doesn't; the database enforces
NOT NULL on `title`; delete removes the row; reachable and unreachable databases are detected;
tables are created on startup.

### Alert-rule tests: `monitoring/prometheus/alerts.test.yml` (4)

Each test feeds fake metrics into Prometheus and checks the outcome:

| Test | Checks that |
|---|---|
| API down | Doesn't fire after 45s, fires after the 1-minute grace period |
| High error rate | 10% failures fires; 1% failures doesn't |
| Database unreachable | Fires once `/health` returns 503 |
| Latency | Fast responses never trigger it |

### Container smoke test: `scripts/smoke_test.sh`

Runs the exact image about to be published, together with PostgreSQL:

1. Both containers become healthy.
2. `/health` returns 200 with the database connected.
3. The API runs as UID 10001, not root.
4. A task is created.
5. Both containers are restarted.
6. The task is still there, and Docker reports the API container as `healthy`.

### Post-deployment checks: `scripts/verify_deployment.py`

Runs against the live Render URL after each release:

1. Waits for the new version to be live.
2. Checks `/health` and the database connection.
3. Lists tasks, creates a task, reads it back and deletes it.
4. Re-checks `/health` a few times, in case the app crashes soon after starting.

If any of these fails, the pipeline rolls back. See
[release-and-rollback.md](release-and-rollback.md).

## Running the tests

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest                    # everything, with a coverage report
pytest -m unit            # one level: unit, api or db
pytest tests/api/test_tasks_api.py -k patch     # a subset by name

# Against PostgreSQL instead of the default in-memory SQLite:
docker run -d --rm --name test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17-alpine
DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres pytest

# Coverage as a browsable HTML report:
pytest --cov-report=html && open htmlcov/index.html

# Container smoke test (builds the image; use API_PORT if 8000 is busy):
./scripts/smoke_test.sh

# Alert-rule tests:
docker run --rm -v "$PWD/monitoring/prometheus:/p" -w /p --entrypoint promtool \
  prom/prometheus:v3.16.0 test rules alerts.test.yml
```

## Problems found by testing and scanning

| Found by | Problem | Fix |
|---|---|---|
| API tests (53 failures) | Metric labels broke on this FastAPI version, which stores included routers differently | Read the matched route from the request instead of searching the router list |
| Trivy image scan | 4 HIGH vulnerabilities in Debian packages (`apt`, `zlib`, `zstd`) | Rebuild on the latest base image and install Debian security updates during the build |
| Trivy image scan | 6 CVEs in the `pip` bundled with the base image, and a HIGH one in pip's bundled setuptools | Remove pip from the final image (the app never uses it) |
| hadolint | Container user set by name, so a platform can't check it isn't root | Fixed numeric UID 10001 |
| System test | App logs on stdout broke a test that read stdout | That test sets `LOG_LEVEL=WARNING` |
| Rollback rehearsal | A release that adds a column passes every test (empty CI database) but fails in production | Post-deployment checks catch it and roll back; this is the rollback demo |

## Showing that CI blocks broken code

1. On a branch, break a test on purpose. For example, in `tests/api/test_system_endpoints.py`,
   change `"healthy"` to `"broken"`.
2. Push the branch and open a PR into `dev`.
3. The **Unit, API and Database Tests** job fails ❌. The run summary lists the failing test,
   and the build, publish and deploy jobs never run.
4. Revert the change and push again. Everything goes green ✅.

If branch protection on `dev`/`main` requires the CI checks, GitHub also blocks merging
the PR while it's red.
