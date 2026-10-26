# ALBA ONE — Native Japanese & English Terminology Review (`docs/I18N_REVIEW.md`)

**Status**: `TODO(owner): Native Japanese & domain owner review required before production release`

## 1. AI Recommendation vs Human Decision Terminology
Per Phase 7 & Phase 8 requirements, AI recommendations and human approval actions are never mixed in the UI or API:

| Concept | Key | Japanese (`ja`) | English (`en`) | Notes for Native Reviewer |
| :--- | :--- | :--- | :--- | :--- |
| Judge Output | `ai_recommendation` | `AI推奨` | `AI recommendation` | Displayed in the top summary card with Tertiary (`#8424DA`) badge |
| Human Action | `human_decision` | `承認の判断` | `Decision` | Displayed in the sticky action bar (approver roles only) |
| Action 1 | `action_approve` | `承認` | `Approve` | `ApprovalAction.APPROVE` |
| Action 2 | `action_approve_with_conditions` | `条件付き承認` | `Approve with conditions` | `ApprovalAction.APPROVE_WITH_CONDITIONS` (opens structured conditions editor) |
| Action 3 | `action_reject` | `却下` | `Reject` | `ApprovalAction.REJECT` |
| Action 4 | `action_request_more_evidence` | `追加根拠を依頼` | `Request more evidence` | `ApprovalAction.REQUEST_MORE_EVIDENCE` (opens questions editor) |

## 2. Comparison Table & Gate Status Badges
| Key | Japanese (`ja`) | English (`en`) |
| :--- | :--- | :--- |
| `parameters_not_verified` | `パラメータ未検証` | `Parameters not verified` |
| `insufficient_data` | `データ不足` | `Insufficient data` |
| `missing` | `データ欠損` | `Missing` |
| `no_evidence` | `根拠なし` | `No evidence` |
| `weights_not_reviewed` | `重み付け未承認（総合スコア非表示）` | `Weights not reviewed (composite score hidden)` |
