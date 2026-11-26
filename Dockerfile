FROM python:3.12-slim

# CI passes the release version (e.g. 1.1.0) so /api/v1/deployment-info reports it.
ARG APP_VERSION=1.0.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

# Apply Debian security fixes released after the base image was published
# (keeps the Trivy scan clean between official python image rebuilds).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Run the application as a non-root user with a fixed numeric ID,
# so platforms can verify the container never runs as root.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

# Install production dependencies first for build caching.
COPY requirements.txt .
# Remove pip once dependencies are installed: the running app never needs it, and
# Trivy flagged CVEs in the pip copy (and its vendored setuptools) in the base image.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall --yes pip

# Copy application source code.
COPY app ./app

USER 10001:10001

EXPOSE 8000

# Docker marks the container unhealthy if /health stops returning 200.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --start-interval=3s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]

# Render supplies PORT; local runs default to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
