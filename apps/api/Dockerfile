# syntax=docker/dockerfile:1.7
# ==============================================================================
# ALBA ONE — Hardened Multi-Stage API & Worker Dockerfile (`apps/api/Dockerfile`)
# - Multi-stage (`builder` -> `runtime` -> targets `api` and `worker`)
# - Base images pinned by digest (see `docs/RUNBOOK_DEPLOY.md` for refresh steps)
# - Numeric non-root `USER 10001:10001`, fixed `HOME=/home/alba`, `PYTHONDONTWRITEBYTECODE=1`
# - Package managers (`apt`, `dpkg`, `pip`) removed from final stage
# - Compatible with `read_only: true` root filesystem (`/tmp` mounted as tmpfs/emptyDir)
# ==============================================================================
ARG UV_BASE_IMAGE=ghcr.io/astral-sh/uv:0.4.20-python3.12-bookworm-slim@sha256:5271df9a2be4bf27f5bc1eebaa91e2dc26a9c6fb89d0c1c05f1fd450200b776c
ARG PYTHON_RUNTIME_IMAGE=python:3.12.7-slim-bookworm@sha256:9c8d94d78f907a9c85662d13d92298a196a35e9d91a5d9a16f71b7c3481a928f

FROM ${UV_BASE_IMAGE} AS builder
WORKDIR /build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml /build/pyproject.toml
COPY apps/api/pyproject.toml /build/apps/api/pyproject.toml
COPY apps/api/src /build/apps/api/src

# Optional BuildKit secret mount for private package indexes (never passed via ARG/ENV)
RUN --mount=type=secret,id=pip_index_url,required=false \
    uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-cache "/build/apps/api"

FROM ${PYTHON_RUNTIME_IMAGE} AS runtime
ARG APP_VERSION=1.0.0
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="alba-one-api" \
      org.opencontainers.image.vendor="ALBACONNECT Inc." \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.source="https://github.com/albaconnect/alba-one"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/alba \
    PATH="/opt/venv/bin:${PATH}" \
    TZ=Asia/Tokyo \
    TMPDIR=/tmp

# Create numeric non-root user 10001:10001 and remove package managers from final image
RUN groupadd --gid 10001 alba && \
    useradd --uid 10001 --gid 10001 --create-home --home-dir /home/alba --shell /usr/sbin/nologin alba && \
    mkdir -p /app && \
    chown -R 10001:10001 /app /home/alba && \
    rm -rf /var/lib/apt/lists/* /usr/bin/apt* /usr/bin/dpkg* /opt/venv/bin/pip*

WORKDIR /app
COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --chown=10001:10001 apps/api/src /app/apps/api/src
COPY --chown=10001:10001 apps/api/alembic /app/apps/api/alembic
COPY --chown=10001:10001 config /app/config
COPY --chown=10001:10001 i18n /app/i18n
COPY --chown=10001:10001 prompts /app/prompts

USER 10001:10001

FROM runtime AS api
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/opt/venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]
ENTRYPOINT ["/opt/venv/bin/uvicorn", "alba_one.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]

FROM runtime AS worker
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/opt/venv/bin/python", "-c", "from alba_one.core.startup_checks import enforce_startup_checks; import os; enforce_startup_checks(dict(os.environ))"]
ENTRYPOINT ["/opt/venv/bin/python", "-m", "alba_one.agents.hitl.outbox"]
