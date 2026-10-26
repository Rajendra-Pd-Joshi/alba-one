"""Shared Long-Term Memory Adapter Contract Test Suite (`apps/api/tests/memory/contract.py`).

Per User Answer 2:
Every `LongTermMemoryPort` adapter (`in_memory`, `mem0`, `langmem`) must pass this exact contract:
1. Tenant isolation (Tenant A can never read, search, or delete Tenant B's memories).
2. User isolation (User 1 can never read, search, or delete User 2's private memories).
3. Complete deletion (`delete_memory` removes the item from both list and search).
4. TTL expiry via injectable clock (`clock()` advancing past `expires_at_epoch` hides expired items).
5. Conflict resolution (newer approved/confirmed fact on the same `topic_key` supersedes older fact).
6. Policy enforcement above adapter (rejects writes without `approval_id`/`user_confirmed=True` and scrubs PII before handing to the adapter).
"""

from __future__ import annotations

from collections.abc import Callable
import unittest

from alba_one.memory.long_term import LongTermMemoryPort, MemoryService


class LongTermMemoryContractMixin:
    """Mixin that runs the 6 mandatory contract assertions against any `LongTermMemoryPort` factory."""

    adapter_factory: Callable[[], LongTermMemoryPort]

    def _make_service(
        self, clock: Callable[[], float] = lambda: 1000.0
    ) -> tuple[MemoryService, LongTermMemoryPort]:
        adapter = self.adapter_factory()
        svc = MemoryService(adapter=adapter, clock=clock, default_ttl_seconds=600)
        return svc, adapter

    def test_contract_tenant_and_user_isolation(self: unittest.TestCase) -> None:
        svc, _ = self._make_service()  # type: ignore[attr-defined]
        svc.propose_memory(
            tenant_id="tenant_a",
            user_id="user_1",
            memory_type="approved_decision_rationale",
            topic_key="berth_b3_priority",
            content="東京港大井第3バース（TYO-OI-B3）は医薬品定温コンテナを優先着岸させる。",
            approval_id="app_001",
        )
        svc.propose_memory(
            tenant_id="tenant_b",
            user_id="user_1",
            memory_type="approved_decision_rationale",
            topic_key="berth_b3_priority",
            content="Tenant B confidential strategy.",
            approval_id="app_002",
        )

        # Tenant A only sees Tenant A's memory
        list_a = svc.list_my_memories(tenant_id="tenant_a", user_id="user_1")
        self.assertEqual(len(list_a), 1)
        self.assertIn("TYO-OI-B3", list_a[0].content)

        # Cross-tenant search from Tenant A for Tenant B's content returns empty
        search_cross = svc.search_memories(
            tenant_id="tenant_a", user_id="user_1", query="confidential"
        )
        self.assertEqual(search_cross, [])

        # User 2 inside Tenant A cannot see User 1's private memory
        list_u2 = svc.list_my_memories(tenant_id="tenant_a", user_id="user_2")
        self.assertEqual(list_u2, [])

        # User 2 cannot delete User 1's memory
        with self.assertRaises(PermissionError):
            svc.delete_memory(
                tenant_id="tenant_a",
                user_id="user_2",
                memory_id=list_a[0].memory_id,
            )

    def test_contract_delete_is_complete(self: unittest.TestCase) -> None:
        svc, _ = self._make_service()  # type: ignore[attr-defined]
        item = svc.propose_memory(
            tenant_id="tenant_a",
            user_id="user_1",
            memory_type="user_preference",
            topic_key="response_detail",
            content="Always show confidence breakdown table in Japanese.",
            user_confirmed=True,
        )
        self.assertEqual(len(svc.list_my_memories(tenant_id="tenant_a", user_id="user_1")), 1)
        deleted = svc.delete_memory(
            tenant_id="tenant_a", user_id="user_1", memory_id=item.memory_id
        )
        self.assertTrue(deleted)
        self.assertEqual(svc.list_my_memories(tenant_id="tenant_a", user_id="user_1"), [])
        self.assertEqual(
            svc.search_memories(tenant_id="tenant_a", user_id="user_1", query="confidence"), []
        )

    def test_contract_ttl_expiry_with_injectable_clock(self: unittest.TestCase) -> None:
        now = 1000.0
        svc, _ = self._make_service(clock=lambda: now)  # type: ignore[attr-defined]
        svc.propose_memory(
            tenant_id="tenant_a",
            user_id="user_1",
            memory_type="glossary_clarification",
            topic_key="sla_definition",
            content="SLA hours count from vessel berth completion.",
            user_confirmed=True,
            ttl_seconds=60,
        )
        self.assertEqual(len(svc.list_my_memories(tenant_id="tenant_a", user_id="user_1")), 1)

        # Advance clock past TTL (60s)
        now += 61.0
        self.assertEqual(svc.list_my_memories(tenant_id="tenant_a", user_id="user_1"), [])

    def test_contract_newer_approved_fact_supersedes_older(self: unittest.TestCase) -> None:
        now = 1000.0
        svc, _ = self._make_service(clock=lambda: now)  # type: ignore[attr-defined]
        svc.propose_memory(
            tenant_id="tenant_a",
            user_id="user_1",
            memory_type="outcome_learning",
            topic_key="wind_halt_threshold",
            content="Old rule: halt crane at 18.0 m/s.",
            approval_id="app_old",
        )
        now += 10.0
        svc.propose_memory(
            tenant_id="tenant_a",
            user_id="user_1",
            memory_type="outcome_learning",
            topic_key="wind_halt_threshold",
            content="Updated rule after outcome review: halt crane at 15.0 m/s.",
            approval_id="app_new",
        )
        active = svc.list_my_memories(tenant_id="tenant_a", user_id="user_1")
        self.assertEqual(len(active), 1)
        self.assertIn("15.0 m/s", active[0].content)
        self.assertNotIn("18.0 m/s", active[0].content)

    def test_contract_write_policy_and_pre_storage_pii_scrubbing(self: unittest.TestCase) -> None:
        svc, adapter = self._make_service()  # type: ignore[attr-defined]

        # Rejects write when neither approval_id nor user_confirmed is set
        with self.assertRaises(PermissionError):
            svc.propose_memory(
                tenant_id="tenant_a",
                user_id="user_1",
                memory_type="user_preference",
                topic_key="unapproved_topic",
                content="Should fail",
                approval_id=None,
                user_confirmed=False,
            )

        # Scrubs PII BEFORE handing to the underlying adapter
        stored = svc.propose_memory(
            tenant_id="tenant_a",
            user_id="user_1",
            memory_type="approved_decision_rationale",
            topic_key="crane_lead_assignment",
            content="渡辺 剛（090-1234-5678）ではなく残業時間の少ない要員を配置する。",
            approval_id="app_100",
        )
        self.assertNotIn("渡辺 剛", stored.content)
        self.assertNotIn("090-1234-5678", stored.content)
        self.assertIn("[PII_PERSON]", stored.content)
        raw_in_adapter = adapter.list_raw(tenant_id="tenant_a")
        self.assertEqual(len(raw_in_adapter), 1)
        self.assertNotIn("渡辺 剛", raw_in_adapter[0].content)
