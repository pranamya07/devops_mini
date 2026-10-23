
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Run the application as a non-root user.
RUN groupadd --system app \
    && useradd --system --gid app app

# Install production dependencies first for build caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code.
COPY app ./app

USER app

EXPOSE 8000

# Render supplies PORT; local runs default to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
