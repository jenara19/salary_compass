# Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Multi-stage build for SalaryCompass (Streamlit + Python 3.14).
#
# Build:  docker build -t salary-compass .
# Run:    docker run -p 8501:8501 salary-compass
# Dev:    docker run -p 8501:8501 -v $(pwd):/app salary-compass
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Install dependencies ────────────────────────────────────────────
FROM python:3.14-slim-bookworm AS builder

# Inject uv from the official image — no curl / apt required
COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /uvx /bin/

# Build-time optimisations
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Copy lock + manifest first — Docker cache layer only invalidates
# when these files change, not when source code changes.
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev group)
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.14-slim-bookworm

# Copy the pre-built virtualenv from builder (no uv, no build tools in runtime)
COPY --from=builder /app/.venv /app/.venv

# Put .venv on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

# Copy application source
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8501

# Streamlit health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["python", "-m", "streamlit", "run", "app.py", \
            "--server.port=8501", \
            "--server.address=0.0.0.0", \
            "--server.headless=true"]
