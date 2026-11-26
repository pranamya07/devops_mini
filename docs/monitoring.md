# Monitoring and logging

| Part | Where |
|---|---|
| Metrics endpoint | `GET /metrics` on the API ([app/observability.py](../app/observability.py)) |
| Prometheus config | [monitoring/prometheus/prometheus.yml](../monitoring/prometheus/prometheus.yml) |
| Alert rules and their tests | [alerts.yml](../monitoring/prometheus/alerts.yml), [alerts.test.yml](../monitoring/prometheus/alerts.test.yml) |
| Grafana dashboard | [monitoring/grafana/dashboards/task-api.json](../monitoring/grafana/dashboards/task-api.json) |
| Logging setup | [app/logging_config.py](../app/logging_config.py) |

`docker compose up -d` starts Prometheus (http://localhost:9090) and Grafana
(http://localhost:3000) with everything already set up.

## Metrics

| Metric | Type | Labels | Shows |
|---|---|---|---|
| `http_requests_total` | counter | method, path, status | Request rate and error rate. `path` is the route pattern (`/api/v1/tasks/{task_id}`), so there's one series per route, not per ID. |
| `http_request_duration_seconds` | histogram | method, path | Latency; p50/p95/p99 |
| `http_requests_in_progress` | gauge | | Requests being handled right now |
| `http_exceptions_total` | counter | path, exception | Unhandled errors by type |
| `task_operations_total` | counter | operation | Tasks created, replaced, updated, deleted |
| `app_info` | gauge | app_name, version, environment | The **running version**, which changes on deploy and rollback |
| `process_cpu_seconds_total` | counter | | CPU used by the API process |
| `process_resident_memory_bytes` | gauge | | Memory used by the API process |
| `up` | gauge | job, deployment | Whether Prometheus can reach the API |

`/metrics` itself isn't counted, so Prometheus's own scrapes don't inflate the traffic numbers.

## Prometheus

| Job | Target | Interval |
|---|---|---|
| `task-api` | `api:8000` (local Compose), label `deployment=local` | 5s |
| `task-api-render` | Render URL over HTTPS, label `deployment=render` | 30s |
| `prometheus` | itself | 5s |

To monitor the live site, put its hostname in
[targets/render.yml](../monitoring/prometheus/targets/render.yml):

```yaml
- targets: ["devops-mini-xxxx.onrender.com"]
  labels:
    deployment: render
```

Prometheus reloads the file by itself within a few minutes. To pick it up straight away,
run `docker compose restart prometheus`.

### Alert rules

| Alert | Fires when | For | Severity |
|---|---|---|---|
| `TaskApiDown` | Prometheus can't scrape the API | 1 min | critical |
| `TaskApiHighErrorRate` | More than 5% of requests return 5xx | 1 min | warning |
| `TaskApiDatabaseUnreachable` | `/health` returns 503 | 30 s | critical |
| `TaskApiSlowResponses` | p95 latency above 500 ms | 5 min | warning |

Active alerts are listed at http://localhost:9090/alerts. All four rules have automated tests
(`promtool test rules`) that run in CI.

## Grafana dashboard: "Task API - Overview"

It opens as Grafana's home page, and no login is needed to view it. The **Deployment**
dropdown at the top switches between `local`, `render` or all.

| Row | Panels |
|---|---|
| Summary | Running version · Uptime · Requests/sec · Error rate (5xx) · p95 latency · Tasks created |
| Traffic | Requests per second by route · Responses by status code |
| Performance | Latency p50/p95/p99 · Error rate over time, with the 5% alert line |
| Resources | CPU usage · Memory · Task operations per minute |

## Logging

Every log line has a UTC timestamp, a level and the source:

```text
2026-11-26T14:18:50.458Z | INFO     | app          | Starting Task Management API version=1.0.0 environment=development database=postgresql+psycopg://taskapi:***@db:5432/taskapi
2026-11-26T14:19:02.113Z | INFO     | app.tasks    | Task created id=42 priority=high
2026-11-26T14:19:02.114Z | INFO     | app.requests | POST /api/v1/tasks 201 6.2ms request_id=3f9c1a7e5b2d4c80
2026-11-26T14:19:05.870Z | WARNING  | app.requests | GET /api/v1/tasks/999 404 2.1ms request_id=a1b2c3d4e5f60718
2026-11-26T14:21:34.962Z | ERROR    | app          | Database error on POST /api/v1/tasks: OperationalError
```

| What | How |
|---|---|
| Request log | One line per request: method, path, status, duration, request ID. 2xx is INFO, 4xx WARNING, 5xx ERROR. |
| Request ID | Returned in the `X-Request-ID` header, so a user's error can be matched to its log line |
| Error logs | ERROR and CRITICAL go to **stderr**, everything else to **stdout**; unhandled errors include the traceback |
| Level | Set with `LOG_LEVEL` (default `INFO`) |
| Container logs | Docker `json-file` driver, rotated at 10 MB, 3 files per container |
| Secrets | Database passwords are masked as `***` |

Reading logs:

```bash
docker compose logs -f api                                  # all API logs, live
docker logs "$(docker compose ps -q api)" 2>&1 >/dev/null   # errors only (stderr)
docker compose logs db prometheus grafana                   # the other containers
```

On Render, the same lines appear in the service's **Logs** tab.

## Demo: watching a failure happen

```bash
docker compose up -d --build
python3 scripts/generate_traffic.py --duration 300 &   # steady traffic
```

1. Open Grafana at http://localhost:3000. Requests/sec is about 5 and the error rate is 0%.
2. Break the database with `docker compose stop db`. Within about a minute:
   - the API answers `503` instead of crashing
   - Grafana's error rate jumps to 100%
   - `TaskApiDatabaseUnreachable` and `TaskApiHighErrorRate` fire at http://localhost:9090/alerts
   - the error log shows `Database error on POST /api/v1/tasks: OperationalError`
3. Fix it with `docker compose start db`. The API recovers by itself, with no restart, and the alerts clear.
