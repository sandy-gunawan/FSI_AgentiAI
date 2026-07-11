"""Shared JSON data loader for all mock surrounding systems."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent


@lru_cache
def load(name: str) -> Any:
    """Load a dataset by file name (e.g. 'customers.json'). Cached in-process."""
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: python mock_services/data/seed.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))
