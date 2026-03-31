
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .db import get_db
from .services import QUESTIONNAIRE_TYPES

def _utc_now_str(fmt: str) -> str:
    return datetime.now(timezone.utc).strftime(fmt)

def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

def _json_array(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []

def _dedupe_strings(values: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped

def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def _normalize_float(value: Any, field_name: str, *, allow_none: bool = False) -> float | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc

def _normalize_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sort_order must be an integer") from exc

def _normalize_required_integer(value: Any, field_name: str, *, allow_none: bool = False) -> int | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc

def _validate_tag_codes_payload(value: Any, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return _dedupe_strings(value)

def _slugify_questionnaire(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not base:
        timestamp = _utc_now_str("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        base = f"q-{timestamp}-{suffix}"
    return base[:120]

def _questionnaire_exists_by_slug(slug: str, *, exclude_id: int | None = None) -> bool:
    sql = "SELECT id FROM questionnaires WHERE slug = ?"
    params: list[Any] = [slug]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_id))
    row = get_db().execute(sql, tuple(params)).fetchone()
    return row is not None

def _normalize_tag_codes(value: Any) -> list[str]:
    # The questionnaire schema keeps the historical field name `tag_codes`,
    # but values are treated end-to-end as the exact WeCom tag identifiers
    # accepted by externalcontact/mark_tag.
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            return _dedupe_strings(_json_array(candidate))
        if "/" in candidate:
            return _dedupe_strings(candidate.split("/"))
        if "," in candidate:
            return _dedupe_strings(candidate.split(","))
        return _dedupe_strings([candidate])
    if isinstance(value, (list, tuple)):
        return _dedupe_strings(list(value))
    return []
