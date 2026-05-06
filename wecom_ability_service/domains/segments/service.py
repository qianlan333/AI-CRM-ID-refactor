"""Segments 服务 — 注册表 CRUD + 人数缓存刷新 + 系统默认分层 seed。

API 风格全部走"显式参数 + 单一职责"，方便外部 Agent 通过 MCP 工具直接调。
所有写操作都要求带 ``operator``（人或 Agent 标识）便于审计。

CRM 前端**不开放**新建/编辑入口；这里所有写函数都只服务 MCP 工具调用。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Iterable

from ...db import get_db
from .sql_sandbox import (
    SqlSandboxError,
    fetch_member_ids,
    run_segment_query,
    validate_segment_sql,
)


logger = logging.getLogger(__name__)


_DEFAULT_SAMPLE_SIZE = 20


def _normalize_code(code: str) -> str:
    text = (code or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or f"seg_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def list_segments(
    *,
    status: str = "active",
    source_type: str = "",
    keyword: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """列出 Segment（默认只返回 active；归档的要主动指定 status='archived'）。"""
    db = get_db()
    cur = db.cursor()
    where = ["1=1"]
    args: list[Any] = []
    if status:
        where.append("status = ?")
        args.append(status)
    if source_type:
        where.append("source_type = ?")
        args.append(source_type)
    kw = (keyword or "").strip()
    if kw:
        where.append("(segment_code LIKE ? OR display_name LIKE ? OR description LIKE ?)")
        args.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    args.append(int(limit))
    cur.execute(
        f"""
        SELECT id, segment_code, display_name, description, source_type, status,
               version, cached_headcount, last_refreshed_at, last_refresh_error,
               usage_count, created_by_agent, created_at, updated_at, tags_json
        FROM segments
        WHERE {' AND '.join(where)}
        ORDER BY usage_count DESC, updated_at DESC, id DESC
        LIMIT ?
        """,
        tuple(args),
    )
    rows = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d.pop("tags_json") or "[]")
        except (TypeError, ValueError):
            d["tags"] = []
        out.append(d)
    return out


def get_segment(*, segment_code: str = "", segment_id: int | None = None) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    if segment_id is not None:
        cur.execute("SELECT * FROM segments WHERE id = ?", (int(segment_id),))
    elif segment_code:
        cur.execute("SELECT * FROM segments WHERE segment_code = ?", (str(segment_code),))
    else:
        return None
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["sql_params"] = json.loads(d.get("sql_params_json") or "{}")
    except (TypeError, ValueError):
        d["sql_params"] = {}
    try:
        d["cached_sample"] = json.loads(d.get("cached_sample_json") or "[]")
    except (TypeError, ValueError):
        d["cached_sample"] = []
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, ValueError):
        d["tags"] = []
    return d


def create_segment(
    *,
    segment_code: str,
    display_name: str,
    description: str = "",
    sql_query: str,
    sql_params: dict[str, Any] | None = None,
    source_type: str = "ai_generated",
    tags: Iterable[str] = (),
    operator: str = "",
    session_id: str = "",
    activate: bool = False,
) -> dict[str, Any]:
    """Agent 创建一个新分层。强制 SQL 沙箱校验 + 试跑一次拿到人数 / 样本。"""
    code = _normalize_code(segment_code)
    name = (display_name or "").strip() or code
    ok, reason = validate_segment_sql(sql_query)
    if not ok:
        raise SqlSandboxError(f"validate_failed:{reason}")
    # 试跑 — 验证 SQL 真能查到 member_id
    try:
        first_run = run_segment_query(sql=sql_query, params=sql_params or {})
    except SqlSandboxError as exc:
        raise SqlSandboxError(f"dry_run_failed:{exc}") from exc
    headcount = int(first_run["row_count"])
    sample = first_run["rows"][:_DEFAULT_SAMPLE_SIZE]

    db = get_db()
    cur = db.cursor()
    # 看 code 是否已存在
    cur.execute("SELECT id FROM segments WHERE segment_code = ?", (code,))
    if cur.fetchone():
        raise ValueError(f"segment_code already exists: {code}")
    cur.execute(
        """
        INSERT INTO segments
            (segment_code, display_name, description, source_type, sql_query,
             sql_params_json, status, version, created_by_agent, created_by_session,
             cached_headcount, cached_sample_json, last_refreshed_at, tags_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            name,
            (description or "").strip(),
            source_type or "ai_generated",
            sql_query,
            json.dumps(sql_params or {}, ensure_ascii=False),
            "active" if activate else "draft",
            (operator or "")[:100],
            (session_id or "")[:100],
            headcount,
            json.dumps(sample, ensure_ascii=False, default=str)[:8000],
            _now_iso(),
            json.dumps(list(tags or []), ensure_ascii=False),
        ),
    )
    db.commit()
    new_id = int(cur.lastrowid or 0)
    logger.info("segment created code=%s id=%s headcount=%d", code, new_id, headcount)
    return get_segment(segment_id=new_id) or {}


def update_segment(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
    display_name: str | None = None,
    description: str | None = None,
    sql_query: str | None = None,
    sql_params: dict[str, Any] | None = None,
    status: str | None = None,
    tags: Iterable[str] | None = None,
    operator: str = "",
) -> dict[str, Any]:
    """更新分层；改了 SQL 就重新校验 + 重新跑一次拿头部数据。"""
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    sets: dict[str, Any] = {}
    if display_name is not None:
        sets["display_name"] = (display_name or "").strip()
    if description is not None:
        sets["description"] = (description or "").strip()
    if tags is not None:
        sets["tags_json"] = json.dumps(list(tags), ensure_ascii=False)
    if status is not None:
        if status not in ("draft", "active", "archived"):
            raise ValueError(f"invalid status: {status}")
        sets["status"] = status
    if sql_query is not None:
        ok, reason = validate_segment_sql(sql_query)
        if not ok:
            raise SqlSandboxError(f"validate_failed:{reason}")
        sets["sql_query"] = sql_query
        sets["sql_params_json"] = json.dumps(sql_params or {}, ensure_ascii=False)
        sets["version"] = int(seg.get("version") or 1) + 1
        # 重跑
        run = run_segment_query(sql=sql_query, params=sql_params or {})
        sets["cached_headcount"] = int(run["row_count"])
        sets["cached_sample_json"] = json.dumps(run["rows"][:_DEFAULT_SAMPLE_SIZE], ensure_ascii=False, default=str)[:8000]
        sets["last_refreshed_at"] = _now_iso()
        sets["last_refresh_error"] = ""
    if not sets:
        return seg
    sets["updated_at"] = _now_iso()
    db = get_db()
    cur = db.cursor()
    placeholders = ",".join([f"{k} = ?" for k in sets.keys()])
    values = list(sets.values()) + [int(seg["id"])]
    cur.execute(f"UPDATE segments SET {placeholders} WHERE id = ?", tuple(values))
    db.commit()
    return get_segment(segment_id=int(seg["id"])) or {}


def archive_segment(*, segment_code: str = "", segment_id: int | None = None) -> bool:
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE segments SET status = 'archived', updated_at = ? WHERE id = ?",
        (_now_iso(), int(seg["id"])),
    )
    db.commit()
    return True


def preview_segment_members(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """实时跑一次 SQL，返回前 N 条样本 + 实时人数。**不更新缓存。**"""
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    res = run_segment_query(
        sql=str(seg.get("sql_query") or ""),
        params=seg.get("sql_params") or {},
    )
    return {
        "segment_code": seg["segment_code"],
        "headcount": int(res["row_count"]),
        "sample": res["rows"][: max(1, min(int(limit), 200))],
        "elapsed_ms": int(res.get("elapsed_ms") or 0),
    }


def refresh_segment_cache(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
) -> dict[str, Any]:
    """跑一次 SQL，把人数 / 样本写回缓存。供定时刷新调用。"""
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    try:
        res = run_segment_query(
            sql=str(seg.get("sql_query") or ""),
            params=seg.get("sql_params") or {},
        )
        headcount = int(res["row_count"])
        sample = res["rows"][:_DEFAULT_SAMPLE_SIZE]
        error_text = ""
    except SqlSandboxError as exc:
        headcount = 0
        sample = []
        error_text = str(exc)[:300]
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE segments SET
            cached_headcount = ?,
            cached_sample_json = ?,
            last_refreshed_at = ?,
            last_refresh_error = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            headcount,
            json.dumps(sample, ensure_ascii=False, default=str)[:8000],
            _now_iso(),
            error_text,
            _now_iso(),
            int(seg["id"]),
        ),
    )
    db.commit()
    return {
        "segment_code": seg["segment_code"],
        "headcount": headcount,
        "error": error_text,
    }


def increment_usage(*, segment_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE segments SET usage_count = usage_count + 1, updated_at = ? WHERE id = ?",
        (_now_iso(), int(segment_id)),
    )
    db.commit()


# ---------- 系统默认分层 ----------------------------------------------------

_SYSTEM_SEED_SEGMENTS = (
    {
        "segment_code": "pool_pending_questionnaire",
        "display_name": "池子 · 待填问卷",
        "description": "automation_member.current_audience_code = pending_questionnaire",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE current_audience_code = 'pending_questionnaire'"
        ),
        "tags": ["pool", "system"],
    },
    {
        "segment_code": "pool_operating",
        "display_name": "池子 · 运营中",
        "description": "automation_member.current_audience_code = operating",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE current_audience_code = 'operating'"
        ),
        "tags": ["pool", "system"],
    },
    {
        "segment_code": "pool_converted",
        "display_name": "池子 · 已转化",
        "description": "automation_member.current_audience_code = converted",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE current_audience_code = 'converted'"
        ),
        "tags": ["pool", "system"],
    },
    {
        "segment_code": "pool_active_focus",
        "display_name": "池子 · 活跃-重点",
        "description": "automation_member.current_pool = active_focus",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE current_pool = 'active_focus'"
        ),
        "tags": ["pool", "system"],
    },
    {
        "segment_code": "pool_inactive_focus",
        "display_name": "池子 · 不活跃-重点",
        "description": "automation_member.current_pool = inactive_focus",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE current_pool = 'inactive_focus'"
        ),
        "tags": ["pool", "system"],
    },
    {
        "segment_code": "behavior_msg_lt_2",
        "display_name": "行为画像 · 消息 < 2 条",
        "description": "automation_member.behavior_tier_key = msg_lt_2",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE behavior_tier_key = 'msg_lt_2'"
        ),
        "tags": ["behavior", "system"],
    },
    {
        "segment_code": "behavior_msg_2_to_9",
        "display_name": "行为画像 · 消息 2~9 条",
        "description": "automation_member.behavior_tier_key = msg_2_to_9",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE behavior_tier_key = 'msg_2_to_9'"
        ),
        "tags": ["behavior", "system"],
    },
    {
        "segment_code": "behavior_msg_gte_10",
        "display_name": "行为画像 · 消息 ≥ 10 条",
        "description": "automation_member.behavior_tier_key = msg_gte_10",
        "sql_query": (
            "SELECT id AS member_id, external_contact_id "
            "FROM automation_member WHERE behavior_tier_key = 'msg_gte_10'"
        ),
        "tags": ["behavior", "system"],
    },
    {
        "segment_code": "silent_30d_no_inbound",
        "display_name": "沉默 · 30 天无回复",
        "description": "30 天内有过 outbound 且最近一次 outbound 之后无 inbound 的成员",
        # 直接走 automation_member 不走视图（视图语法在 PG 上需要严格类型；这里
        # 用纯字符串比较，两边都通用）
        "sql_query": (
            "SELECT m.id AS member_id, m.external_contact_id "
            "FROM automation_member m "
            "WHERE m.last_ai_push_at <> ''"
        ),
        "tags": ["silent", "system"],
    },
)


def seed_default_segments() -> int:
    """启动期把 9 个系统默认分层写库（已存在则不覆盖）。返回新增条数。"""
    written = 0
    for spec in _SYSTEM_SEED_SEGMENTS:
        existing = get_segment(segment_code=spec["segment_code"])
        if existing:
            continue
        try:
            create_segment(
                segment_code=spec["segment_code"],
                display_name=spec["display_name"],
                description=spec["description"],
                sql_query=spec["sql_query"],
                source_type="system_default",
                tags=spec.get("tags") or [],
                operator="system",
                activate=True,
            )
            written += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("seed segment failed code=%s err=%s", spec["segment_code"], exc)
    return written


__all__ = [
    "archive_segment",
    "create_segment",
    "get_segment",
    "increment_usage",
    "list_segments",
    "preview_segment_members",
    "refresh_segment_cache",
    "seed_default_segments",
    "update_segment",
]
