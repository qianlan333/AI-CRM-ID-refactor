"""Campaign 服务 — 创建草稿、互斥分配、提交审阅、人工启动。

互斥分配是这个文件的灵魂：``allocate_campaign_members`` 把所有 Segment 命中
的 member 按 ``priority`` 排序，第一次见到的 member 才落到 ``campaign_members``，
重复命中的全部丢弃 — UNIQUE(campaign_id, member_id) 兜底保证。

整个 Campaign 的生命周期：

    propose_campaign (Agent)
        ├─ 创建 campaigns 行 (review_status=pending_review, run_status=draft)
        ├─ 创建 campaign_segments 行（带 priority）
        ├─ 创建 campaign_steps 行（每个 segment 自己的节奏）
        └─ allocate_campaign_members（互斥分配候选）

    submit_campaign_for_review (Agent)
        └─ 把 metadata 整理好，CRM 后台开始能看到这个 Campaign

    start_campaign (CRM 后台 + 人工 token)
        ├─ run_status = active
        ├─ 给每个 campaign_member 计算 next_due_at（基于 anchor_mode）
        └─ Cron 接管，按 due 推送
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable

from ...db import get_db
from ..segments.service import get_segment, increment_usage
from ..segments.sql_sandbox import fetch_member_ids


logger = logging.getLogger(__name__)


_VALID_ANCHOR_MODES = ("campaign_start_date", "member_joined_at")
_DEFAULT_SEND_TIME = "09:00"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _new_campaign_code() -> str:
    return f"camp-{uuid.uuid4().hex[:12]}"


# ---------- 创建 / 编辑 -----------------------------------------------------

def create_campaign_draft(
    *,
    campaign_code: str = "",
    display_name: str,
    intent: str,
    anchor_mode: str = "campaign_start_date",
    anchor_date: str = "",
    owner_userid: str = "",
    operator: str = "",
    session_id: str = "",
    trace_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if anchor_mode not in _VALID_ANCHOR_MODES:
        raise ValueError(f"invalid anchor_mode: {anchor_mode}")
    code = (campaign_code or "").strip() or _new_campaign_code()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM campaigns WHERE campaign_code = ?", (code,))
    if cur.fetchone():
        raise ValueError(f"campaign_code already exists: {code}")
    effective_anchor = (anchor_date or "").strip()
    if not effective_anchor and anchor_mode == "campaign_start_date":
        effective_anchor = datetime.utcnow().date().isoformat()
    cur.execute(
        """
        INSERT INTO campaigns
            (campaign_code, display_name, intent, anchor_mode, anchor_date,
             review_status, run_status, created_by_agent, created_by_session,
             trace_id, owner_userid, metadata_json)
        VALUES (?, ?, ?, ?, ?, 'draft', 'draft', ?, ?, ?, ?, ?)
        """,
        (
            code,
            (display_name or "").strip() or code,
            (intent or "").strip(),
            anchor_mode,
            effective_anchor,
            (operator or "")[:100],
            (session_id or "")[:100],
            (trace_id or "")[:100],
            (owner_userid or "")[:100],
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    db.commit()
    return get_campaign(campaign_id=int(cur.lastrowid or 0)) or {}


def add_segment_to_campaign(
    *,
    campaign_id: int,
    segment_code: str = "",
    segment_id: int | None = None,
    priority: int = 100,
    label: str = "",
) -> dict[str, Any]:
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    if str(seg.get("status") or "") != "active":
        raise ValueError(f"segment not active: {seg.get('segment_code')}")
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id FROM campaign_segments WHERE campaign_id = ? AND segment_id = ?",
        (int(campaign_id), int(seg["id"])),
    )
    existing = cur.fetchone()
    if existing:
        return {"id": int(existing["id"]), "status": "exists"}
    cur.execute(
        """
        INSERT INTO campaign_segments
            (campaign_id, segment_id, segment_code, priority, label)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(campaign_id),
            int(seg["id"]),
            str(seg["segment_code"]),
            int(priority),
            (label or "")[:200],
        ),
    )
    db.commit()
    increment_usage(segment_id=int(seg["id"]))
    return {"id": int(cur.lastrowid or 0), "segment_id": int(seg["id"])}


def add_step_to_campaign(
    *,
    campaign_id: int,
    campaign_segment_id: int,
    step_index: int,
    day_offset: int,
    content_text: str = "",
    content_payload: dict[str, Any] | None = None,
    send_time: str = _DEFAULT_SEND_TIME,
    timezone: str = "Asia/Shanghai",
    stop_on_reply: bool = True,
    skip_if_recently_touched_days: int = 0,
    agent_run_id: str = "",
) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO campaign_steps
            (campaign_id, campaign_segment_id, step_index, day_offset, send_time,
             timezone, content_text, content_payload_json, stop_on_reply,
             skip_if_recently_touched_days, agent_run_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(campaign_id),
            int(campaign_segment_id),
            int(step_index),
            int(day_offset),
            (send_time or _DEFAULT_SEND_TIME),
            (timezone or "Asia/Shanghai"),
            (content_text or "")[:4000],
            json.dumps(content_payload or {}, ensure_ascii=False),
            bool(stop_on_reply),
            int(skip_if_recently_touched_days or 0),
            (agent_run_id or "")[:100],
            _now_iso(),
        ),
    )
    db.commit()
    return {"campaign_segment_id": int(campaign_segment_id), "step_index": int(step_index)}


# ---------- 互斥分配 — 灵魂 ------------------------------------------------

def allocate_campaign_members(
    *,
    campaign_id: int,
) -> dict[str, Any]:
    """对 Campaign 下所有 segment 跑一遍 SQL，按 priority 互斥分配 member。

    保证：
    - 高优先级 segment 先扫，扫到的 member 就锁在那个 segment 上
    - 低优先级 segment 即使扫到同一个 member，UNIQUE 约束会拒绝插入
    - 整个分配在一个事务里完成（避免并发竞争）
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT trace_id, anchor_mode, anchor_date FROM campaigns WHERE id = ?",
        (int(campaign_id),),
    )
    camp_row = cur.fetchone()
    if not camp_row:
        raise LookupError("campaign not found")
    trace_id = str(camp_row["trace_id"] or "")

    cur.execute(
        """
        SELECT cs.id AS campaign_segment_id, cs.segment_id, cs.priority,
               s.segment_code, s.sql_query, s.sql_params_json, s.status
        FROM campaign_segments cs
        JOIN segments s ON s.id = cs.segment_id
        WHERE cs.campaign_id = ?
        ORDER BY cs.priority DESC, cs.id ASC
        """,
        (int(campaign_id),),
    )
    seg_rows = cur.fetchall() or []
    if not seg_rows:
        return {"campaign_id": campaign_id, "allocated": 0, "skipped_collisions": 0}

    allocated = 0
    collision = 0
    per_segment: dict[int, dict[str, int]] = {}
    seen_member_ids: set[int] = set()

    for s in seg_rows:
        if str(s["status"] or "") != "active":
            continue
        seg_id = int(s["segment_id"])
        cs_id = int(s["campaign_segment_id"])
        try:
            params = json.loads(s["sql_params_json"] or "{}")
        except (TypeError, ValueError):
            params = {}
        try:
            member_ids = fetch_member_ids(sql=str(s["sql_query"] or ""), params=params)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("segment %s sql failed during allocation: %s", s["segment_code"], exc)
            continue
        bucket = per_segment.setdefault(cs_id, {"matched": 0, "allocated": 0, "skipped": 0})
        bucket["matched"] += len(member_ids)
        for mid in member_ids:
            if mid in seen_member_ids:
                collision += 1
                bucket["skipped"] += 1
                continue
            # 取 external_contact_id 兜底
            cur.execute(
                "SELECT external_contact_id FROM automation_member WHERE id = ?",
                (int(mid),),
            )
            mr = cur.fetchone()
            external = str(mr["external_contact_id"] or "") if mr else ""
            try:
                cur.execute(
                    """
                    INSERT INTO campaign_members
                        (campaign_id, campaign_segment_id, segment_id, member_id,
                         external_contact_id, status, current_step_index,
                         trace_id)
                    VALUES (?, ?, ?, ?, ?, 'pending', -1, ?)
                    """,
                    (
                        int(campaign_id),
                        cs_id,
                        seg_id,
                        int(mid),
                        external,
                        trace_id,
                    ),
                )
                seen_member_ids.add(mid)
                allocated += 1
                bucket["allocated"] += 1
            except Exception as exc:
                # UNIQUE 约束兜底（极端并发情况下）
                logger.debug("allocate skip mid=%s reason=%s", mid, exc)
                collision += 1
                bucket["skipped"] += 1
    db.commit()
    return {
        "campaign_id": campaign_id,
        "allocated": allocated,
        "skipped_collisions": collision,
        "per_segment": per_segment,
        "trace_id": trace_id,
    }


# ---------- 状态机 ----------------------------------------------------------

def submit_campaign_for_review(*, campaign_id: int, operator: str = "") -> dict[str, Any]:
    """Agent 端把方案打磨好，提交 CRM 端审阅 — review_status: draft → pending_review。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET review_status = 'pending_review', updated_at = ? "
        "WHERE id = ? AND review_status IN ('draft','pending_review')",
        (_now_iso(), int(campaign_id)),
    )
    db.commit()
    if not cur.rowcount:
        raise RuntimeError("campaign not in submittable state")
    logger.info("campaign %s submitted for review by %s", campaign_id, operator)
    return get_campaign(campaign_id=campaign_id) or {}


def start_campaign(
    *,
    campaign_id: int,
    human_approver: str,
    approval_token_value: str,
) -> dict[str, Any]:
    """CRM 后台 + 人工 token → Campaign 真正启动，调度器接管。"""
    from ..cloud_orchestrator import approval_token

    if not approval_token_value:
        raise PermissionError("approval_token is required")
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        raise LookupError("campaign not found")
    if camp.get("run_status") in ("active", "paused", "finished"):
        return camp
    token_check = approval_token.consume_token(
        token=approval_token_value,
        plan_id=str(camp["campaign_code"]),
        consumer=human_approver,
        scope="start_campaign",
    )
    if not token_check.get("ok"):
        raise PermissionError(f"approval_token rejected: {token_check.get('reason')}")
    db = get_db()
    cur = db.cursor()
    started_at = _now_iso()
    cur.execute(
        """
        UPDATE campaigns SET
            review_status = 'approved', run_status = 'active',
            approved_by = ?, approved_at = ?, started_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            str(human_approver)[:100],
            started_at,
            started_at,
            started_at,
            int(campaign_id),
        ),
    )
    # 给所有 campaign_member 计算 anchor_date + 第一步 next_due_at
    anchor_mode = str(camp.get("anchor_mode") or "campaign_start_date")
    if anchor_mode == "campaign_start_date":
        anchor_date = str(camp.get("anchor_date") or "") or datetime.utcnow().date().isoformat()
        cur.execute(
            "UPDATE campaign_members SET anchor_date = ?, joined_at = ? WHERE campaign_id = ?",
            (anchor_date, started_at, int(campaign_id)),
        )
    else:
        # member_joined_at — 已经在 allocate 时设置 joined_at；anchor_date = joined_at 当天
        cur.execute(
            "UPDATE campaign_members SET anchor_date = substr(joined_at, 1, 10) "
            "WHERE campaign_id = ?",
            (int(campaign_id),),
        )
    # 第一步 due 时间 = anchor_date + day_offset @ send_time
    cur.execute(
        """
        SELECT cm.id AS cm_id, cm.campaign_segment_id, cm.anchor_date
        FROM campaign_members cm
        WHERE cm.campaign_id = ? AND cm.status = 'pending'
        """,
        (int(campaign_id),),
    )
    member_rows = cur.fetchall() or []
    for mr in member_rows:
        cur.execute(
            """
            SELECT day_offset, send_time
            FROM campaign_steps
            WHERE campaign_segment_id = ?
            ORDER BY step_index ASC LIMIT 1
            """,
            (int(mr["campaign_segment_id"]),),
        )
        step_row = cur.fetchone()
        if not step_row:
            continue
        try:
            base_date = datetime.fromisoformat(str(mr["anchor_date"] or "")[:10])
        except ValueError:
            base_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        send_time = str(step_row["send_time"] or _DEFAULT_SEND_TIME)
        try:
            hour_str, minute_str = send_time.split(":")[:2]
            base_date = base_date.replace(hour=int(hour_str), minute=int(minute_str))
        except ValueError:
            pass
        due_dt = base_date + timedelta(days=int(step_row["day_offset"] or 0))
        cur.execute(
            "UPDATE campaign_members SET next_due_at = ?, current_step_index = -1 WHERE id = ?",
            (due_dt.isoformat(), int(mr["cm_id"])),
        )
    db.commit()
    logger.info("campaign %s started by %s", campaign_id, human_approver)
    return get_campaign(campaign_id=campaign_id) or {}


def pause_campaign(*, campaign_id: int, reason: str = "") -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET run_status = 'paused', paused_at = ?, paused_reason = ?, updated_at = ? "
        "WHERE id = ? AND run_status = 'active'",
        (_now_iso(), str(reason)[:200], _now_iso(), int(campaign_id)),
    )
    db.commit()
    return get_campaign(campaign_id=campaign_id) or {}


def resume_campaign(*, campaign_id: int) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET run_status = 'active', paused_at = '', paused_reason = '', updated_at = ? "
        "WHERE id = ? AND run_status = 'paused'",
        (_now_iso(), int(campaign_id)),
    )
    db.commit()
    return get_campaign(campaign_id=campaign_id) or {}


def reject_campaign(*, campaign_id: int, reason: str = "") -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET review_status = 'rejected', run_status = 'cancelled', "
        "paused_reason = ?, updated_at = ? WHERE id = ?",
        (str(reason)[:200], _now_iso(), int(campaign_id)),
    )
    db.commit()
    return (cur.rowcount or 0) > 0


def finish_campaign(*, campaign_id: int) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET run_status = 'finished', finished_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), int(campaign_id)),
    )
    db.commit()
    return get_campaign(campaign_id=campaign_id) or {}


# ---------- 查询 ------------------------------------------------------------

def get_campaign(*, campaign_code: str = "", campaign_id: int | None = None) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    if campaign_id is not None:
        cur.execute("SELECT * FROM campaigns WHERE id = ?", (int(campaign_id),))
    elif campaign_code:
        cur.execute("SELECT * FROM campaigns WHERE campaign_code = ?", (str(campaign_code),))
    else:
        return None
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        d["metadata"] = {}
    try:
        d["stats"] = json.loads(d.get("stats_json") or "{}")
    except (TypeError, ValueError):
        d["stats"] = {}
    return d


def list_campaigns(
    *,
    review_status: str = "",
    run_status: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    where = ["1=1"]
    args: list[Any] = []
    if review_status:
        where.append("review_status = ?")
        args.append(review_status)
    if run_status:
        where.append("run_status = ?")
        args.append(run_status)
    args.append(int(limit))
    cur.execute(
        f"""
        SELECT id, campaign_code, display_name, intent, anchor_mode, anchor_date,
               review_status, run_status, created_by_agent, started_at, finished_at,
               created_at, updated_at
        FROM campaigns WHERE {' AND '.join(where)}
        ORDER BY id DESC LIMIT ?
        """,
        tuple(args),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def assemble_campaign_overview(*, campaign_id: int) -> dict[str, Any]:
    """聚合一个 Campaign 的全部信息：定义 + 分层 + 节奏 + 成员统计。给审阅页用。"""
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        return {}
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cs.id AS campaign_segment_id, cs.segment_id, cs.segment_code,
               cs.priority, cs.label,
               s.display_name AS segment_name, s.cached_headcount,
               (SELECT COUNT(*) FROM campaign_members cm
                  WHERE cm.campaign_segment_id = cs.id) AS allocated_count
        FROM campaign_segments cs
        JOIN segments s ON s.id = cs.segment_id
        WHERE cs.campaign_id = ?
        ORDER BY cs.priority DESC, cs.id ASC
        """,
        (int(campaign_id),),
    )
    segments = []
    for row in cur.fetchall() or []:
        cs_id = int(row["campaign_segment_id"])
        cur.execute(
            """
            SELECT step_index, day_offset, send_time, content_text, stop_on_reply,
                   skip_if_recently_touched_days
            FROM campaign_steps
            WHERE campaign_segment_id = ?
            ORDER BY step_index ASC
            """,
            (cs_id,),
        )
        steps = [dict(r) for r in (cur.fetchall() or [])]
        d = dict(row)
        d["steps"] = steps
        segments.append(d)
    cur.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM campaign_members
        WHERE campaign_id = ?
        GROUP BY status
        """,
        (int(campaign_id),),
    )
    member_status = {str(r["status"] or "unknown"): int(r["c"] or 0) for r in (cur.fetchall() or [])}
    return {
        "campaign": camp,
        "segments": segments,
        "member_status_counts": member_status,
        "total_members": sum(member_status.values()),
    }


# ---------- 一站式 ---------------------------------------------------------

def propose_campaign(
    *,
    display_name: str,
    intent: str,
    segments: list[dict[str, Any]],
    anchor_mode: str = "campaign_start_date",
    anchor_date: str = "",
    owner_userid: str = "",
    operator: str = "",
    session_id: str = "",
    trace_id: str = "",
    auto_allocate: bool = True,
) -> dict[str, Any]:
    """Agent 一次调用搞定整个 Campaign 草稿。

    ``segments`` 形如：
    [
      {
        "segment_code": "silent_30d_no_inbound",
        "priority": 200,
        "label": "沉默-重点",
        "steps": [
          {"step_index":0, "day_offset":0, "send_time":"09:00", "content_text":"..."},
          {"step_index":1, "day_offset":3, "send_time":"09:00", "content_text":"..."},
        ]
      },
      ...
    ]

    会按 priority 降序去做互斥分配（高优先级先抢人）。
    """
    if not segments:
        raise ValueError("at least one segment is required")
    camp = create_campaign_draft(
        display_name=display_name,
        intent=intent,
        anchor_mode=anchor_mode,
        anchor_date=anchor_date,
        owner_userid=owner_userid,
        operator=operator,
        session_id=session_id,
        trace_id=trace_id,
    )
    camp_id = int(camp["id"])
    for seg_spec in segments:
        added = add_segment_to_campaign(
            campaign_id=camp_id,
            segment_code=str(seg_spec.get("segment_code") or ""),
            priority=int(seg_spec.get("priority") or 100),
            label=str(seg_spec.get("label") or ""),
        )
        cs_id = int(added["id"])
        for step in (seg_spec.get("steps") or []):
            add_step_to_campaign(
                campaign_id=camp_id,
                campaign_segment_id=cs_id,
                step_index=int(step.get("step_index") or 0),
                day_offset=int(step.get("day_offset") or 0),
                send_time=str(step.get("send_time") or _DEFAULT_SEND_TIME),
                timezone=str(step.get("timezone") or "Asia/Shanghai"),
                content_text=str(step.get("content_text") or ""),
                stop_on_reply=bool(step.get("stop_on_reply", True)),
                skip_if_recently_touched_days=int(step.get("skip_if_recently_touched_days") or 0),
                agent_run_id=str(step.get("agent_run_id") or ""),
            )
    allocation = {}
    if auto_allocate:
        allocation = allocate_campaign_members(campaign_id=camp_id)
    overview = assemble_campaign_overview(campaign_id=camp_id)
    overview["allocation"] = allocation
    return overview


__all__ = [
    "add_segment_to_campaign",
    "add_step_to_campaign",
    "allocate_campaign_members",
    "assemble_campaign_overview",
    "create_campaign_draft",
    "finish_campaign",
    "get_campaign",
    "list_campaigns",
    "pause_campaign",
    "propose_campaign",
    "reject_campaign",
    "resume_campaign",
    "start_campaign",
    "submit_campaign_for_review",
]
