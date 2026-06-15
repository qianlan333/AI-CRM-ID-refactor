from __future__ import annotations

from typing import Any


PUSH_STATUS_PENDING = "pending"
PUSH_STATUS_RUNNING = "running"
PUSH_STATUS_SUCCEEDED = "succeeded"
PUSH_STATUS_FAILED = "failed"

STANDARD_PUSH_STATUSES = (
    PUSH_STATUS_PENDING,
    PUSH_STATUS_RUNNING,
    PUSH_STATUS_SUCCEEDED,
    PUSH_STATUS_FAILED,
)

PUSH_STATUS_LABELS = {
    PUSH_STATUS_PENDING: "待执行",
    PUSH_STATUS_RUNNING: "执行中",
    PUSH_STATUS_SUCCEEDED: "执行成功",
    PUSH_STATUS_FAILED: "执行失败",
}

PUSH_STATUS_DEFINITIONS = {
    PUSH_STATUS_PENDING: "已进入统一推送任务池，等待统一调度器扫描或等待前置条件满足。",
    PUSH_STATUS_RUNNING: "任务已被统一调度器锁定，正在执行外部动作。",
    PUSH_STATUS_SUCCEEDED: "外部动作已执行成功，并已有成功 attempt 记录。",
    PUSH_STATUS_FAILED: "外部动作未成功完成，包括重试失败、终止失败、配置阻断、取消或过期。",
}

_RAW_TO_STANDARD = {
    "planned": PUSH_STATUS_PENDING,
    "approved": PUSH_STATUS_PENDING,
    "queued": PUSH_STATUS_PENDING,
    "dispatching": PUSH_STATUS_RUNNING,
    "succeeded": PUSH_STATUS_SUCCEEDED,
    "failed_retryable": PUSH_STATUS_FAILED,
    "failed_terminal": PUSH_STATUS_FAILED,
    "blocked": PUSH_STATUS_FAILED,
    "cancelled": PUSH_STATUS_FAILED,
    "expired": PUSH_STATUS_FAILED,
}

_ATTEMPT_TO_STANDARD = {
    "succeeded": PUSH_STATUS_SUCCEEDED,
    "failed_retryable": PUSH_STATUS_FAILED,
    "failed_terminal": PUSH_STATUS_FAILED,
    "blocked": PUSH_STATUS_FAILED,
    "skipped": PUSH_STATUS_FAILED,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def standard_push_status(raw_status: Any) -> str:
    return _RAW_TO_STANDARD.get(_text(raw_status), PUSH_STATUS_FAILED)


def standard_attempt_status(raw_status: Any) -> str:
    return _ATTEMPT_TO_STANDARD.get(_text(raw_status), standard_push_status(raw_status))


def push_status_label(status: Any) -> str:
    standard = standard_push_status(status)
    return PUSH_STATUS_LABELS[standard]


def attempt_status_label(status: Any) -> str:
    standard = standard_attempt_status(status)
    return PUSH_STATUS_LABELS[standard]


def status_matches(raw_status: Any, expected: Any) -> bool:
    expected_text = _text(expected)
    if not expected_text:
        return True
    if expected_text in STANDARD_PUSH_STATUSES:
        return standard_push_status(raw_status) == expected_text
    return _text(raw_status) == expected_text


def status_definitions_payload() -> list[dict[str, str]]:
    return [
        {"key": status, "label": PUSH_STATUS_LABELS[status], "definition": PUSH_STATUS_DEFINITIONS[status]}
        for status in STANDARD_PUSH_STATUSES
    ]
