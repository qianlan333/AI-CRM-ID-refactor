from __future__ import annotations

from typing import Any

JOB_TABS = (
    {"key": "overview", "label": "概览"},
    {"key": "archive", "label": "聊天同步"},
    {"key": "callbacks", "label": "回调状态"},
    {"key": "batches", "label": "消息批次"},
    {"key": "deferred", "label": "待处理作业"},
    {"key": "webhooks", "label": "Webhook 投递"},
    {"key": "broadcast_queue", "label": "群发队列", "href": "/admin/broadcast-jobs"},
)

BROADCAST_STATUSES = (
    "waiting_approval",
    "queued",
    "claimed",
    "sent",
    "failed",
    "cancelled",
)

BROADCAST_SOURCE_TYPES = (
    "campaign",
    "sop",
    "workflow",
    "operation_task",
    "cloud_plan",
    "focus_send",
    "deferred",
    "manual",
)


def normalized_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def status_tone(status: str) -> str:
    normalized = normalized_text(status).lower()
    if normalized in {"success", "acked", "enabled", "healthy", "sent", "queued"}:
        return "ok"
    if normalized in {"failed", "disabled", "error", "exhausted", "cancelled"}:
        return "danger"
    if normalized in {"pending", "running", "processing", "conflict", "skipped", "retry_scheduled", "waiting_approval", "claimed"}:
        return "warn"
    return "neutral"


def status_label(status: Any) -> str:
    mapping = {
        "success": "成功",
        "failed": "失败",
        "pending": "待处理",
        "processing": "处理中",
        "running": "运行中",
        "conflict": "冲突",
        "skipped": "已跳过",
        "acked": "已确认",
        "enabled": "已开启",
        "disabled": "未开启",
        "healthy": "正常",
        "never": "暂无记录",
        "retry_scheduled": "待自动重试",
        "exhausted": "已耗尽",
        "waiting_approval": "待审批",
        "queued": "排队中",
        "claimed": "执行中",
        "sent": "已发送",
        "cancelled": "已取消",
    }
    normalized = normalized_text(status).lower()
    return mapping.get(normalized, normalized_text(status) or "-")


def webhook_event_label(event_type: Any) -> str:
    mapping = {
        "openclaw_focus_message": "OpenClaw 焦点消息",
        "questionnaire_submit": "问卷提交外发",
    }
    return mapping.get(normalized_text(event_type), normalized_text(event_type) or "-")
