# Stage 1: Builder
# Use the official uv image for high-performance dependency resolution
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies separately to leverage Docker layer caching
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Stage 2: Runner
FROM python:3.12-slim-bookworm

# Combine system setup into a single layer for performance and size
# Includes: system deps (libgomp1 for XGB/LGBM), user creation, and directory scaffolding
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && groupadd -r f1user && useradd -r -g f1user f1user \
    && mkdir -p /app/data/raw /app/data/processed /app/data/outputs/models /app/reports /app/logs /app/cache \
    && chown -R f1user:f1user /app \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtual environment and code using --link for independent layer caching
# Note: --link requires BuildKit and allows layers to be reused even if previous ones change
COPY --from=builder --link /app/.venv /app/.venv
COPY --link src/ ./src/
COPY --link scripts/ ./scripts/
COPY --link pyproject.toml ./
COPY --link data/outputs/models/ ./data/outputs/models/

# Set environment variables
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src:${PYTHONPATH:-}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER f1user

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command to run the FastAPI server
CMD ["uvicorn", "f1_predictions.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
