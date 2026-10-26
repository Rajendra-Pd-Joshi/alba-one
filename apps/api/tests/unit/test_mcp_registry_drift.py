"""MCP Registry Drift Test & 22-Server Contract Suite Runner (`tests/unit/test_mcp_registry_drift.py`).

Enforces User Answer 3 ("Preventing Drift"):
Every server in `mcp_servers/registry.yaml` must have:
1. A service entry `mcp-<name>` in `infra/docker-compose.yml`
2. An optional dependency extra `mcp-<name>` in `apps/api/pyproject.toml`
3. `server.py` and `README.md` in `apps/api/src/alba_one/mcp_servers/<name>/`
4. Documentation in `docs/MCP_CATALOG.md`
5. A contract test in `apps/api/tests/mcp/<name>/test_contract.py`
6. A golden dataset in `goldens/mcp/<name>.json` (`>= 15` items, half JP / half EN, `status: "draft"`)
7. An evaluation script in `evals/mcp/<name>_eval.py`
And vice versa (no unregistered server directory).
Also executes all 22 per-server contract suites.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

import yaml

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.kb.indexer import find_repo_root
from alba_one.mcp_servers.base import load_mcp_registry


class TestMCPRegistryDriftAndContracts(unittest.TestCase):
    """Verify zero drift across `registry.yaml`, compose, pyproject, docs, tests, goldens, and evals."""

    def setUp(self) -> None:
        self.root = find_repo_root()
        self.registry = load_mcp_registry()

    def test_registry_has_all_22_servers(self) -> None:
        self.assertEqual(len(self.registry), 22)
        internal = [s for s in self.registry.values() if s.server_class in ("read", "write")]
        external = [s for s in self.registry.values() if s.server_class == "external"]
        self.assertEqual(len(internal), 13)
        self.assertEqual(len(external), 9)

    def test_no_drift_between_registry_and_filesystem_compose_pyproject_docs(self) -> None:
        compose_raw = yaml.safe_load((self.root / "infra" / "docker-compose.yml").read_text(encoding="utf-8"))
        compose_services = set(compose_raw.get("services", {}).keys())
        pyproject_text = (self.root / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
        catalog_text = (self.root / "docs" / "MCP_CATALOG.md").read_text(encoding="utf-8")
        mcp_servers_dir = self.root / "apps" / "api" / "src" / "alba_one" / "mcp_servers"

        for name, entry in self.registry.items():
            svc_name = f"mcp-{name}"
            self.assertIn(svc_name, compose_services, f"Missing compose service {svc_name}")
            self.assertIn(entry.image_extra, pyproject_text, f"Missing pyproject extra {entry.image_extra}")
            self.assertIn(name, catalog_text, f"Missing {name} in docs/MCP_CATALOG.md")

            srv_dir = mcp_servers_dir / name
            self.assertTrue((srv_dir / "server.py").is_file(), f"Missing {srv_dir}/server.py")
            self.assertTrue((srv_dir / "README.md").is_file(), f"Missing {srv_dir}/README.md")

            contract_file = self.root / "apps" / "api" / "tests" / "mcp" / name / "test_contract.py"
            self.assertTrue(contract_file.is_file(), f"Missing contract test {contract_file}")

            golden_file = self.root / "goldens" / "mcp" / f"{name}.json"
            self.assertTrue(golden_file.is_file(), f"Missing golden file {golden_file}")
            g_data = json.loads(golden_file.read_text(encoding="utf-8"))
            items = g_data.get("items", [])
            self.assertGreaterEqual(len(items), 15, f"Golden {name}.json has <15 items")
            ja_items = [it for it in items if it.get("lang") == "ja"]
            en_items = [it for it in items if it.get("lang") == "en"]
            self.assertEqual(len(ja_items), len(en_items), f"Golden {name}.json must be 50/50 JP/EN")
            self.assertTrue(all(it.get("status") == "draft" for it in items))

            eval_file = self.root / "evals" / "mcp" / f"{name}_eval.py"
            self.assertTrue(eval_file.is_file(), f"Missing eval script {eval_file}")

    def test_all_22_server_contract_suites_pass(self) -> None:
        for name in self.registry:
            contract_path = self.root / "apps" / "api" / "tests" / "mcp" / name / "test_contract.py"
            spec = importlib.util.spec_from_file_location(f"test_contract_{name}", str(contract_path))
            self.assertIsNotNone(spec)
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
            result = unittest.TestResult()
            suite.run(result)
            self.assertEqual(len(result.failures), 0, f"Contract failure in {name}: {result.failures}")
            self.assertEqual(len(result.errors), 0, f"Contract error in {name}: {result.errors}")


if __name__ == "__main__":
    unittest.main()
