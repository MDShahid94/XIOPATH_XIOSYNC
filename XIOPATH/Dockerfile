# ==================================================
# XIOPATH — Production Dockerfile (Phase P.1)
# ==================================================
# Multi-stage build: builder → api | worker
# Security: non-root user, read-only FS, no new privileges
# ==================================================
# Usage:
#   docker compose build
#   docker compose up -d
#   docker compose exec api python -m pytest tests/ -v
# ==================================================

# ── Stage 1: Builder (install deps, compile wheels) ──────────────────
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime base (minimal image) ────────────────────────────
FROM python:3.13-slim AS base

# Only runtime libs — no compilers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Copy project source
COPY core/ ./core/
COPY api/ ./api/
COPY plugins/ ./plugins/
COPY llm_worker/ ./llm_worker/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY main.py .
COPY requirements.txt .

# Copy initialization script
COPY start.sh .

# Ensure data directory exists
RUN mkdir -p /app/data /app/data/vector_db /app/data/exports /app/data/dlq

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1001 appuser \
    && chown -R appuser:appuser /app/data && chown appuser:appuser start.sh

# Labels
LABEL org.opencontainers.image.source="https://github.com/XIOPATH/core"
LABEL org.opencontainers.image.description="XIOPATH Control Plane (v5.0)"

EXPOSE 8000
USER appuser

# Use tini and our startup script
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./start.sh"]


# ── Target: API Server ───────────────────────────────────────────────
FROM base AS api

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1


# ── Target: LLM Worker ──────────────────────────────────────────────
FROM base AS worker

USER appuser
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "llm_worker.main"]
