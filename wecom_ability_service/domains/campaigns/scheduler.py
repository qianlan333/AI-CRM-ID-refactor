"""Campaign 调度引擎 — 把 due 的 campaign_member 推一步。

每个 ``campaign_member`` 是一条独立的旅程。Cron 调用 ``process_due_campaign_members``
扫所有 ``status=pending`` 且 ``next_due_at <= now`` 的成员，对每个成员：

1. claim — 改 status='running'（乐观锁防并发重复处理）
2. 取下一步 step → 拼内容 → 走频次预算 → 调发送管道
3. 写 ``automation_touch_delivery_log``（继承 trace_id）
4. 推进 ``current_step_index`` → 算下一步 ``next_due_at`` 或标记完成

回复处理：``register_member_reply`` 在 reply_monitor 收到 inbound 时被调，
对应 campaign_member 走 ``stop_on_reply`` 逻辑。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from ...db import get_db


logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _due_at_for_step(*, anchor_date: str, day_offset: int, send_time: str) -> str:
    try:
        base = datetime.fromisoformat((anchor_date or "")[:10])
    except ValueError:
        base = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        h, m = (send_time or "09:00").split(":")[:2]
        base = base.replace(hour=int(h), minute=int(m))
    except ValueError:
        pass
    return (base + timedelta(days=int(day_offset))).isoformat()


def _claim_due_member(*, member_row_id: int) -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaign_members SET status = 'running', updated_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (_now_iso(), int(member_row_id)),
    )
    db.commit()
    return (cur.rowcount or 0) > 0


def _next_step(
    *, campaign_segment_id: int, after_step_index: int
) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, step_index, day_offset, send_time, content_text,
               content_payload_json, stop_on_reply, skip_if_recently_touched_days
        FROM campaign_steps
        WHERE campaign_segment_id = ? AND step_index > ?
        ORDER BY step_index ASC LIMIT 1
        """,
        (int(campaign_segment_id), int(after_step_index)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _send_step_to_member(
    *,
    campaign: dict[str, Any],
    member: dict[str, Any],
    step: dict[str, Any],
) -> dict[str, Any]:
    """实际把这一步推给一个 member。复用 dispatch_wecom_task + 频次预算。"""
    from ..marketing_automation import frequency_budget_service
    from ..marketing_automation.service import DEFAULT_AUTOMATION_OWNER_USERID
    from ..marketing_automation.service import dispatch_wecom_task

    external = str(member.get("external_contact_id") or "")
    member_id = int(member.get("member_id") or 0)
    if not external:
        return {"ok": False, "reason": "missing_external_contact_id"}

    # 频次预算
    verdict = frequency_budget_service.check_member_budget(
        member_id=member_id,
        external_contact_id=external,
        channels=("wecom_private", "ai_initiated"),
        program_codes=("campaign",),
    )
    if not verdict.allowed:
        return {"ok": False, "reason": verdict.skip_reason}

    owner_userid = str(campaign.get("owner_userid") or "") or DEFAULT_AUTOMATION_OWNER_USERID
    request_payload = {
        "sender": owner_userid,
        "external_userid": [external],
        "text": {"content": str(step.get("content_text") or "")},
        "attachments": [],
    }
    try:
        wecom_result = dispatch_wecom_task(
            "private_message",
            "create_private_message_task",
            request_payload,
        )
        task_id = int(wecom_result.get("task_id") or 0)
    except Exception as exc:
        logger.exception("campaign send failed: %s", exc)
        return {"ok": False, "reason": f"dispatch_error:{exc}"}

    trace_id = str(member.get("trace_id") or campaign.get("trace_id") or "")
    db = get_db()
    cur = db.cursor()
    # 写 touch delivery log（沿用 program_code='campaign'）
    cur.execute(
        """
        INSERT INTO automation_touch_delivery_log
            (program_code, touch_surface, rule_key, member_id,
             external_contact_id, status, detail, metadata_json, trace_id, sent_at)
        VALUES (?, 'campaign_step', ?, ?, ?, 'sent', ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        (
            f"campaign:{campaign.get('campaign_code')}",
            f"step:{step.get('step_index')}",
            int(member_id) if member_id else None,
            external,
            f"campaign_step task_id={task_id}",
            json.dumps(
                {
                    "campaign_id": campaign.get("id"),
                    "campaign_segment_id": member.get("campaign_segment_id"),
                    "step_index": step.get("step_index"),
                    "wecom_task_id": task_id,
                },
                ensure_ascii=False,
            ),
            trace_id,
            _now_iso(),
        ),
    )
    db.commit()
    # 写频次预算消耗
    try:
        frequency_budget_service.record_consumption(
            member_id=member_id or None,
            external_contact_id=external,
            channels=("wecom_private", "ai_initiated"),
            program_codes=("campaign",),
            source_kind="campaign_step",
            source_id=str(step.get("id") or ""),
            trace_id=trace_id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("record_consumption failed: %s", exc)
    return {"ok": True, "task_id": task_id}


def progress_member_after_send(
    *,
    member_row_id: int,
    step: dict[str, Any],
    send_result: dict[str, Any],
) -> None:
    """发完后推进 — 计算下一步 due，或者标记成员完成 / 失败。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cm.id, cm.campaign_id, cm.campaign_segment_id, cm.anchor_date,
               c.run_status
        FROM campaign_members cm
        JOIN campaigns c ON c.id = cm.campaign_id
        WHERE cm.id = ?
        """,
        (int(member_row_id),),
    )
    row = cur.fetchone()
    if not row:
        return
    if str(row["run_status"] or "") != "active":
        cur.execute(
            "UPDATE campaign_members SET status = 'paused', updated_at = ? WHERE id = ?",
            (_now_iso(), int(member_row_id)),
        )
        db.commit()
        return
    next_step = _next_step(
        campaign_segment_id=int(row["campaign_segment_id"]),
        after_step_index=int(step.get("step_index") or 0),
    )
    if not next_step:
        # 走完最后一步 → 完成
        cur.execute(
            """
            UPDATE campaign_members SET
                status = 'completed',
                current_step_index = ?,
                last_step_sent_at = ?,
                next_due_at = '',
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(step.get("step_index") or 0),
                _now_iso() if send_result.get("ok") else "",
                _now_iso(),
                int(member_row_id),
            ),
        )
    else:
        # 算下一步 due
        next_due = _due_at_for_step(
            anchor_date=str(row["anchor_date"] or ""),
            day_offset=int(next_step["day_offset"] or 0),
            send_time=str(next_step["send_time"] or "09:00"),
        )
        cur.execute(
            """
            UPDATE campaign_members SET
                status = 'pending',
                current_step_index = ?,
                last_step_sent_at = ?,
                next_due_at = ?,
                last_error_text = ?,
                retry_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(step.get("step_index") or 0),
                _now_iso() if send_result.get("ok") else "",
                next_due,
                "" if send_result.get("ok") else str(send_result.get("reason") or "")[:300],
                0 if send_result.get("ok") else 1,
                _now_iso(),
                int(member_row_id),
            ),
        )
    db.commit()


def process_due_campaign_members(*, batch_size: int = 200) -> dict[str, Any]:
    """Cron 入口：扫一批 due 的 member、各推一步。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cm.id AS cm_id, cm.member_id, cm.external_contact_id,
               cm.campaign_id, cm.campaign_segment_id, cm.current_step_index,
               cm.anchor_date, cm.trace_id,
               c.campaign_code, c.run_status, c.owner_userid
        FROM campaign_members cm
        JOIN campaigns c ON c.id = cm.campaign_id
        WHERE cm.status = 'pending'
          AND cm.next_due_at <> ''
          AND cm.next_due_at <= ?
          AND c.run_status = 'active'
        ORDER BY cm.next_due_at ASC, cm.id ASC
        LIMIT ?
        """,
        (_now_iso(), int(batch_size)),
    )
    due = cur.fetchall() or []
    processed = 0
    sent_ok = 0
    sent_failed = 0
    skipped = 0
    for r in due:
        cm_id = int(r["cm_id"])
        if not _claim_due_member(member_row_id=cm_id):
            continue
        processed += 1
        # 取下一个待发的 step（current_step_index 之后的第一个）
        step = _next_step(
            campaign_segment_id=int(r["campaign_segment_id"]),
            after_step_index=int(r["current_step_index"] or -1),
        )
        if not step:
            cur.execute(
                "UPDATE campaign_members SET status = 'completed', next_due_at = '', updated_at = ? "
                "WHERE id = ?",
                (_now_iso(), cm_id),
            )
            db.commit()
            continue
        member_dict = {
            "member_id": int(r["member_id"] or 0),
            "external_contact_id": str(r["external_contact_id"] or ""),
            "trace_id": str(r["trace_id"] or ""),
            "campaign_segment_id": int(r["campaign_segment_id"]),
        }
        campaign_dict = {
            "id": int(r["campaign_id"]),
            "campaign_code": str(r["campaign_code"] or ""),
            "owner_userid": str(r["owner_userid"] or ""),
            "trace_id": str(r["trace_id"] or ""),
        }
        try:
            send_res = _send_step_to_member(
                campaign=campaign_dict,
                member=member_dict,
                step=step,
            )
        except Exception as exc:
            logger.exception("send step crashed: %s", exc)
            send_res = {"ok": False, "reason": f"crash:{exc}"}
        if send_res.get("ok"):
            sent_ok += 1
        elif (send_res.get("reason") or "").startswith("budget_exceeded"):
            skipped += 1
        else:
            sent_failed += 1
        progress_member_after_send(
            member_row_id=cm_id,
            step=step,
            send_result=send_res,
        )
    return {
        "processed": processed,
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
        "skipped_budget": skipped,
        "scanned_at": _now_iso(),
    }


def register_member_reply(
    *,
    external_contact_id: str = "",
    member_id: int | None = None,
) -> int:
    """reply_monitor 收到 inbound 时调 — 把对应 campaign_member 标记为已回复，停止后续步骤。

    返回被影响的成员数。
    """
    if not external_contact_id and member_id is None:
        return 0
    db = get_db()
    cur = db.cursor()
    if member_id is not None:
        cur.execute(
            """
            UPDATE campaign_members SET
                status = 'replied',
                stop_reason = 'user_replied',
                next_due_at = '',
                updated_at = ?
            WHERE member_id = ? AND status IN ('pending','running')
            """,
            (_now_iso(), int(member_id)),
        )
    else:
        cur.execute(
            """
            UPDATE campaign_members SET
                status = 'replied',
                stop_reason = 'user_replied',
                next_due_at = '',
                updated_at = ?
            WHERE external_contact_id = ? AND status IN ('pending','running')
            """,
            (_now_iso(), str(external_contact_id)),
        )
    db.commit()
    return int(cur.rowcount or 0)


__all__ = [
    "process_due_campaign_members",
    "progress_member_after_send",
    "register_member_reply",
]
