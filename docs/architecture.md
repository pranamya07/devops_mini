# Architecture

1. [System architecture](#1-system-architecture)
2. [CI/CD pipeline](#2-cicd-pipeline)
3. [Application architecture](#3-application-architecture)
4. [Docker architecture](#4-docker-architecture)
5. [Database architecture](#5-database-architecture)
6. [Monitoring and logging architecture](#6-monitoring-and-logging-architecture)
7. [Release and rollback flow](#7-release-and-rollback-flow)

## 1. System architecture

```mermaid
flowchart TB
    dev([Developer]) -->|git push / pull request / version tag| github[GitHub repository]
    github --> actions

    subgraph actions [GitHub Actions: ci-cd.yml]
        direction LR
        lint[Lint & code quality<br/>Ruff · hadolint · promtool]
        tests[Tests<br/>unit · API · database<br/>on PostgreSQL]
        trivyfs[Trivy code scan<br/>secrets · misconfig]
        build[Docker build]
        trivyimg[Trivy image scan]
        smoke[Container smoke test]
        lint --> build
        tests --> build
        trivyfs --> build
        build --> trivyimg --> smoke
    end

    smoke -->|push versioned image<br/>1.2.0 · sha-abc1234| ghcr[(GitHub Container Registry)]
    ghcr -->|deploy hook with exact tag| web

    subgraph render [Render cloud]
        web[FastAPI container<br/>non-root, port from $PORT] -->|SQLAlchemy + psycopg| pg[(Render PostgreSQL)]
    end

    actions -.->|post-deployment checks<br/>rollback on failure| web

    subgraph monitoring [Monitoring: Docker Compose]
        prom[Prometheus<br/>scrape + alert rules] --> grafana[Grafana dashboard]
    end
    prom -->|GET /metrics every 30s| web
    users([Users / Swagger UI]) --> web
```

| Component | Technology | Runs on |
|---|---|---|
| API | Python 3.12, FastAPI, Uvicorn | Render (production), Docker Compose (local) |
| Database | PostgreSQL 17 | Render PostgreSQL (production), `postgres:17-alpine` container (local, CI) |
| Image registry | GitHub Container Registry (GHCR) | GitHub |
| CI/CD | GitHub Actions | GitHub-hosted Ubuntu runners |
| Security scanning | Trivy, hadolint, Ruff security rules | CI |
| Monitoring | Prometheus, Grafana | Docker Compose |

## 2. CI/CD pipeline

```mermaid
flowchart LR
    trigger{{"PR · push to dev/main · tag vX.Y.Z"}} --> lint & test & scan

    lint["<b>lint</b><br/>Ruff lint + format<br/>hadolint (Dockerfile)<br/>promtool check + test rules<br/>Grafana JSON check"]
    test["<b>test</b><br/>pytest on PostgreSQL service<br/>coverage ≥ 90%<br/>JUnit + coverage reports"]
    scan["<b>security-scan</b><br/>Trivy filesystem scan<br/>secrets · misconfig · deps"]

    lint & test & scan --> build

    build["<b>build</b><br/>docker build (APP_VERSION baked in)<br/>Trivy image scan: fixable HIGH/CRITICAL = fail<br/>SARIF → Security tab<br/>smoke test with Compose + PostgreSQL"]

    build -->|push events only| push["push to GHCR<br/>main · dev · sha-xxxxxxx<br/>1.2.0 · 1.2 · latest (tags)"]
    push -->|version tags only| deploy["<b>deploy</b><br/>Render deploy hook (exact tag)<br/>post-deployment checks"]
    deploy -->|checks fail| rollback["roll back to last good<br/>release and verify it"]
```

| Job | Fails the pipeline when |
|---|---|
| `lint` | Ruff finds a lint or format issue; hadolint flags the Dockerfile; Prometheus config or alert-rule tests fail; dashboard JSON is invalid |
| `test` | Any test fails, or coverage falls below 90% |
| `security-scan` | Trivy finds a secret, a HIGH/CRITICAL misconfiguration, or a fixable HIGH/CRITICAL dependency issue |
| `build` | The image doesn't build; Trivy finds a fixable HIGH/CRITICAL vulnerability in the image; the smoke test fails |
| `deploy` | The new version doesn't go live, or the live checks fail (it rolls back first, then fails) |

Each job shows its results on the run page: a test results table, a coverage table, the
Trivy findings, image tags and a release summary. Test and Trivy reports can be downloaded
as run artifacts.

## 3. Application architecture

```mermaid
flowchart LR
    client([HTTP client]) --> mw

    subgraph app [FastAPI application]
        mw["ObservabilityMiddleware<br/>request ID · timing · metrics · request log"]
        mw --> router["routers/tasks.py<br/>/api/v1/tasks"]
        mw --> sys["main.py<br/>/health · /metrics · /deployment-info"]
        router -->|validated by| schemas["schemas.py<br/>Pydantic models"]
        router --> crud["crud.py<br/>create · list · get · update · delete"]
        crud --> models["models.py<br/>Task table"]
        models --> database["database.py<br/>engine · sessions"]
        handler["503 handler<br/>database unavailable"]
    end

    database --> pg[(PostgreSQL)]
    database -.->|OperationalError| handler
```

| Module | Responsibility |
|---|---|
| `main.py` | Creates the app, startup (create tables, log version), `/health`, `/metrics`, the database-error handler |
| `routers/tasks.py` | The six task endpoints; returns 404 for missing tasks; counts task operations |
| `schemas.py` | Validation rules: lengths, allowed values, unknown fields rejected, nulls only where allowed |
| `crud.py` | All database reads and writes |
| `models.py` | The `tasks` table definition |
| `database.py` | Connection pool (with `pool_pre_ping`, so dead connections are replaced after a database restart) |
| `config.py` | Settings from environment variables; converts Render's `postgres://` URLs for SQLAlchemy |
| `observability.py` | Prometheus metrics and one log line per request |
| `logging_config.py` | Log format with UTC timestamps; INFO/WARNING to stdout, ERROR to stderr |
| `healthcheck.py` | Used by Docker `HEALTHCHECK`, because the slim image has no curl |

## 4. Docker architecture

```mermaid
flowchart TB
    subgraph host [Developer machine]
        p8000[":8000"]
        p3000[":3000"]
        p9090[":9090"]
    end

    subgraph compose [Docker Compose network: default]
        api["<b>api</b><br/>taskapi image<br/>UID 10001 · HEALTHCHECK /health"]
        db["<b>db</b><br/>postgres:17-alpine<br/>HEALTHCHECK pg_isready"]
        prometheus["<b>prometheus</b><br/>prom/prometheus:v3.16.0"]
        grafana["<b>grafana</b><br/>grafana/grafana:13.3.2"]
    end

    p8000 --> api
    p3000 --> grafana
    p9090 --> prometheus

    api -->|"db:5432 (waits until healthy)"| db
    prometheus -->|"api:8000/metrics every 5s"| api
    grafana -->|"prometheus:9090"| prometheus

    db --- v1[("volume: pgdata")]
    prometheus --- v2[("volume: prometheus-data")]
    grafana --- v3[("volume: grafana-data")]
```

**The API image** (`Dockerfile`), in build order:

1. `python:3.12-slim` (Debian 13)
2. `apt-get upgrade`, to apply Debian security fixes published since the base image was built
3. Create user `app`, UID/GID 10001
4. Install `requirements.txt`, then **remove pip** (not needed at runtime)
5. Copy `app/` only. Tests, scripts, docs and `.env` are excluded by `.dockerignore`.
6. `USER 10001:10001`, `HEALTHCHECK` every 30 seconds, run `uvicorn` on `$PORT` (Render sets it; 8000 by default)

`APP_VERSION` is a build argument, so each image reports its own release version.

**Volumes:** the database is stored in the named volume `pgdata`. Restarting or recreating
containers keeps the data; only `docker compose down -v` deletes it.

**Logging:** every container uses the `json-file` driver with rotation (10 MB × 3 files).

## 5. Database architecture

```mermaid
erDiagram
    TASKS {
        int id PK "auto-increment"
        varchar(200) title "NOT NULL"
        text description "nullable, max 1000 chars (API)"
        varchar(20) status "NOT NULL: todo | in_progress | done"
        varchar(20) priority "NOT NULL: low | medium | high"
        date due_date "nullable"
        timestamptz created_at "NOT NULL, set on insert (UTC)"
        timestamptz updated_at "NOT NULL, updated on every change (UTC)"
    }
```

| Topic | How it works |
|---|---|
| Access | SQLAlchemy 2.0 ORM with the psycopg 3 driver; one session per request, closed afterwards |
| Schema creation | Tables are created at startup if missing (`create_all`) |
| Enums | Stored as readable text (`in_progress`), with the allowed values enforced by the API |
| Connection URL | `DATABASE_URL`. Render's `postgres://…` form is converted to `postgresql+psycopg://…`. |
| Resilience | `pool_pre_ping` replaces broken connections; if the database is unreachable, endpoints return `503` and `/health` reports `unreachable` |
| Persistence | Local: Docker volume `pgdata`. Production: Render's managed PostgreSQL. |
| Environments | Local runs without Docker use SQLite; Compose, CI and Render use PostgreSQL 17 |

**Known limitation (and the rollback demo):** `create_all` creates missing tables, but it
never changes existing ones. A release that adds a column passes CI, because CI starts from an
empty database, but fails in production. The post-deployment checks catch exactly this, and
the [rollback demo](release-and-rollback.md#demo-a-failed-release-that-rolls-itself-back)
shows it happening. A migration tool such as Alembic would be the next step.

## 6. Monitoring and logging architecture

```mermaid
flowchart LR
    subgraph api [FastAPI app]
        mw[Middleware] -->|counters · histograms| reg[Prometheus registry]
        reg --> metrics["/metrics"]
        mw -->|one line per request| logs[Python logging]
    end

    metrics -->|"scrape: local 5s, Render 30s"| prom[Prometheus]
    prom -->|evaluate every 5s| rules["Alert rules<br/>API down · error rate > 5%<br/>DB unreachable · p95 > 500ms"]
    prom -->|PromQL| grafana["Grafana<br/>Task API - Overview"]

    logs -->|INFO / WARNING| stdout[stdout]
    logs -->|ERROR / CRITICAL| stderr[stderr]
    stdout & stderr --> docker["Docker json-file logs<br/>(rotated) / Render Logs tab"]
```

Details: [monitoring.md](monitoring.md).

## 7. Release and rollback flow

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant GH as GitHub Actions
    participant Reg as GHCR
    participant R as Render
    participant App as Live API

    Dev->>GH: git push origin v1.2.0
    GH->>GH: lint, tests, Trivy, build, image scan, smoke test
    GH->>Reg: push image :1.2.0
    GH->>GH: find last good release (deployment history) → v1.1.0
    GH->>R: deploy hook ?imgURL=…:1.2.0
    R->>App: start 1.2.0, switch traffic once /health = 200
    loop until version = 1.2.0 (max 15 min)
        GH->>App: GET /api/v1/deployment-info
    end
    GH->>App: /health, list tasks, create → read → delete a task
    alt all checks pass
        GH-->>Dev: ✅ v1.2.0 deployed and verified
    else a check fails
        GH->>R: deploy hook ?imgURL=…:1.1.0
        GH->>App: same checks against 1.1.0
        GH-->>Dev: ❌ v1.2.0 failed, ✅ rolled back to v1.1.0
    end
```

Setup and the demo script: [release-and-rollback.md](release-and-rollback.md).
