from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _stringify_tags(customer: dict[str, Any]) -> list[str]:
    tags = customer.get("tags") or []
    result: list[str] = []
    seen: set[str] = set()
    for item in tags:
        if isinstance(item, dict):
            value = str(item.get("tag_name") or item.get("tag_id") or "").strip()
        else:
            value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    class_status = customer.get("class_user_status") or {}
    signup_label_name = str(class_status.get("signup_label_name") or "").strip()
    if signup_label_name and signup_label_name not in seen:
        result.append(signup_label_name)
    return result


def build_followup_candidates_payload(
    arguments: dict[str, Any],
    *,
    normalize_limit: Callable[[Any], int],
    get_db: Callable[[], Any],
    get_customer_detail: Callable[[str], dict[str, Any] | None],
    get_recent_messages_by_user: Callable[[str, int], list[dict[str, Any]]],
) -> dict[str, Any]:
    limit = normalize_limit(arguments.get("limit"), default=20, minimum=1, maximum=100)
    lookback_hours = normalize_limit(arguments.get("lookback_hours"), default=24, minimum=1, maximum=168)
    now = datetime.now()
    since = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = get_db().execute(
        """
        SELECT external_userid, MAX(send_time) AS last_message_at
        FROM archived_messages
        WHERE external_userid IS NOT NULL AND external_userid <> '' AND send_time >= ?
        GROUP BY external_userid
        ORDER BY last_message_at DESC, external_userid ASC
        """,
        (since,),
    ).fetchall()

    blocked_keywords = ("已成交", "成交", "勿扰", "关闭", "黑名单")
    high_intent_keywords = ("高意向", "待跟进", "已报价")
    candidates: list[dict[str, Any]] = []

    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        customer = get_customer_detail(external_userid)
        if not customer:
            continue

        tags = _stringify_tags(customer)
        class_status = customer.get("class_user_status") or {}
        status_text = " ".join(
            [
                str(class_status.get("signup_status") or "").strip(),
                str(class_status.get("signup_label_name") or "").strip(),
                " ".join(tags),
            ]
        )
        if any(keyword in status_text for keyword in blocked_keywords):
            continue

        recent_messages = get_recent_messages_by_user(external_userid, 20)
        if not recent_messages:
            continue

        score = 0
        reasons: list[str] = []
        last_customer_message_at: datetime | None = None
        latest_message_from_customer = False
        for index, message in enumerate(recent_messages):
            sender = str(message.get("from") or message.get("sender") or "").strip()
            send_time = _parse_timestamp(message.get("send_time"))
            if index == 0 and sender == external_userid:
                latest_message_from_customer = True
            if sender == external_userid and send_time is not None:
                last_customer_message_at = send_time
                break

        if last_customer_message_at is not None:
            age_hours = (now - last_customer_message_at).total_seconds() / 3600
            if age_hours <= 1:
                score += 5
                reasons.append("最近1小时客户有消息")
            elif age_hours <= 6:
                score += 3
                reasons.append("最近6小时客户有消息")

        if latest_message_from_customer:
            score += 4
            reasons.append("客户最后一条消息后暂无顾问跟进")

        if any(keyword in tag for tag in tags for keyword in high_intent_keywords):
            score += 3
            reasons.append("当前标签包含高意向信号")

        score += 2
        reasons.append("客户仍处于可继续跟进状态")

        if score <= 0:
            continue

        candidates.append(
            {
                "external_userid": external_userid,
                "customer_name": str(customer.get("customer_name") or "").strip(),
                "owner_userid": str(customer.get("owner_userid") or "").strip(),
                "score": score,
                "reason": reasons[0],
                "reasons": reasons,
                "suggested_action": "contact_now" if score >= 6 else "review_context",
                "last_message_at": str(customer.get("last_message_at") or row.get("last_message_at") or "").strip(),
                "tags": tags,
                "class_user_status": class_status,
            }
        )

    candidates.sort(key=lambda item: (int(item["score"]), str(item["last_message_at"]), item["external_userid"]), reverse=True)
    ranked = []
    for index, item in enumerate(candidates[:limit], start=1):
        payload = dict(item)
        payload["rank"] = index
        ranked.append(payload)

    return {
        "ok": True,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_hours": lookback_hours,
        "limit": limit,
        "candidates": ranked,
    }
