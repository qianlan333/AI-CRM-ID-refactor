"""Shared helpers for customer_pulse/repo.py and split sibling modules.

Extracted from repo.py (阶段 5.1 customer_pulse repo cleanup).

Private to the customer_pulse package — names stay underscore-prefixed and are
explicitly re-exported via ``__all__`` so callers can ``from ._repo_helpers
import *`` and pick them all up.
"""

from __future__ import annotations

import json
from typing import Any

from ...db import get_db
from .access import customer_pulse_default_tenant_key

CUSTOMER_PULSE_DEFAULT_TENANT_KEY = customer_pulse_default_tenant_key()


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_storage(value: Any, *, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text or default
    # PG JSONB 列读出来已是 dict/list，里面可能塞着 datetime（来自 TIMESTAMPTZ
    # 列 join 进 JSON 聚合后回写的场景）。``json.dumps`` 默认不认 datetime —
    # 用 ``default=str`` 兜底，输出 ISO 8601 字符串。
    return json.dumps(value, ensure_ascii=False, default=str)


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _required_tenant_key(tenant_key: Any) -> str:
    normalized = _normalized_text(tenant_key)
    if normalized:
        return normalized
    raise ValueError("customer_pulse repo requires explicit tenant_key")




__all__ = [
    "CUSTOMER_PULSE_DEFAULT_TENANT_KEY",
    "_normalized_text",
    "_json_storage",
    "_fetchall_dict",
    "_fetchone_dict",
    "_required_tenant_key",
]
