# Security

| Area | Control |
|---|---|
| Vulnerability scanning | Trivy scans the code and every Docker image; fixable HIGH/CRITICAL findings fail the pipeline |
| Secrets | No secrets in the repo; deployment credentials live in GitHub Secrets; Trivy scans for leaked secrets |
| Container | Non-root user (UID 10001), slim base, OS security patches applied at build time, no pip in the final image |
| Code | Ruff security rules (Bandit), strict input validation, safe request IDs, no stack traces returned to users |
| Pipeline | Least-privilege permissions per job, PRs never publish images, scanners run from pinned container images |

## Trivy vulnerability scanning

Two Trivy scans run in CI ([ci-cd.yml](../.github/workflows/ci-cd.yml)):

| Scan | Job | Looks at | Fails the pipeline on |
|---|---|---|---|
| Filesystem | `security-scan` | The repository: leaked secrets, Dockerfile misconfigurations, pinned dependencies | Any secret; HIGH/CRITICAL misconfiguration; fixable HIGH/CRITICAL vulnerability |
| Image | `build` | The built image: Debian packages and installed Python packages | A HIGH or CRITICAL vulnerability that has a fix available |

The image is scanned **before** it's pushed, so a vulnerable image never reaches GHCR or Render.

Trivy's results appear in three places:
- **Run page:** a table of any blocking findings.
- **Artifact `trivy-reports`:** the full report at every severity, as a table and as SARIF.
- **Security tab:** **Code scanning** shows the findings, uploaded as SARIF.

### Latest image scan

Trivy 0.76.2, 26 Nov 2026, image built from this branch:

| Target | Findings | With a fix available | Blocking |
|---|---|---|---|
| Python packages | 0 | 0 | none |
| Debian 13.8 system packages | 222 (53 HIGH, 79 MEDIUM, 77 LOW, 13 UNKNOWN) | 0 | none |
| Secrets in the image | 0 | | none |
| Repository scan (secrets, Dockerfile) | 0 | | none |

**Why 222 Debian findings don't block a release:** none of them has a fix available yet.
Trivy reports them because a CVE exists, but there's no patched package to install. The
pipeline blocks every fixable HIGH/CRITICAL issue, and the Dockerfile runs `apt-get upgrade`,
so each fix is picked up in the next build as soon as Debian releases it. This is the usual
policy (`--ignore-unfixed`); blocking on unfixable issues would block every release while
making nothing safer.

### Issues the scans found and we fixed

| Finding | Fix |
|---|---|
| 4 HIGH CVEs in Debian packages (`apt`, `zlib`, `zstd`) with fixes available | Latest base image, plus `apt-get upgrade` during the build |
| 6 CVEs in the `pip` bundled with `python:3.12-slim` | pip is removed from the final image |
| HIGH CVE-2025-47273 in setuptools bundled inside newer pip | Gone with pip |
| hadolint DL3066: user set by name | Fixed numeric UID/GID 10001 |

## Secrets

- **Nothing secret is committed.** `.env` is ignored by git, and `.env.example` contains only placeholders.
- **Compose refuses to start without a password.** `POSTGRES_PASSWORD` must be set in `.env`.
- **Production credentials live on GitHub and Render:**

  | Name | Type | Purpose |
  |---|---|---|
  | `RENDER_DEPLOY_HOOK_URL` | GitHub **secret** | Triggers Render deploys. It acts as a password, so GitHub masks it in logs. |
  | `RENDER_SERVICE_URL` | GitHub **variable** | Public URL of the live API (not secret) |
  | `GITHUB_TOKEN` | Automatic, per run | Pushes images to GHCR; expires when the run ends |
  | `DATABASE_URL` (Render) | Render environment variable | Linked from the Render database, never stored in git |

- **Passwords stay out of logs.** At startup the app logs the database URL as `postgresql+psycopg://taskapi:***@db:5432/taskapi`.
- **Trivy checks every push for leaked secrets** (`--scanners secret`).

## Container hardening

| Control | Detail |
|---|---|
| Non-root | Runs as UID/GID 10001 (`USER 10001:10001`); the smoke test fails if it's ever 0 |
| Small attack surface | `python:3.12-slim` base, no compilers, no pip, only `app/` copied in (`.dockerignore`) |
| Patched | `apt-get upgrade` at build time; CI pulls the newest base image on every build |
| Health check | Docker `HEALTHCHECK` on `/health`; Render's health check uses the same endpoint |
| Linted | hadolint passes with no warnings |

## Application security

- **Input validation:** unknown fields are rejected; titles are 1–200 characters and descriptions at
  most 1000; status and priority only accept allowed values; IDs must be positive integers.
- **Safe error responses:** a database outage returns `503` with a generic message, and
  unexpected errors return a plain `500`. Details and tracebacks go to the error log only.
- **Request IDs:** an incoming `X-Request-ID` is only reused if it's short and contains safe
  characters, which stops log injection. Otherwise a new ID is generated.
- **Static analysis:** Ruff runs the Bandit security rules (`S`) on all code.

## Pipeline security

- **Least privilege:** the workflow defaults to `contents: read`. Only the `build` job may write
  packages and security events, and only `deploy` may read deployments.
- **Pull requests:** images are built and scanned but never pushed. SARIF uploads are skipped
  for PRs from forks.
- **Trivy and hadolint run from version-pinned container images**, not third-party actions.
  The `trivy-action` wrapper had a script-injection advisory in February 2026.
- **One deployment at a time:** `concurrency: deploy-production`, never cancelled halfway.

## Known limitations

| Limitation | Why it's acceptable here / next step |
|---|---|
| The API has no authentication | Demo project; the next step would be API keys or OAuth2 |
| `/metrics` is public on Render | It contains no personal data; a bearer token could protect it |
| Grafana allows anonymous viewing | Local Compose only, not deployed |
| 222 unfixed Debian CVEs | No fixes exist yet; a distroless base image would shrink this further |
