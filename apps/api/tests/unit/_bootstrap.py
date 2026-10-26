"""Bootstrap module for `unittest discover` so `apps/api/src`, `evals/`, and `redteam/` resolve on all filesystems."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_SRC = Path(__file__).resolve().parents[2] / "src"
for p in (str(_SRC), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


class _StatPathFinder(importlib.abc.MetaPathFinder):
    """Fallback MetaPathFinder using `Path.is_file()` when FUSE `readdir` omits subdirs."""

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname.startswith("alba_one"):
            base = _SRC
        elif fullname.startswith(("evals", "redteam")):
            base = _ROOT
        else:
            return None
        rel = fullname.replace(".", "/")
        pkg_init = base / rel / "__init__.py"
        if pkg_init.is_file():
            return importlib.util.spec_from_file_location(
                fullname,
                str(pkg_init),
                submodule_search_locations=[str(pkg_init.parent)],
            )
        mod_file = base / f"{rel}.py"
        if mod_file.is_file():
            return importlib.util.spec_from_file_location(fullname, str(mod_file))
        return None


if not any(type(f).__name__ == "_StatPathFinder" for f in sys.meta_path):
    sys.meta_path.insert(0, _StatPathFinder())
