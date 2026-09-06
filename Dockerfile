# syntax=docker/dockerfile:1

# wallcal renders wallpapers from a URL and keeps nothing: no database, no
# volumes, no secrets, no writable state. That shapes every choice below --
# the runtime filesystem can stay entirely root-owned and read-only to the
# process, and there is no host ownership to reconcile via PUID/PGID.

# ---------------------------------------------------------------------------
# Stage 1: build the runtime environment
# ---------------------------------------------------------------------------
# 3.12 explicitly, matching requires-python = ">=3.12" in pyproject.toml.
# Same base in both stages so the venv's absolute paths and shebangs stay valid.
FROM python:3.12-slim-bookworm AS builder

# uv is pinned: an unpinned build tool is a reproducibility hole in a stage
# whose whole purpose is a reproducible install.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, without the project, so editing src/ does not invalidate
# the layer that took the network.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --no-editable

# README.md is read by hatchling when it builds the wallcal wheel.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="wallcal" \
      org.opencontainers.image.description="Self-hosted calendar wallpapers rendered on demand from a URL" \
      org.opencontainers.image.source="https://github.com/CosmDandy/wallcal" \
      org.opencontainers.image.url="https://github.com/CosmDandy/wallcal" \
      org.opencontainers.image.documentation="https://github.com/CosmDandy/wallcal/blob/master/docs/docker.md" \
      org.opencontainers.image.licenses="MIT"

# Defaults only. No hostname, no domain, no reverse-proxy path is baked in:
# the service never builds an absolute URL, and the operator maps the port.
# MALLOC_ARENA_MAX: rendering allocates a whole image per request across a
# thread pool, and glibc gives each thread its own arena it never gives back.
# Capped at two, a burst of requests reuses memory instead of settling at a
# high-water mark the container is then judged by.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    WALLCAL_HOST=0.0.0.0 \
    WALLCAL_PORT=8000 \
    WALLCAL_TZ=UTC

# A fixed system UID, high enough not to collide with a host account.
RUN groupadd --system --gid 10001 wallcal \
 && useradd --system --uid 10001 --gid 10001 --no-create-home \
            --home-dir /nonexistent --shell /usr/sbin/nologin wallcal

# Deliberately not --chown: the venv stays root-owned and world-readable, so
# the service can read its own code but cannot rewrite it.
COPY --from=builder /app/.venv /app/.venv

WORKDIR /app
USER 10001:10001

# Documentation of the default only -- publishing the port is the operator's job.
EXPOSE 8000

# No curl and no wget in this image, and adding one to poll a local socket is
# not worth a package. Python is already PID 1's interpreter.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('WALLCAL_PORT','8000')+'/healthz', timeout=3).status==200 else 1)"]

# uvicorn installs its own SIGTERM handler, so PID 1 stops cleanly without an init.
ENTRYPOINT ["wallcal"]
