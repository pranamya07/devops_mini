
# FastAPI CI/CD DevOps Project

A Dockerized FastAPI application with automated testing,
Docker build validation, and continuous deployment through
GitHub Actions and Render.

## Features

- REST API built with FastAPI
- Automated tests using pytest
- Dockerized application
- Docker Compose for local execution
- GitHub Actions CI/CD workflow
- Deployment to Render
- Environment-based configuration
- Health-check endpoint
- Swagger API documentation

## Architecture

Developer
  -> GitHub push or pull request
  -> GitHub Actions
  -> Install dependencies
  -> Run pytest
  -> Build Docker image
  -> On successful push to main, trigger Render
  -> Render builds and deploys the application
  -> Health-check verification

## Project Structure

- app/: Application source code
- tests/: Automated tests
- .github/workflows/: CI/CD configuration
- Dockerfile: Docker image instructions
- compose.yaml: Local container configuration
- render.yaml: Render service configuration

## Prerequisites

- Python 3.12
- Git
- Docker Desktop or Docker Engine
- GitHub account
- Render account

## Run Locally

Create and activate a virtual environment.

Windows PowerShell:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1

macOS/Linux:

    python3.12 -m venv .venv
    source .venv/bin/activate

Install dependencies:

    pip install -r requirements-dev.txt

Create a local environment file by copying
.env.example to .env.

Run tests:

    pytest -v

Run the API:

    uvicorn app.main:app --reload

Open http://127.0.0.1:8000/docs

## Run With Docker Compose

Create .env from .env.example, then run:

    docker compose up --build -d

Inspect logs:

    docker compose logs -f api

Stop the application:

    docker compose down

## API Endpoints

- GET /
- GET /health
- GET /api/v1/greet/{name}
- GET /docs

## CI/CD Workflow

Pull requests and pushes to main trigger automated tests
and Docker build validation.

Successful pushes to main trigger the Render deployment
hook after the test-and-build job succeeds.

Configure the repository secret RENDER_DEPLOY_HOOK_URL
before enabling production deployment.

## Environment Variables

- APP_NAME: Application display name
- APP_ENV: Current environment

Local values belong in .env. Production values are
configured through the hosting platform.

## Troubleshooting

1. If tests fail, inspect the pytest assertion and traceback.
2. If Docker fails, inspect the build output.
3. If the container exits, inspect docker compose logs.
4. If the deployment job fails, check the GitHub Actions
   logs and verify the deployment-hook secret.
5. If the service is unavailable, inspect Render deployment
   logs and verify GET /health.

## Future Improvements

- Publish versioned images to GitHub Container Registry
- Add PostgreSQL and database migrations
- Add Prometheus and Grafana monitoring
- Add container vulnerability scanning
- Add deployment notifications and rollback procedures

- ## Test line
- CI verification test for the dev branch.
