# ALBA ONE — Regression Corpus (`redteam/corpus/README.md`)

Every critical security finding or red-team bypass discovered in staging or production MUST have a corresponding deterministic regression fixture added to `redteam/corpus/` and verified by a passing retest before the incident issue can be closed by a human reviewer.

- All fixtures in `redteam/corpus/` must use clearly fictional entities (`架空テスト海運株式会社`, `Fictional Test Maritime Corp`, `FICTIONAL-CODE-KAGUYA-架空`) and dynamic `CANARY-<hex>` markers.
- Changes to `redteam/corpus/` require `@albaconnect/security-owners` approval via `.github/CODEOWNERS`.
