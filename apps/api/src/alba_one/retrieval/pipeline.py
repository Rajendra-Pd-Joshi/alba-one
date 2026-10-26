"""Phase 3: Retrieval Pipeline Subgraph & CLI (`retrieval/pipeline.py`).

Orchestrates Clarifier -> Adaptive Router -> Multi-Query Rewriter -> Hybrid RRF
Retrieval -> Retriever Guardrail -> Reranker -> Self-RAG Grader -> Corrective RAG,
recording stage latency and token cost to `llm_calls` and LangSmith spans.
CLI: `uv run python -m alba_one.retrieval.pipeline "<question>" --lang ja`
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, TypedDict

from alba_one.kb.indexer import KnowledgeBaseIndexer, build_default_demo_kb
from alba_one.retrieval.clarifier import (
    MAX_CLARIFICATION_ROUNDS,
    ClarificationResult,
    analyze_clarification,
)
from alba_one.retrieval.corrective import CorrectiveOutcomeStatus, run_corrective_rag
from alba_one.retrieval.external_stub import StubExternalSearchAdapter
from alba_one.retrieval.grader import grade_retrieved_chunks
from alba_one.retrieval.guardrail_stub import RetrieverGuardrailStub
from alba_one.retrieval.hybrid import RetrievalMode, run_hybrid_retrieval
from alba_one.retrieval.ports import ExternalResult, ExternalSearchPort
from alba_one.retrieval.query_rewriter import RewrittenQuerySet, rewrite_queries
from alba_one.retrieval.reranker import FakeReranker, RerankerPort
from alba_one.retrieval.router import AdaptiveRouteDecision, route_query
from alba_one.retrieval.telemetry import RetrievalTelemetryCollector


class RetrievalGraphState(TypedDict, total=False):
    """TypedDict state for the LangGraph retrieval subgraph."""

    tenant_id: str
    caller_role: str
    query: str
    lang: str
    round_number: int
    clarification_answers: list[str]
    explicit_assumptions: list[str]
    thread_memory: dict[str, Any]
    clarification: dict[str, Any]
    rewritten: dict[str, Any]
    route: dict[str, Any]
    fused_chunks: list[dict[str, Any]]
    reranked_chunks: list[dict[str, Any]]
    final_chunks: list[dict[str, Any]]
    external_results: list[dict[str, Any]]
    external_used: bool
    status: str
    tried_steps: list[str]
    guardrail_events: list[dict[str, Any]]
    telemetry: list[dict[str, Any]]


@dataclass(frozen=True)
class RetrievalPipelineOutput:
    """Complete structured output of an end-to-end retrieval pipeline execution."""

    tenant_id: str
    query: str
    lang: str
    status: CorrectiveOutcomeStatus | str
    clarification_rounds: list[ClarificationResult]
    explicit_assumptions: list[str]
    rewritten_queries: RewrittenQuerySet
    route: AdaptiveRouteDecision
    fused_chunks: list[dict[str, Any]]
    reranked_chunks: list[dict[str, Any]]
    final_chunks: list[dict[str, Any]]
    external_results: list[ExternalResult]
    external_used: bool
    tried_steps: list[str]
    guardrail_events: list[dict[str, Any]] = field(default_factory=list)
    telemetry: list[dict[str, Any]] = field(default_factory=list)


class RetrievalPipeline:
    """Composable retrieval pipeline usable directly, from CLI, or inside LangGraph nodes."""

    def __init__(
        self,
        *,
        indexer: KnowledgeBaseIndexer,
        reranker: RerankerPort | None = None,
        external_port: ExternalSearchPort | None = None,
        guardrail: RetrieverGuardrailStub | None = None,
        query_rewrite_count: int = 4,
        rerank_top_k: int = 5,
        relevance_threshold: float = 0.35,
        allow_external_fallback: bool = True,
        enable_multimodal_rag: bool = False,
    ) -> None:
        self.indexer = indexer
        self.reranker = reranker or FakeReranker()
        self.external_port = external_port or StubExternalSearchAdapter()
        self.guardrail = guardrail or RetrieverGuardrailStub()
        self.query_rewrite_count = query_rewrite_count
        self.rerank_top_k = rerank_top_k
        self.relevance_threshold = relevance_threshold
        self.allow_external_fallback = allow_external_fallback
        self.enable_multimodal_rag = enable_multimodal_rag

    def run(
        self,
        query: str,
        *,
        tenant_id: str = "tenant_alba_demo",
        caller_role: str = "analyst",
        lang: str = "ja",
        clarification_answers: list[str] | None = None,
        interactive_answer_fn: Callable[[ClarificationResult], str | None] | None = None,
        thread_memory: dict[str, Any] | None = None,
        retrieval_mode: RetrievalMode = "hybrid",
        use_reranker: bool = True,
        use_corrective: bool = True,
    ) -> RetrievalPipelineOutput:
        """Execute the full retrieval pipeline and return `RetrievalPipelineOutput`."""
        telemetry = RetrievalTelemetryCollector(tenant_id=tenant_id)
        answers = list(clarification_answers or [])
        rounds: list[ClarificationResult] = []
        assumptions: list[str] = []

        round_num = 0
        while True:
            with telemetry.measure("clarifier", model="gpt-4o-2024-08-06", prompt_tokens=120, completion_tokens=45):
                clar = analyze_clarification(
                    query, lang=lang, round_number=round_num,
                    clarification_answers=answers, thread_memory=thread_memory,
                )
            rounds.append(clar)
            assumptions.extend(clar.explicit_assumptions)
            if not clar.is_ambiguous:
                break
            if interactive_answer_fn is None or round_num >= MAX_CLARIFICATION_ROUNDS:
                fallback_clar = analyze_clarification(
                    query, lang=lang, round_number=MAX_CLARIFICATION_ROUNDS,
                    clarification_answers=answers, thread_memory=thread_memory,
                )
                rounds.append(fallback_clar)
                assumptions.extend(fallback_clar.explicit_assumptions)
                break
            reply = interactive_answer_fn(clar)
            if not reply or not reply.strip():
                round_num = MAX_CLARIFICATION_ROUNDS
            else:
                answers.append(reply.strip())
                round_num += 1

        with telemetry.measure("router", model="deterministic"):
            route = route_query(" ".join([query, *answers]))
        with telemetry.measure("query_rewriter", model="gpt-4o-2024-08-06", prompt_tokens=150, completion_tokens=80):
            rewritten = rewrite_queries(
                query, lang=lang,
                num_variants=self.query_rewrite_count if route.use_multi_query else 2,
                clarification_answers=answers, explicit_assumptions=assumptions, thread_memory=thread_memory,
            )

        if route.classification == "no_retrieval":
            return RetrievalPipelineOutput(
                tenant_id, query, lang, "no_retrieval", rounds, assumptions, rewritten,
                route, [], [], [], [], False, ["router(no_retrieval)"], [], telemetry.to_dicts(),
            )

        with telemetry.measure("hybrid_retrieval", model="text-embedding-3-large", prompt_tokens=90):
            raw_fused = run_hybrid_retrieval(
                self.indexer, tenant_id=tenant_id, caller_role=caller_role,
                queries=rewritten.all_queries, top_k=max(self.rerank_top_k * 2, 8), mode=retrieval_mode,
            )
        with telemetry.measure("retriever_guardrail", model="deterministic"):
            guarded, gr_stats = self.guardrail.filter_kb_chunks(raw_fused, tenant_id=tenant_id, caller_role=caller_role)

        if use_reranker:
            with telemetry.measure("reranker", model="rerank-v4.0-pro", prompt_tokens=200):
                reranked = self.reranker.rerank(" ".join([query, *answers]).strip(), guarded, top_k=self.rerank_top_k)
        else:
            reranked = guarded[: self.rerank_top_k]

        with telemetry.measure("self_rag_grader", model="gpt-4o-2024-08-06", prompt_tokens=180, completion_tokens=40):
            graded = grade_retrieved_chunks(query, reranked, relevance_threshold=self.relevance_threshold)

        if not use_corrective:
            status_val = "grounded_kb" if graded.meets_threshold else "insufficient_evidence"
            return RetrievalPipelineOutput(
                tenant_id, query, lang, status_val, rounds, assumptions, rewritten,
                route, guarded, reranked, reranked, [], False,
                [f"no_corrective(max_score={graded.max_score})"], gr_stats.events, telemetry.to_dicts(),
            )

        def _retry_fn(retry_q: str) -> list[dict[str, Any]]:
            rf = run_hybrid_retrieval(
                self.indexer, tenant_id=tenant_id, caller_role=caller_role,
                queries=[retry_q, *rewritten.all_queries[:2]], top_k=max(self.rerank_top_k * 2, 8), mode=retrieval_mode,
            )
            rc, _ = self.guardrail.filter_kb_chunks(rf, tenant_id=tenant_id, caller_role=caller_role)
            return self.reranker.rerank(retry_q, rc, top_k=self.rerank_top_k)

        with telemetry.measure("corrective_rag", model="gpt-4o-2024-08-06", prompt_tokens=110, completion_tokens=35):
            corr = run_corrective_rag(
                query=query, lang=lang, initial_graded=graded, retry_retrieve_fn=_retry_fn,
                external_port=self.external_port, guardrail=self.guardrail,
                relevance_threshold=self.relevance_threshold, allow_external_fallback=self.allow_external_fallback,
            )

        return RetrievalPipelineOutput(
            tenant_id, query, lang, corr.status, rounds, assumptions, rewritten,
            route, guarded, reranked, corr.chunks, corr.external_results,
            corr.external_used, corr.tried_steps, [*gr_stats.events, *corr.guardrail_events], telemetry.to_dicts(),
        )


def build_retrieval_langgraph(pipeline: RetrievalPipeline) -> Any:
    """Compile the Phase 3 Retrieval Pipeline as a LangGraph `StateGraph` subgraph."""
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    def clarify_node(state: RetrievalGraphState) -> dict[str, Any]:
        clar = analyze_clarification(
            state["query"], lang=state.get("lang", "ja"), round_number=state.get("round_number", 0),
            clarification_answers=state.get("clarification_answers", []), thread_memory=state.get("thread_memory"),
        )
        if clar.is_ambiguous:
            ans = interrupt({"questions": clar.questions, "missing_slots": clar.missing_slots})
            return {
                "clarification_answers": [*state.get("clarification_answers", []), str(ans)],
                "round_number": clar.round_number, "clarification": asdict(clar),
            }
        return {"explicit_assumptions": clar.explicit_assumptions, "clarification": asdict(clar)}

    def retrieve_node(state: RetrievalGraphState) -> dict[str, Any]:
        out = pipeline.run(
            state["query"], tenant_id=state.get("tenant_id", "tenant_alba_demo"),
            caller_role=state.get("caller_role", "analyst"), lang=state.get("lang", "ja"),
            clarification_answers=state.get("clarification_answers", []), thread_memory=state.get("thread_memory"),
        )
        return {
            "rewritten": asdict(out.rewritten_queries), "route": asdict(out.route),
            "fused_chunks": out.fused_chunks, "reranked_chunks": out.reranked_chunks,
            "final_chunks": out.final_chunks, "external_used": out.external_used,
            "status": out.status, "tried_steps": out.tried_steps,
            "guardrail_events": out.guardrail_events, "telemetry": out.telemetry,
        }

    builder = StateGraph(RetrievalGraphState)
    builder.add_node("clarify", clarify_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_edge(START, "clarify")
    builder.add_edge("clarify", "retrieve")
    builder.add_edge("retrieve", END)
    return builder.compile()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: `uv run python -m alba_one.retrieval.pipeline "<question>" --lang ja`."""
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 3 Retrieval Pipeline CLI")
    parser.add_argument("question", help="User decision question")
    parser.add_argument("--lang", default="ja", choices=["ja", "en"])
    parser.add_argument("--tenant", default="tenant_alba_demo")
    parser.add_argument("--role", default="analyst")
    parser.add_argument("--answer", action="append", default=[])
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args(argv)

    indexer, _, _ = build_default_demo_kb()
    pipeline = RetrievalPipeline(indexer=indexer)

    def _cli_prompt(clar: ClarificationResult) -> str | None:
        print(f"\n[Clarification Round {clar.round_number}] Missing slots: {clar.missing_slots}")
        for idx, q in enumerate(clar.questions, start=1):
            print(f"  Q{idx}: {q}")
        if args.non_interactive or not sys.stdin.isatty():
            return None
        return input("Your answer (or Enter to proceed with assumptions): ")

    out = pipeline.run(
        args.question, tenant_id=args.tenant, caller_role=args.role,
        lang=args.lang, clarification_answers=args.answer, interactive_answer_fn=_cli_prompt,
    )
    payload = {
        "query": out.query, "lang": out.lang, "status": out.status,
        "clarification_rounds": [asdict(r) for r in out.clarification_rounds],
        "explicit_assumptions": out.explicit_assumptions, "route": asdict(out.route),
        "rewritten_queries": out.rewritten_queries.all_queries,
        "final_chunks": [{"chunk_id": c["chunk_id"], "score": c["score"], "text": c["text"]} for c in out.final_chunks],
        "external_used": out.external_used, "tried_steps": out.tried_steps,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
