"""Idempotent AWS Bedrock Guardrail definition and provisioner (`infra/bedrock/create_guardrail.py`).

Verified against AWS Bedrock `create_guardrail` / `update_guardrail` API docs (2026-10-24):
- Classic tier (`CLASSIC`) only covers English, French, and Spanish.
- Japanese (`ja`) requires the **Standard tier** (`tierConfig={'tierName': 'STANDARD'}`)
  on `contentPolicyConfig` and `topicPolicyConfig`, plus `crossRegionConfig={'guardrailProfileIdentifier': ...}`
  (e.g. `apac.guardrail.v1:0` in `ap-northeast-1`).
- Fails with a clear `ValueError` if `tier == 'CLASSIC'` and Japanese support is required,
  or if `tier == 'STANDARD'` and `cross_region_profile` is missing.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any


def build_create_guardrail_payload(
    *,
    name: str = "alba-one-decision-os-guardrail",
    tier: str,
    cross_region_profile: str,
    mode: str = "enforce",
    require_japanese: bool = True,
) -> dict[str, Any]:
    """Construct the exact boto3 `create_guardrail` / `update_guardrail` parameter dictionary.

    Args:
        name: Guardrail resource name.
        tier: From `BEDROCK_GUARDRAIL_TIER` (`"STANDARD"` or `"CLASSIC"`).
        cross_region_profile: From `BEDROCK_GUARDRAIL_CROSS_REGION_PROFILE` (no hardcoded profile!).
        mode: `"enforce"` (`BLOCK` / `ANONYMIZE`) or `"monitor"` (Detect mode: `NONE`).
        require_japanese: When True, rejects `CLASSIC` tier because Japanese is only supported on `STANDARD`.
    """
    norm_tier = tier.strip().upper()
    if norm_tier not in ("STANDARD", "CLASSIC"):
        raise ValueError(f"Invalid BEDROCK_GUARDRAIL_TIER='{tier}'. Must be 'STANDARD' or 'CLASSIC'.")

    if require_japanese and norm_tier == "CLASSIC":
        raise ValueError(
            "BEDROCK_GUARDRAIL_TIER='CLASSIC' does not support Japanese (Classic tier only covers "
            "English, French, and Spanish). Set BEDROCK_GUARDRAIL_TIER=STANDARD and configure "
            "BEDROCK_GUARDRAIL_CROSS_REGION_PROFILE (e.g., apac.guardrail.v1:0 for ap-northeast-1)."
        )

    profile = cross_region_profile.strip()
    if norm_tier == "STANDARD" and not profile:
        raise ValueError(
            "BEDROCK_GUARDRAIL_CROSS_REGION_PROFILE is required when BEDROCK_GUARDRAIL_TIER='STANDARD'."
        )

    block_action = "BLOCK" if mode.strip().lower() == "enforce" else "NONE"
    pii_action = "ANONYMIZE" if mode.strip().lower() == "enforce" else "NONE"

    content_filters = [
        {
            "type": ftype,
            "inputStrength": "HIGH",
            "outputStrength": "HIGH" if ftype != "PROMPT_ATTACK" else "NONE",
            "inputAction": block_action,
            "outputAction": block_action,
            "inputEnabled": True,
            "outputEnabled": ftype != "PROMPT_ATTACK",
        }
        for ftype in ("HATE", "INSULTS", "SEXUAL", "VIOLENCE", "MISCONDUCT", "PROMPT_ATTACK")
    ]

    payload: dict[str, Any] = {
        "name": name,
        "description": "ALBA ONE Decision OS bilingual (JP/EN) guardrail (Standard tier)",
        "blockedInputMessaging": (
            "ガードレールポリシーにより入力が制限されました。業務範囲内の質問を入力してください。 / "
            "Your input was restricted by the guardrail policy. Please submit an in-scope operational query."
        ),
        "blockedOutputsMessaging": (
            "ガードレールポリシーにより出力が制限されました。根拠が確認できる範囲で再実行してください。 / "
            "The output was restricted by the guardrail policy due to safety or grounding rules."
        ),
        "contentPolicyConfig": {
            "filtersConfig": content_filters,
            "tierConfig": {"tierName": norm_tier},
        },
        "topicPolicyConfig": {
            "topicsConfig": [
                {
                    "name": "medical_or_clinical_advice",
                    "definition": "Providing medical diagnosis, clinical treatment, or prescription advice in Japanese or English.",
                    "examples": [
                        "この症状に効く処方薬と診断名を教えてください",
                        "Diagnose my medical symptoms and prescribe medication",
                    ],
                    "type": "DENY",
                    "inputAction": block_action,
                    "outputAction": block_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                },
                {
                    "name": "personal_legal_or_tax_representation",
                    "definition": "Acting as a licensed attorney or tax advisor for personal litigation or tax evasion.",
                    "examples": [
                        "脱税スキームや個人訴訟の弁護方針を作成して",
                        "Draft a personal lawsuit strategy or tax evasion scheme",
                    ],
                    "type": "DENY",
                    "inputAction": block_action,
                    "outputAction": block_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                },
            ],
            "tierConfig": {"tierName": norm_tier},
        },
        "wordPolicyConfig": {
            # Note: AWS Bedrock Word Filters only support EN/FR/ES; JP words are enforced by our local validator.
            "wordsConfig": [
                {
                    "text": "OVERRIDE_SAFETY_GATE",
                    "inputAction": block_action,
                    "outputAction": block_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                }
            ],
            "managedWordListsConfig": [
                {
                    "type": "PROFANITY",
                    "inputAction": block_action,
                    "outputAction": block_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                }
            ],
        },
        "sensitiveInformationPolicyConfig": {
            "piiEntitiesConfig": [
                {"type": "EMAIL", "action": pii_action, "inputAction": pii_action, "outputAction": pii_action, "inputEnabled": True, "outputEnabled": True},
                {"type": "PHONE", "action": pii_action, "inputAction": pii_action, "outputAction": pii_action, "inputEnabled": True, "outputEnabled": True},
                {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": block_action, "inputAction": block_action, "outputAction": block_action, "inputEnabled": True, "outputEnabled": True},
            ],
            "regexesConfig": [
                {
                    "name": "JP_MY_NUMBER_12_DIGIT",
                    "description": "Japanese 12-digit Individual Number (マイナンバー)",
                    "pattern": r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)",
                    "action": pii_action,
                    "inputAction": pii_action,
                    "outputAction": pii_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                },
                {
                    "name": "JP_PHONE_NUMBER",
                    "description": "Japanese domestic & +81 phone numbers",
                    "pattern": r"(?:\+81[-\s]?|0)\d{1,4}[-\s()（）]\d{1,4}[-\s()（）]\d{3,4}",
                    "action": pii_action,
                    "inputAction": pii_action,
                    "outputAction": pii_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                },
                {
                    "name": "JP_POSTAL_CODE",
                    "description": "Japanese postal code with 〒 symbol",
                    "pattern": r"〒\s*\d{3}-\d{4}",
                    "action": pii_action,
                    "inputAction": pii_action,
                    "outputAction": pii_action,
                    "inputEnabled": True,
                    "outputEnabled": True,
                },
            ],
        },
        "contextualGroundingPolicyConfig": {
            "filtersConfig": [
                {"type": "GROUNDING", "threshold": 0.75, "action": block_action, "enabled": True},
                {"type": "RELEVANCE", "threshold": 0.70, "action": block_action, "enabled": True},
            ]
        },
    }

    if norm_tier == "STANDARD":
        payload["crossRegionConfig"] = {"guardrailProfileIdentifier": profile}

    return payload


def ensure_guardrail_idempotent(
    bedrock_client: Any,
    *,
    name: str = "alba-one-decision-os-guardrail",
    tier: str,
    cross_region_profile: str,
    mode: str = "enforce",
) -> dict[str, str]:
    """Idempotently create or update the ALBA ONE Bedrock Guardrail via `boto3.client('bedrock')`."""
    payload = build_create_guardrail_payload(
        name=name,
        tier=tier,
        cross_region_profile=cross_region_profile,
        mode=mode,
    )
    existing_list = bedrock_client.list_guardrails().get("guardrails", [])
    existing = next((g for g in existing_list if g.get("name") == name), None)

    if existing:
        guardrail_id = str(existing["id"])
        resp = bedrock_client.update_guardrail(guardrailIdentifier=guardrail_id, **payload)
        version = str(resp.get("version", "DRAFT"))
        return {"action": "updated", "guardrailId": guardrail_id, "version": version}

    resp = bedrock_client.create_guardrail(**payload)
    guardrail_id = str(resp["guardrailId"])
    ver_resp = bedrock_client.create_guardrail_version(
        guardrailIdentifier=guardrail_id,
        description="Initial ALBA ONE Standard-tier release",
    )
    return {
        "action": "created",
        "guardrailId": guardrail_id,
        "version": str(ver_resp.get("version", "1")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision or preview ALBA ONE Bedrock Guardrail.")
    parser.add_argument("--dry-run", action="store_true", help="Print payload JSON without calling AWS")
    parser.add_argument("--tier", default=os.getenv("BEDROCK_GUARDRAIL_TIER", "STANDARD"))
    parser.add_argument(
        "--cross-region-profile",
        default=os.getenv("BEDROCK_GUARDRAIL_CROSS_REGION_PROFILE", ""),
    )
    parser.add_argument("--mode", default=os.getenv("GUARDRAIL_MODE", "enforce"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-northeast-1"))
    args = parser.parse_args(argv)

    payload = build_create_guardrail_payload(
        tier=args.tier,
        cross_region_profile=args.cross_region_profile,
        mode=args.mode,
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    import boto3

    client = boto3.client("bedrock", region_name=args.region)
    res = ensure_guardrail_idempotent(
        client,
        tier=args.tier,
        cross_region_profile=args.cross_region_profile,
        mode=args.mode,
    )
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
