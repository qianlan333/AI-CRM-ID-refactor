"""Campaign step payload normalization helpers."""
from __future__ import annotations

import json
from typing import Any


def parse_step_payload(raw: Any) -> dict[str, Any]:
    """Return a mutable payload dict from PG jsonb dicts or legacy JSON strings."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def normalize_int_list(values: Any, *, limit: int | None = None) -> list[int]:
    items: list[int] = []
    for raw in values or []:
        try:
            items.append(int(raw))
        except (TypeError, ValueError):
            continue
    return items[:limit] if limit is not None else items


def normalize_str_list(values: Any, *, limit: int | None = None) -> list[str]:
    items: list[str] = []
    for raw in values or []:
        if raw is None:
            continue
        item = str(raw).strip()
        if item:
            items.append(item)
    return items[:limit] if limit is not None else items
