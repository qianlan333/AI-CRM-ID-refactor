"""Shared helpers for the marketing_automation package.

Extracted from repo.py (阶段 5.2 marketing_automation repo cleanup).

Private to the marketing_automation package; names stay underscore-prefixed
and are explicitly re-exported via ``__all__``. Callers should import via
explicit names (`from ._repo_helpers import _normalized_text, ...`) rather
than star imports, to avoid ruff F405 warnings if/when ruff is configured
for this domain.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts as _db_fetchall_dicts
from ...db.helpers import fetchone_dict as _db_fetchone_dict
from ...db.helpers import placeholders as _db_placeholders
from ...infra.json_utils import json_dumps


def _db_bool(value: bool) -> bool:
    return bool(value)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    return _db_fetchone_dict(get_db(), sql, params)


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return _db_fetchall_dicts(get_db(), sql, params)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_text_list(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    return [text for item in values or () if (text := _normalized_text(item))]


def _placeholders(values: list[Any] | tuple[Any, ...]) -> str:
    return _db_placeholders(values)


def _nullable_timestamp_text(value: Any) -> str | None:
    normalized = _normalized_text(value)
    return normalized or None


def _json_dumps(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


__all__ = [
    "_db_bool",
    "_fetchone_dict",
    "_fetchall_dicts",
    "_normalized_text",
    "_normalized_text_list",
    "_placeholders",
    "_nullable_timestamp_text",
    "_json_dumps",
]
