# FastAPI CI/CD DevOps Project

## 1. Project Overview

This project demonstrates how to build, test, containerize, and deploy a REST API using FastAPI and DevOps practices.

The project uses automated testing and a GitHub Actions CI/CD pipeline. Docker is used to package the application, and Render hosts the deployed API.

## 2. Technologies Used

- **Python** — application programming language
- **FastAPI** — REST API framework
- **Uvicorn** — ASGI server
- **pytest** — automated testing
- **Docker** — application containerization
- **GitHub Actions** — continuous integration and deployment automation
- **Render** — application hosting

## 3. Prerequisites

Install the following tools before running the project locally:

- Python 3.12
- Git
- Docker Desktop (required for local Docker commands)
- Visual Studio Code (optional)

## 4. Installation and Setup

Clone the repository:

```bash
git clone https://github.com/pranamya07/devops_mini.git
cd devops_mini
```

Create and activate a virtual environment if desired.

On Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

Install the development dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Run the API locally:

```bash
uvicorn app.main:app --reload
```

Open the following URLs in your browser:

- API root: http://127.0.0.1:8000/
- Interactive API documentation: http://127.0.0.1:8000/docs

## 5. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Returns basic project information |
| GET | `/health` | Reports the application's health status |
| GET | `/api/v1/greet/{name}` | Returns a greeting for the supplied name |
| GET | `/api/v1/deployment-info` | Returns application name, environment, version, and running status |

The deployment-info endpoint should be available in the deployed application after the corresponding changes have been merged into the deployment branch and deployed successfully.

## 6. Automated Testing

Run the test suite from the repository root:

```bash
pytest -v
```

The tests verify the API's expected responses. Run the tests before submitting code changes.

## 7. Docker

Build the Docker image from the repository root:

```bash
docker build -t fastapi-cicd-devops .
```

Run the container:

```bash
docker run -p 8000:8000 fastapi-cicd-devops
```

If the Dockerfile uses a different internal port or startup command, adjust the run instructions to match the actual Dockerfile.

## 8. CI/CD Pipeline

The GitHub Actions workflow is defined in `.github/workflows/ci-cd.yml`.

The pipeline:

1. Checks out the repository.
2. Sets up Python.
3. Installs development dependencies.
4. Runs automated tests.
5. Builds a Docker image.
6. Triggers a Render deployment when the workflow's deployment conditions are satisfied.

The workflow runs on the configured branches and pull requests. Deployment is restricted to pushes to `main` after the test-and-build job succeeds.

## 9. Deployment

The application is hosted on Render.

- **Live API:** https://devops-mini-sxph.onrender.com
- **Swagger documentation:** https://devops-mini-sxph.onrender.com/docs

The GitHub Actions workflow triggers deployment using a Render deploy hook stored in GitHub repository secrets. Secret values must not be committed to the repository or included in this documentation.

A change merged into `dev` does not automatically mean that it is live on Render. Changes must reach `main`, and the deployment workflow must complete successfully.

## 10. Project Structure

```text
devops_mini/
├── app/
│   ├── main.py
│   └── config.py
├── tests/
├── .github/
│   └── workflows/
│       └── ci-cd.yml
├── Dockerfile
├── requirements-dev.txt
└── README.md
```

Verify the actual repository structure before treating this tree as exhaustive.