
from fastapi import FastAPI

from app.config import APP_ENV, APP_NAME

app = FastAPI(
    title=APP_NAME,
    description="A Dockerized API with automated CI/CD.",
    version="1.0.0",
)


@app.get("/")
def read_root():
    return {
        "message": "FastAPI CI/CD project is running",
        "app_name": APP_NAME,
        "environment": APP_ENV,
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/v1/greet/{name}")
def greet(name: str):
    return {"message": f"Hello, {name}!"}
