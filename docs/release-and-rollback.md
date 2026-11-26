# Releases, deployment and rollback

Production runs on Render. Every release is a Docker image that CI has already
tested, scanned and pushed to GitHub Container Registry (GHCR). After deploying,
CI checks the live site, and if the checks fail it puts the last good version
back automatically.

```
git tag v1.2.0 && git push origin v1.2.0
        │
        ▼
lint + tests + Trivy ──> build image ──> scan ──> push ghcr.io/pranamya07/devops_mini:1.2.0
                                                          │
                                                          ▼
                                     Render deploys exactly :1.2.0 (deploy hook)
                                                          │
                                                          ▼
                                     post-deployment checks on the live URL
                                        │                         │
                                     pass ✅                    fail ❌
                                  v1.2.0 stays live      deploy last good version
                                                          (e.g. :1.1.0) and verify it
```

## One-time setup

Steps 2, 4, 5 and 6 need the repository owner. Steps 3 and 4 need access to the Render account.

1. **Merge to `main`.** Every push to `main` publishes `ghcr.io/pranamya07/devops_mini:main`.
   Render needs this image in step 3.

2. **Make the image public.** GitHub > your profile > **Packages** > `devops_mini` >
   **Package settings** > **Change visibility** > **Public**.
   Render can then pull it without registry credentials.

3. **Create the Render service and database.** The old service builds from the repo, and
   Render can't switch an existing service to a prebuilt image, so delete or rename it first. Then either:
   - **Blueprint (recommended):** Render > **New** > **Blueprint** > pick this repo, branch `main`.
     `render.yaml` creates the PostgreSQL database and the web service, and links them.
   - **By hand:**
     1. **New** > **Postgres** (free).
     2. **New** > **Web Service** > **Existing image** > `ghcr.io/pranamya07/devops_mini:main`.
     3. Health check path `/health`.
     4. Environment: `APP_ENV=production`, plus `DATABASE_URL` set to the database's
        *Internal Database URL*.

   Don't set `APP_VERSION` on Render. Each image already carries its own version.
   Free Render databases are deleted 30 days after creation, so create this one
   less than 30 days before the final demo.

4. **Save the deploy hook in GitHub.** Render service > **Settings** > **Deploy Hook** > copy.
   GitHub repo > **Settings** > **Secrets and variables** > **Actions** > **Secrets** >
   set `RENDER_DEPLOY_HOOK_URL` to that URL. Treat it like a password.

5. **Save the live URL in GitHub.** Same page > **Variables** > **New repository variable**:
   `RENDER_SERVICE_URL` = `https://<your-service>.onrender.com` (no trailing slash).

6. **Set the default branch to `main`.** **Settings** > **General** > **Default branch**.
   GitHub only shows the manual **Rollback Production** button for workflows on the default branch.

7. **First release:**
   ```bash
   git switch main && git pull
   git tag v1.0.0
   git push origin v1.0.0
   ```

## Releasing a version

```bash
git switch main && git pull
git tag v1.1.0
git push origin v1.1.0
```

Watch it under **Actions**. The **Deploy to Render and Verify** job:

1. Finds the rollback target: the last release that deployed and passed its checks,
   taken from GitHub's deployment history. A release that failed is never a rollback target.
2. Asks Render to deploy exactly `ghcr.io/pranamya07/devops_mini:1.1.0`.
3. Runs `scripts/verify_deployment.py` against the live URL. It:
   - waits (up to 15 minutes) until `/api/v1/deployment-info` reports `1.1.0`
   - checks `/health` returns 200 and the database is connected
   - lists tasks, creates a test task, reads it back and deletes it again
   - checks `/health` a few more times, in case the app crashes soon after starting
4. If any check fails, deploys the rollback target and runs the same checks on it.
5. Writes a summary on the run page: the result, any rollback, the image and the URL.

Each run also appears under the repo's **Deployments** (environment `production`).

Pushes to `main` and `dev` build, scan and publish images but don't deploy.
Only version tags reach production.

## Rolling back by hand

- **GitHub:** **Actions** > **Rollback Production** > **Run workflow** > enter a version such as `1.1.0`.
  It deploys that image and runs the same post-deployment checks.
- **Render:** service > **Events** > pick an earlier deploy > **Rollback**.
  It's quick, but it skips the checks.

## Demo: a failed release that rolls itself back

Before the demo, v1.0.0 and v1.1.0 should already be released and live.

**v1.2.0 is the planned failure:** a change that passes every test in CI but breaks in production.
It adds a column to the `Task` model with no database migration:

```python
# app/models.py
from sqlalchemy import Boolean, Date, DateTime, Enum, String, Text
...
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

- **In CI:** tests start from an empty database, which gets the new column, so all tests pass ✅.
- **In production:** the `tasks` table already exists without that column. `/health` still
  returns 200, so Render switches traffic to v1.2.0, but listing or creating tasks fails with
  `column tasks.archived does not exist` (HTTP 500).

Demo steps:

1. Commit the change on `main`, then `git tag v1.2.0 && git push origin v1.2.0`.
2. **Actions:** lint ✅, tests ✅, Trivy ✅, build and push ✅, deploy:
   - post-deployment check ❌ (`GET /api/v1/tasks returns 200 (HTTP 500)`)
   - **Roll back to last good version** ✅ (v1.1.0)
   - The summary reads "❌ v1.2.0 failed its post-deployment checks / ✅ rolled back to v1.1.0".
3. **Live site:** `/api/v1/deployment-info` shows `1.1.0` again, and existing tasks are still there.
4. **Grafana** (after adding the Render URL to `monitoring/prometheus/targets/render.yml`):
   the *Running version* panel goes 1.1.0 → 1.2.0 → 1.1.0, with a spike in *Error rate*.
5. Clean up: `git revert` the change on `main` and release `v1.2.1`.

Each Render deploy takes a few minutes on the free plan, so the whole demo takes about
10 minutes. Rehearse it beforehand, and record a screen capture as a backup.

### Rehearsing locally

The same check runs against Docker Compose. Build the good and bad versions as
`taskapi:1.1.0` and `taskapi:1.2.0`, then:

```bash
API_IMAGE=taskapi:1.1.0 docker compose up -d --no-build --wait api
python3 scripts/verify_deployment.py --base-url http://localhost:8000 --expected-version 1.1.0   # passes

API_IMAGE=taskapi:1.2.0 docker compose up -d --no-build --wait api
python3 scripts/verify_deployment.py --base-url http://localhost:8000 --expected-version 1.2.0   # fails

API_IMAGE=taskapi:1.1.0 docker compose up -d --no-build --wait api   # roll back
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Add the RENDER_DEPLOY_HOOK_URL repository secret` | Setup steps 4 and 5 |
| Render answers 400 to the deploy hook | The service's image must be `ghcr.io/pranamya07/devops_mini` (any tag). Render rejects other repositories. |
| Render can't pull the image / `not found in GHCR` | Package isn't public (step 2), or that version was never released |
| Check waits, then times out on the old version | The new version failed Render's own health check, so Render kept the old one. Check Render > **Logs** for a startup crash. |
| First request takes about a minute | Free instances sleep after 15 idle minutes. The check waits for them. |
