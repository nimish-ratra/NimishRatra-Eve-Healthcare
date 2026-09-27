# ==============================================================================
# Multi-stage Dockerfile for EVE Healthcare Backend Monolith
# Base image: Python 3.12-slim Debian
# ==============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install minimal OS dependencies for Postgres client and curl healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application source code
COPY . .

# Create non-root user for security best practices
RUN useradd -u 1000 -U -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Container liveness check hitting /health/live/
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live/ || exit 1

# Default command: apply migrations and boot Django development server
CMD ["sh", "-c", "python manage.py migrate && python manage.py seed_demo_data && python manage.py runserver 0.0.0.0:8000"]
