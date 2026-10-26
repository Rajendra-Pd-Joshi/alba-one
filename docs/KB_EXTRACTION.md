# ALBA ONE — On-Premise Knowledge Base Extraction & Security Model (`docs/KB_EXTRACTION.md`)

## 1. DBA-Controlled Read-Only Views (`infra/seed/02_kb_readonly_views.sql`)

To ensure the ingestion pipeline never accesses unapproved columns or mutates operational tables, `alba_one.kb.extractors` only queries allowlisted read-only SQL views (`ALLOWED_EXTRACTION_VIEWS`):

| View Name | Underlying Table | Business Entities Mapped | Incremental Watermark |
| :--- | :--- | :--- | :--- |
| `v_kb_companies` | `tenants` | `company` | `updated_at` |
| `v_kb_delivery_routes` | `demo_delivery_routes` | `route`, `equipment` | `updated_at` |
| `v_kb_vessels_berths` | `demo_vessels_berths` | `vessel`, `product` | `updated_at` |
| `v_kb_staff_shifts` | `demo_staff_shifts` | `staff` | `updated_at` |
| `v_kb_ml_model_releases` | `demo_ml_model_releases` | `model_release` | `updated_at` |

## 2. Pre-Embedding PII Redaction (`kb/pii.py`)

Before any text leaves on-premise PostgreSQL for embedding (`text-embedding-3-large`), `PIIRedactor` normalizes Unicode (`NFKC`) and replaces sensitive fields with deterministic tokens:
- **Japanese & English Person Names** (configured per tenant) -> `[PII_PERSON]`
- **Japanese Phone Numbers** (`03-...`, `090-...`, `+81-...`) -> `[PII_PHONE]`
- **Japanese Postal Codes** (`〒140-0003`, `Postal: 140-0003`) -> `[PII_POSTAL_JP]`
- **Individual Number / マイナンバー** (12-digit numbers) -> `[PII_MYNUMBER]`
- **Email Addresses** -> `[PII_EMAIL]`

## 3. Strict Separation of On-Prem Text vs. Pinecone Vector Metadata (`kb/indexer.py`)

- **On-Premise PostgreSQL (`kb_documents`, `kb_chunks`)**: Stores the full chunk text (`text`) and Japanese morphological tokens (`tokenized_text`).
- **Pinecone Vector Index (`namespace=tenant_id`)**: Stores **ONLY** the 7 allowlisted metadata fields:
  `chunk_id`, `tenant_id`, `acl_tags`, `entity_type`, `lang`, `valid_from`, `valid_to`.
- `assert_pinecone_metadata_safe()` raises a `ValueError` if any text field (`text`, `content`, `body`, `quote`, `parent_text`, `title`) is ever passed to Pinecone.
