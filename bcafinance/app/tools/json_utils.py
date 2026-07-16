"""Robust JSON extraction from LLM agent output.

Foundry agents are instructed to return raw JSON, but models sometimes wrap it in
```json fences``` or add stray prose. This strips those and parses safely.
"""
from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json(text: str) -> dict:
    """Best-effort parse of a JSON object from model text. Returns {} on failure."""
    if not text:
        return {}
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    # Narrow to the outermost {...} if there is surrounding prose.
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return {}
