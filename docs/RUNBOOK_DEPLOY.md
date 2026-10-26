# ALBA ONE — Deployment, Base Image Refresh & Local TLS Runbook (`docs/RUNBOOK_DEPLOY.md`)

**Company:** ALBACONNECT Inc. (Tokyo; ISMS-certified)

## 1. Refreshing Digest-Pinned Base Images in Dockerfiles

All production Dockerfiles (`apps/api/Dockerfile`, `apps/api/Dockerfile.mcp`, `apps/web/Dockerfile`) and `infra/docker-compose.prod-like.yml` pin base images by immutable `@sha256:...` digest so builds are reproducible and immune to mutable tag tampering.

### How to Refresh Base Image Digests (Monthly or on CVE Advisory)
1. Pull the latest patch tag on a developer workstation with Docker / `crane`:
   ```bash
   docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.4.20-python3.12-bookworm-slim
   docker buildx imagetools inspect python:3.12.7-slim-bookworm
   docker buildx imagetools inspect node:22.11.0-bookworm-slim
   ```
2. Copy the multi-arch manifest list `Digest: sha256:...` into the `ARG` headers at the top of:
   - `apps/api/Dockerfile`
   - `apps/api/Dockerfile.mcp`
   - `apps/web/Dockerfile`
3. Run `./ci/scripts/check_images.sh` to verify digest pinning, non-root `USER 10001:10001`, and read-only rootfs startup.
4. Open a PR; CI will run Trivy vulnerability scanning and rebuild all container targets.

---

## 2. Trusting the Local Test Certificate for `infra/docker-compose.prod-like.yml`

No TLS private keys or certificates are stored in this repository. When running `infra/docker-compose.prod-like.yml` locally:
- The `proxy` service (`Caddy 2.8`) uses `tls internal` (`deploy/docker/Caddyfile`) to generate an ephemeral local CA and leaf certificate inside its in-memory `/data` tmpfs volume on startup.
- To trust the local Caddy root certificate on your workstation during local testing:
  ```bash
  docker compose -f infra/docker-compose.prod-like.yml up -d proxy
  docker compose -f infra/docker-compose.prod-like.yml cp proxy:/data/caddy/pki/authorities/local/root.crt /tmp/alba-local-ca.crt
  # macOS:
  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain /tmp/alba-local-ca.crt
  # Ubuntu / Debian:
  sudo cp /tmp/alba-local-ca.crt /usr/local/share/ca-certificates/alba-local-ca.crt && sudo update-ca-certificates
  ```
- In staging and production, TLS 1.2/1.3 termination is handled by AWS ALB + ACM (or Ingress + `cert-manager`) with automated certificate renewal.

---

## 3. Verifying Read-Only Root Filesystem Locally

Every service in `infra/docker-compose.prod-like.yml` and `deploy/helm/alba-one` runs with `read_only: true` (`readOnlyRootFilesystem: true`), `cap_drop: [ALL]`, and `no-new-privileges:true`.
- **FastAPI / Worker / MCP servers (`apps/api/Dockerfile*`)**:
  - Bytecode compilation is performed during the image build (`UV_COMPILE_BYTECODE=1`) and disabled at runtime (`PYTHONDONTWRITEBYTECODE=1`).
  - `/tmp` is mounted as an in-memory `tmpfs` (`emptyDir` in Kubernetes).
- **Next.js 15 Standalone (`apps/web/Dockerfile`)**:
  - Built with `output: "standalone"`. At runtime, Next.js writes only to `/app/.next/cache` (incremental cache) and `/tmp`.
  - Both `/tmp` and `/app/.next/cache` are explicitly mounted as `tmpfs` in `infra/docker-compose.prod-like.yml` and `emptyDir` in `deploy/helm/alba-one/templates/deployments.yaml`.
