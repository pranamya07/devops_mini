# Evidence checklist for the project report

What to capture, where to find it, and when. Save screenshots in a shared folder
named as in the first column, so the report can refer to them.

## Diagrams

All diagrams are in [architecture.md](architecture.md) and render directly on GitHub.
For a Word or PDF report, paste a diagram's code block into https://mermaid.live and
download it as PNG or SVG.

- [ ] `01-system-architecture.png`: section 1
- [ ] `02-cicd-pipeline.png`: section 2
- [ ] `03-docker-architecture.png`: section 4
- [ ] `04-database-er-diagram.png`: section 5
- [ ] `05-monitoring-architecture.png`: section 6
- [ ] `06-release-rollback-sequence.png`: section 7

## Application and Docker

- [ ] `10-swagger-docs.png`: http://localhost:8000/docs (or the live URL + `/docs`) with the task endpoints
- [ ] `11-compose-healthy.png`: terminal, `docker compose ps`, all 4 containers `(healthy)`
- [ ] `12-data-persistence.png`: terminal, create a task → `docker compose restart api db` → `curl localhost:8000/api/v1/tasks` still shows it
- [ ] `13-non-root.png`: terminal, `docker compose exec api id` shows `uid=10001`

## Testing

- [ ] `20-pytest-local.png`: terminal, `pytest`: 158 passed, coverage table, "Required test coverage of 90% reached"
- [ ] `21-ci-test-summary.png`: Actions run → summary → **Test results** and **Coverage** tables
- [ ] `22-ci-test-artifacts.png`: the same run → **Artifacts** → `test-reports` (and the HTML coverage report opened)
- [ ] `23-ci-blocks-failing-test.png`: a PR with a deliberately broken test showing the red ❌ check (see [testing.md](testing.md#showing-that-ci-blocks-broken-code))
- [ ] `24-smoke-test.png`: the **Smoke test image with Docker Compose** step log, or `./scripts/smoke_test.sh` locally

## CI/CD and security

- [ ] `30-pipeline-graph.png`: Actions run graph for a release tag: lint, tests and security-scan → build → deploy, all green
- [ ] `31-trivy-image-scan.png`: build job → **Trivy image scan** step showing the result table
- [ ] `32-security-tab.png`: repo **Security** → **Code scanning** with the Trivy results
- [ ] `33-ghcr-versions.png`: GitHub → **Packages** → `devops_mini`, showing tags `1.0.0`, `1.1.0`, `1.2.0`, `latest`
- [ ] `34-github-secrets.png`: **Settings** → **Secrets and variables** → **Actions**, showing `RENDER_DEPLOY_HOOK_URL` exists (values are hidden)

## Deployment and rollback (the live demo)

- [ ] `40-release-success.png`: run summary for `v1.1.0`: "✅ v1.1.0 deployed and verified"
- [ ] `41-deployment-info-1.1.0.png`: browser, `<live URL>/api/v1/deployment-info` showing `"version": "1.1.0"`, `"environment": "production"`
- [ ] `42-release-failed-rollback.png`: run summary for `v1.2.0`: "❌ failed its post-deployment checks" and "✅ rolled back to v1.1.0"
- [ ] `43-post-deploy-check-log.png`: the **Post-deployment health check** step log showing `✗ GET /api/v1/tasks returns 200 (HTTP 500)`
- [ ] `44-render-events.png`: Render → service → **Events**, showing the deploys of 1.1.0 → 1.2.0 → 1.1.0
- [ ] `45-render-logs.png`: Render → **Logs**, showing `column tasks.archived does not exist` during v1.2.0
- [ ] `46-github-deployments.png`: repo → **Deployments** → `production` history
- [ ] `47-deployment-info-after-rollback.png`: `/api/v1/deployment-info` back on `1.1.0`, with earlier tasks still listed

## Monitoring and logging

- [ ] `50-grafana-normal.png`: Grafana dashboard with `generate_traffic.py` running, 0% errors
- [ ] `51-grafana-db-outage.png`: the same dashboard after `docker compose stop db`, with the error-rate spike
- [ ] `52-prometheus-alerts.png`: http://localhost:9090/alerts with `TaskApiDatabaseUnreachable` and `TaskApiHighErrorRate` **firing**
- [ ] `53-prometheus-targets.png`: http://localhost:9090/targets with `task-api` (and `task-api-render`) **UP**
- [ ] `54-grafana-version-rollback.png`: with the Render target added, the **Running version** panel during the rollback demo
- [ ] `55-logs.png`: terminal, `docker compose logs api`, showing timestamps, levels and request IDs
- [ ] `56-error-logs.png`: terminal, `docker logs "$(docker compose ps -q api)" 2>&1 >/dev/null` during the outage (errors only)
