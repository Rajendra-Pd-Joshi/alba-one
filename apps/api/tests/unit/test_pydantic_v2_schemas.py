"""Unit tests for Pydantic v2 domain models (`alba_one.schemas`)."""

from __future__ import annotations

import importlib.util as _ilu, pathlib as _pl
_spec = _ilu.spec_from_file_location('_bootstrap', _pl.Path(__file__).with_name('_bootstrap.py'))
assert _spec is not None and _spec.loader is not None
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)

import unittest
import pydantic

IS_PYDANTIC_V2 = pydantic.__version__.startswith("2.")


@unittest.skipUnless(IS_PYDANTIC_V2, f"Requires Pydantic v2 (found {pydantic.__version__})")
class TestPydanticV2Schemas(unittest.TestCase):
    """Verify Principle 2 & Principle 3: Pydantic v2 boundary validation and Evidence-first rules."""

    def test_hypothesis_requires_at_least_one_evidence_citation(self) -> None:
        from alba_one.schemas import (
            ConfidenceBreakdown,
            Evidence,
            EvidenceKind,
            Hypothesis,
            HypothesisStance,
        )

        conf = ConfidenceBreakdown(
            score=0.85,
            evidence_strength=0.9,
            coverage=0.8,
            consistency=0.85,
            judge_notes="Grounded in KB chunk.",
        )

        with self.assertRaises(pydantic.ValidationError):
            Hypothesis(
                id="hyp_invalid",
                tenant_id="tenant_alba_demo",
                statement="Uncited claim",
                stance=HypothesisStance.SUPPORT,
                rationale="No evidence",
                evidence=[],
                confidence=conf,
            )

        valid = Hypothesis(
            id="hyp_valid",
            tenant_id="tenant_alba_demo",
            statement="Cited claim",
            stance=HypothesisStance.SUPPORT,
            rationale="Backed by KB chunk",
            evidence=[
                Evidence(
                    kind=EvidenceKind.KB,
                    ref_id="chunk_synth_001",
                    quote_span="SLA 4.0 hours",
                )
            ],
            confidence=conf,
        )
        self.assertEqual(valid.id, "hyp_valid")

    def test_decision_recommendation_requires_hypothesis_citations_on_approve(self) -> None:
        from alba_one.schemas import DecisionRecommendation, RecommendationVerdict

        with self.assertRaises(pydantic.ValidationError):
            DecisionRecommendation(
                decision_id="dec_1",
                tenant_id="tenant_alba_demo",
                verdict=RecommendationVerdict.RECOMMEND_APPROVE,
                options_compared=["Option A", "Option B"],
                rationale="Option A is better",
                cited_hypothesis_ids=[],
            )


if __name__ == "__main__":
    unittest.main()
