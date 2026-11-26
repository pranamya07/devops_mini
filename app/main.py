from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import APP_ENV, APP_NAME, APP_VERSION
from app.database import database_is_reachable, init_db
from app.routers import tasks


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    description="A task management REST API backed by PostgreSQL, with automated CI/CD.",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.include_router(tasks.router)


@app.get("/")
def read_root():
    return {
        "message": "FastAPI CI/CD project is running",
        "app_name": APP_NAME,
        "environment": APP_ENV,
        "docs": "/docs",
    }


@app.get("/health", responses={503: {"description": "Database unreachable"}})
def health_check():
    if database_is_reachable():
        return {"status": "healthy", "database": "connected"}
    return JSONResponse(
        status_code=503,
        content={"status": "unhealthy", "database": "unreachable"},
    )


@app.get("/api/v1/greet/{name}")
def greet(name: str):
    return {"message": f"Hello, {name}!"}


@app.get("/api/v1/deployment-info")
def deployment_info():
    return {
        "app_name": APP_NAME,
        "environment": APP_ENV,
        "version": app.version,
        "status": "running",
    }
