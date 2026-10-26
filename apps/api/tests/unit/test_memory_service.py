"""Unit tests for Short-Term Memory and Long-Term Memory Service & Adapters (`test_memory_service.py`)."""

from __future__ import annotations

import importlib.util as _ilu
import os
import pathlib as _pl
import unittest

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_contract_path = _pl.Path(__file__).resolve().parents[1] / "memory" / "contract.py"
_cspec = _ilu.spec_from_file_location("memory_contract", _contract_path)
assert _cspec and _cspec.loader
_cmod = _ilu.module_from_spec(_cspec)
_cspec.loader.exec_module(_cmod)
LongTermMemoryContractMixin = _cmod.LongTermMemoryContractMixin

from alba_one.memory.long_term import (  # noqa: E402
    InMemoryLongTermAdapter,
    LangMemAdapter,
    Mem0OSSAdapter,
)
from alba_one.memory.short_term import ShortTermThreadMemory  # noqa: E402

try:
    import mem0  # type: ignore[import-not-found]  # noqa: F401

    HAS_MEM0_LIVE = bool(os.getenv("RUN_LIVE_MEM0"))
except ImportError:
    HAS_MEM0_LIVE = False


class TestInMemoryAdapterContract(LongTermMemoryContractMixin, unittest.TestCase):
    """Run the shared long-term memory contract suite against `InMemoryLongTermAdapter`."""

    adapter_factory = InMemoryLongTermAdapter


class TestLangMemAdapterContract(LongTermMemoryContractMixin, unittest.TestCase):
    """Run the shared long-term memory contract suite against `LangMemAdapter`."""

    adapter_factory = LangMemAdapter


class TestMem0AdapterConfigAndContract(LongTermMemoryContractMixin, unittest.TestCase):
    """Run the shared contract suite against `Mem0OSSAdapter` (mirror mode offline; live pgvector when RUN_LIVE_MEM0=1)."""

    adapter_factory = lambda self: Mem0OSSAdapter(  # noqa: E731
        gateway_base_url="https://api.portkey.ai/v1",
        gateway_api_key="test-gw-key",
        main_model="gpt-4o-2024-08-06",
        embedding_model="text-embedding-3-large",
    )

    def test_mem0_oss_config_routes_llm_and_embedder_through_gateway_and_pgvector(self) -> None:
        adapter = self.adapter_factory()
        cfg = adapter.config_dict
        self.assertEqual(cfg["vector_store"]["provider"], "pgvector")
        self.assertEqual(cfg["llm"]["config"]["openai_base_url"], "https://api.portkey.ai/v1")
        self.assertEqual(cfg["embedder"]["config"]["openai_base_url"], "https://api.portkey.ai/v1")


class TestShortTermMemory(unittest.TestCase):
    """Verify thread-scoped short-term memory summarization and browser-refresh resumption."""

    def test_short_term_summarizer_trims_and_preserves_facts_and_clarifications(self) -> None:
        stm = ShortTermThreadMemory(max_recent_messages=2)
        for i in range(4):
            stm.save_turn(
                tenant_id="tenant_alba_demo",
                thread_id="th_001",
                user_id="user_analyst_01",
                role="user",
                content=f"Turn {i}: 配送ルートRT-KNT-101のSLA 4.0hを確認",
                clarification_answer="対象車両はVH-REEFER-08" if i == 1 else None,
                active_entity="RT-KNT-101",
            )

        resumed = stm.resume_thread(tenant_id="tenant_alba_demo", thread_id="th_001")
        self.assertIsNotNone(resumed)
        assert resumed is not None
        self.assertEqual(len(resumed.messages), 2)
        self.assertIn("VH-REEFER-08", resumed.summary)
        self.assertIn("RT-KNT-101", resumed.summary)

        # Cross-tenant resume must return None
        self.assertIsNone(stm.resume_thread(tenant_id="tenant_other", thread_id="th_001"))


if __name__ == "__main__":
    unittest.main()
