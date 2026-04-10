"""Shared bootstrap for all scripts.

Usage at the top of every script::

    from scripts._bootstrap import REPO_ROOT  # noqa: F401  (side-effect: adds REPO_ROOT to sys.path)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
