import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import APP_ENV, APP_NAME, APP_VERSION, LOG_LEVEL
from app.database import database_is_reachable, engine, init_db
from app.logging_config import setup_logging
from app.observability import ObservabilityMiddleware, metrics_response, record_app_info
from app.routers import tasks

setup_logging(LOG_LEVEL)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Starting %s version=%s environment=%s database=%s",
        APP_NAME,
        APP_VERSION,
        APP_ENV,
        engine.url.render_as_string(hide_password=True),
    )
    init_db()
    record_app_info(APP_NAME, APP_VERSION, APP_ENV)
    logger.info("Startup complete, database tables ready")
    yield
    logger.info("Shutting down %s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    description="A task management REST API backed by PostgreSQL, with automated CI/CD.",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(ObservabilityMiddleware)
app.include_router(tasks.router)


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError):
    """Answer 503 instead of crashing with 500 when PostgreSQL is down."""
    logger.error(
        "Database error on %s %s: %s",
        request.method,
        request.url.path,
        type(exc.orig or exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable, please try again shortly"},
    )


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


@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus scrape endpoint."""
    return metrics_response()


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
