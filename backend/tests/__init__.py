"""Pressure Out backend application package."""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys

__version__ = "0.3.0"


class _DirectStatPathFinder(importlib.abc.MetaPathFinder):
    """Fallback MetaPathFinder that uses os.stat/isfile directly for 9p virtual filesystems."""

    def find_spec(self, fullname: str, path=None, target=None):
        parts = fullname.split(".")
        search_roots = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
        for root in search_roots:
            candidate_pkg = os.path.join(root, *parts, "__init__.py")
            if os.path.isfile(candidate_pkg):
                return importlib.util.spec_from_file_location(
                    fullname,
                    candidate_pkg,
                    submodule_search_locations=[os.path.dirname(candidate_pkg)],
                )
            candidate_mod = os.path.join(root, *parts) + ".py"
            if os.path.isfile(candidate_mod):
                return importlib.util.spec_from_file_location(fullname, candidate_mod)
        return None


if not any(type(f).__name__ == "_DirectStatPathFinder" for f in sys.meta_path):
    sys.meta_path.insert(0, _DirectStatPathFinder())
