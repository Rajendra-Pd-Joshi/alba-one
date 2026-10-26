# ALBA ONE — Production Deployment Order of Operations (`deploy/README.md`)

**Company:** ALBACONNECT Inc. (Tokyo; ISMS-certified)

## 1. Repository Separation: `infra/` vs. `deploy/`

- **`infra/` (Local Development & Bootstrap Only)**:
  - `infra/docker-compose.yml`: Local developer Compose with profiles (`core`, `domain`, `external`, `all`).
  - `infra/docker-compose.prod-like.yml`: Local hardening & 4-tier network segmentation verification (`read_only: true`, `cap_drop: [ALL]`, `no-new-privileges:true`, `edge`/`app`/`data`/`egress`). **Not a production deployment target.**
  - `infra/seed/`: Synthetic demo company SQL (`01_synthetic_demo_company.sql`) and DBA read-only KB views (`02_kb_readonly_views.sql`).
  - `infra/bedrock/create_guardrail.py`: AWS Bedrock Standard-tier guardrail provisioning script.
- **`deploy/` (Production & Staging Deployment Artifacts)**:
  - `deploy/docker/Caddyfile`: Edge TLS 1.2/1.3 reverse proxy and single source of security headers (HSTS, CSP, `X-Frame-Options`, `X-Content-Type-Options`).
  - `deploy/terraform/main.tf`: Managed Amazon RDS PostgreSQL 16 (`pgvector`, Multi-AZ, KMS, `rds.force_ssl = 1`, IAM DB Auth) and Managed ElastiCache Redis 7 (`transit_encryption_enabled = true`).
  - `deploy/security/mtls-and-pss.yaml`: Kubernetes Pod Security Standard (`restricted`) and Istio `STRICT` mTLS across API, Workers, MCP servers, and the on-premise KB link.
  - `deploy/helm/alba-one/`: Production Helm chart (`values.yaml`, `values-staging.yaml`, and `values-dev.yaml` labeled not-for-production).
  - `deploy/gitops/applications.yaml`: ArgoCD GitOps `Application` manifests (automated sync to staging; manual approval gate for production).
  - `deploy/observability/prometheus-alerts.yaml`: Prometheus alert rules for JWKS refresh fallback, tenant mismatch events, guardrail spikes, p95 latency, and daily cost caps.
  - `deploy/runbooks/key-rotation.md`: Zero-downtime secret rotation & emergency leak revocation runbook.

---

## 2. Exact Order of Operations for First Production Deployment

1. **Provision Managed Cloud Infrastructure (`deploy/terraform`)**:
   ```bash
   cd deploy/terraform
   terraform init
   terraform apply -var="environment=production" -var="aws_region=ap-northeast-1"
   ```
2. **Provision AWS Bedrock Standard-Tier Guardrail**:
   ```bash
   uv run python infra/bedrock/create_guardrail.py --region ap-northeast-1 --tier STANDARD
   ```
3. **Populate Secrets in AWS Secrets Manager (`ap-northeast-1`)**:
   - Create `alba-one/production/providers` and `alba-one/production/s2s` in AWS Secrets Manager.
   - Never commit `.env` or TLS private keys to the repository or container images.
4. **Apply Namespace PodSecurity (`restricted`) & mTLS Policies**:
   ```bash
   kubectl apply -f deploy/security/mtls-and-pss.yaml
   ```
5. **Run Database Migrations (`Alembic`)**:
   ```bash
   uv run alembic -c apps/api/alembic.ini upgrade head
   ```
6. **Deploy via ArgoCD GitOps (`deploy/gitops/applications.yaml`)**:
   ```bash
   kubectl apply -f deploy/gitops/applications.yaml
   ```
   - Verify staging health (`/api/v1/health/deep`) and safety evals before approving the manual sync for `alba-one-production`.
