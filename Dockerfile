# Stage 1: Builder
# Use the official uv image for high-performance dependency resolution.
#
# This stage deliberately runs on the *build* platform ($BUILDPLATFORM) rather
# than the target one, so installing ~100 wheels is never emulated. uv is told
# which wheels to fetch with --python-platform, derived below from BuildKit's
# $TARGETPLATFORM, so the virtual environment still holds binaries for the
# architecture the runner image will use. Emulating this stage under QEMU (the
# previous behaviour) cost ~25x the time for an identical result: the arm64 leg
# took 528s against 21s for amd64.
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Supplied automatically by BuildKit; must be declared to be readable here.
ARG TARGETPLATFORM

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Map $TARGETPLATFORM onto uv's target triple. Only the platforms the workflow
# publishes are accepted, so an unexpected target fails the build loudly instead
# of silently baking an environment the runtime image cannot load.
RUN case "${TARGETPLATFORM}" in \
      linux/amd64) echo "x86_64-unknown-linux-gnu" ;; \
      linux/arm64) echo "aarch64-unknown-linux-gnu" ;; \
      *) echo "Unsupported TARGETPLATFORM: ${TARGETPLATFORM}" >&2; exit 1 ;; \
    esac > /uv-python-platform \
    && cat /uv-python-platform

# Install dependencies separately to leverage Docker layer caching
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev \
      --python-platform "$(cat /uv-python-platform)"

# Stage 2: Runner
FROM python:3.12-slim-bookworm

# Combine system setup into a single layer for performance and size
# Includes: system deps (libgomp1 for XGB/LGBM) and the runtime user.
# NOTE: directory scaffolding deliberately happens at the *end* of this stage --
# see the chown below for why.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    # Kaleido / Plotly static export dependencies (headless graphics)
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && groupadd -g 1001 f1user \
    && useradd -g 1001 -u 1001 -m -d /home/f1user f1user \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtual environment and code using --link for independent layer caching
# Note: --link requires BuildKit and allows layers to be reused even if previous ones change.
# --chown uses the numeric UID/GID because --link builds each layer independently of
# the rest of the graph, so a name created in an earlier layer cannot be resolved.
COPY --from=builder --link --chown=1001:1001 /app/.venv /app/.venv
COPY --link --chown=1001:1001 src/ ./src/
COPY --link --chown=1001:1001 scripts/ ./scripts/
COPY --link --chown=1001:1001 pyproject.toml ./
COPY --link --chown=1001:1001 data/outputs/models/ ./data/outputs/models/

# Scaffold the directories the application writes to, and hand /app to the runtime
# user, AFTER every COPY has landed.
#
# This ordering is load-bearing. COPY layers materialise their destination
# directories as root, so an earlier `chown -R` gets overwritten: /app ended up
# root-owned, `Settings.resolve_and_mkdir()` could not create /app/.cache, and the
# container died on startup with PermissionError before uvicorn ever bound a port.
# The image was published on every push to master without anything ever running it,
# which is why the workflow now smoke-tests what it publishes.
RUN mkdir -p /app/.cache/fastf1 /app/data/raw /app/data/processed \
             /app/data/external /app/reports /app/logs /app/cache /app/models/artifacts \
    && chown 1001:1001 /app \
    && chown -R 1001:1001 /app/data /app/.cache /app/reports /app/logs /app/cache /app/models

# Set environment variables
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR="/app/.cache/matplotlib"

USER f1user

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command to run the FastAPI server
CMD ["uvicorn", "f1_predictions.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
