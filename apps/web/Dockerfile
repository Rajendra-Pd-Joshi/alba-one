# syntax=docker/dockerfile:1.7
# ==============================================================================
# ALBA ONE — Hardened Multi-Stage Next.js 15 Dockerfile (`apps/web/Dockerfile`)
# - Uses Next.js `output: "standalone"` (per Next.js 15 docs, runtime writes ONLY
#   to `/app/.next/cache` for ISR/image cache and `/tmp`; both are mounted as
#   tmpfs / emptyDir when running with `read_only: true` root filesystem)
# - Enforces build-time `assert-no-mocks-in-prod.mjs` and startup `check-startup.mjs`
# - Base image pinned by digest; numeric non-root `USER 10001:10001`
# ==============================================================================
ARG NODE_IMAGE=node:22.11.0-bookworm-slim@sha256:6b8d2885a22b0e83a142da38cb086942a8ef75bd124f275a1a65d1e9a4526bc1

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY apps/web/package.json ./package.json
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc,required=false \
    npm install --no-audit --no-fund

FROM ${NODE_IMAGE} AS builder
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_USE_MOCKS=false

COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ ./
RUN node scripts/assert-no-mocks-in-prod.mjs && npm run build

FROM ${NODE_IMAGE} AS runtime
ARG APP_VERSION=1.0.0
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="alba-one-web" \
      org.opencontainers.image.vendor="ALBACONNECT Inc." \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.source="https://github.com/albaconnect/alba-one"

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOME=/home/alba \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    TMPDIR=/tmp

RUN groupadd --gid 10001 alba && \
    useradd --uid 10001 --gid 10001 --create-home --home-dir /home/alba --shell /usr/sbin/nologin alba && \
    mkdir -p /app/.next/cache && \
    chown -R 10001:10001 /app /home/alba && \
    rm -rf /var/lib/apt/lists/* /usr/bin/apt* /usr/bin/dpkg* /usr/local/bin/npm /usr/local/bin/npx

WORKDIR /app
COPY --from=builder --chown=10001:10001 /app/public ./public
COPY --from=builder --chown=10001:10001 /app/.next/standalone ./
COPY --from=builder --chown=10001:10001 /app/.next/static ./.next/static
COPY --from=builder --chown=10001:10001 /app/scripts/check-startup.mjs ./scripts/check-startup.mjs

USER 10001:10001
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/ja').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]

ENTRYPOINT ["node", "-e", "import('./scripts/check-startup.mjs').then(() => import('./server.js'))"]
