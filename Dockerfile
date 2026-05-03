# Stage 1: Builder
# Use the official uv image for high-performance dependency resolution
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies separately to leverage Docker layer caching
# This only re-runs if pyproject.toml or uv.lock changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Stage 2: Runner
FROM python:3.12-slim-bookworm

# Install system dependencies required by LightGBM/XGBoost (OpenMP)
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security (DevOps best practice)
RUN groupadd -r f1user && useradd -r -g f1user f1user

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the source code and scripts
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY pyproject.toml ./

# Ensure the app can write to necessary directories
RUN mkdir -p data/raw data/processed data/outputs reports logs cache && \
    chown -R f1user:f1user /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:$PYTHONPATH" \
    PYTHONUNBUFFERED=1

USER f1user

# Default command (can be overridden by docker-compose or CLI)
CMD ["python", "scripts/predict_season.py", "--help"]
