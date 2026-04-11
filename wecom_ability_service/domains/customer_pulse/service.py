from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from flask import current_app, g, has_app_context, has_request_context

from ...infra.settings import get_setting
from ..marketing_automation import set_manual_followup_segment
from ..tags.service import mark_customer_tags, unmark_customer_tags
from ..tasks.service import get_outbound_task, save_local_private_message_draft, update_outbound_task_status
from .access import (
    CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
    CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
    CustomerPulseTenantContext,
    CustomerPulseAccessDenied,
    assert_customer_pulse_action_permission,
    assert_customer_pulse_evidence_view,
    assert_customer_pulse_feedback_permission,
    customer_pulse_action_permission,
    customer_pulse_context_tenant_key,
    customer_pulse_external_request_scoped_enforced,
    current_customer_pulse_request_access_context,
    customer_pulse_permission_summary,
    customer_pulse_tenant_context_summary,
    customer_pulse_default_tenant_key,
    customer_pulse_scoped_key,
    customer_pulse_tenant_mode,
)
from .ai_recommendation import (
    customer_pulse_mask_pii,
    customer_pulse_text_guardrail_hits,
    generate_customer_pulse_ai_recommendation,
)
from . import repo

CUSTOMER_PULSE_FLAG_KEY = "ai_customer_pulse"
CUSTOMER_PULSE_RULES_VERSION = "customer_pulse_rules_v1"
CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE = "customer_pulse_recompute"
CUSTOMER_PULSE_TENANT_KEY = customer_pulse_default_tenant_key()
CUSTOMER_PULSE_UNDO_WINDOW_MINUTES = 10
CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD_KEY = "CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD"
CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_KEY = "CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS"
CUSTOMER_PULSE_ALLOWED_ACTION_TYPES_KEY = "CUSTOMER_PULSE_ALLOWED_ACTION_TYPES"
CUSTOMER_PULSE_FLAG_POLICY_KEY = "CUSTOMER_PULSE_FLAG_POLICY_JSON"
CUSTOMER_PULSE_DEFAULT_HIGH_PRIORITY_THRESHOLD = 70
CUSTOMER_PULSE_DEFAULT_SHOW_LOW_CONFIDENCE = False
CUSTOMER_PULSE_RESOURCE_CARD = "customer_pulse_card"
CUSTOMER_PULSE_RESOURCE_EVIDENCE = "customer_pulse_evidence"
CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS = 7
_FEATURE_POLICY_RESERVED_KEYS = {"default_enabled", "roles", "userids", "legacy_internal", "tenants"}
_CROSS_TENANT_ERROR_CODES = {"cross_tenant_owner_scope"}
_UNAUTHORIZED_ERROR_CODES = {
    "action_permission_denied",
    "action_permission_unmapped",
    "actor_owner_scope_forbidden",
    "card_view_forbidden",
    "customer_pulse_detail_forbidden",
    "evidence_view_forbidden",
    "feedback_permission_forbidden",
    "inbox_view_forbidden",
    "internal_role_forbidden",
    "operator_role_forbidden",
    "owner_scope_forbidden",
    "page_permission_forbidden",
    "viewer_role_forbidden",
    "widget_view_forbidden",
}
_EXECUTION_AUDIT_AI_SUGGESTED = "ai_suggested"
_EXECUTION_AUDIT_HUMAN_CONFIRMED = "human_confirmed"
_EXECUTION_AUDIT_HUMAN_EDITED = "human_edited"
_EXECUTION_META_FIELDS = {
    "admin_action_token",
    "action_type",
    "operator",
    "metric_source",
    "track_click",
    "feedback_source",
    "note",
}
_EXECUTION_ALLOWED_FIELDS = {
    "generate_reply_draft": {"draft_message"},
    "create_followup_task": {"task_title", "due_at"},
    "update_followup_segment": {"followup_segment"},
    "update_tags": {"add_tag_ids", "remove_tag_ids", "add_tag", "remove_tag"},
    "set_followup_reminder": {"due_at"},
}
_EXECUTION_FORBIDDEN_FIELDS = {
    "tenant_key",
    "tenant_id",
    "card_id",
    "execution_id",
    "price",
    "discount",
    "refund",
    "refund_policy",
    "promise",
    "system_prompt",
    "prompt",
}
_HIGH_INTENT_SEGMENTS = {"core", "top", "focus"}
_HIGH_INTENT_STAGE_KEYS = {
    "pool/active_focus",
    "pool/inactive_focus",
}
_HIGH_INTENT_TAG_KEYWORDS = ("高意向", "待跟进", "已报价", "课程安排", "想报名")
_HIGH_INTENT_MESSAGE_KEYWORDS = (
    "报价",
    "价格",
    "费用",
    "方案",
    "试听",
    "试课",
    "课程",
    "开课",
    "安排",
    "名额",
    "报名",
    "合同",
    "付款",
    "预约",
    "体验",
)
_QUESTION_HINT_KEYWORDS = (
    "?",
    "？",
    "吗",
    "呢",
    "么",
    "什么时候",
    "多久",
    "怎么",
    "如何",
    "可以",
    "报价",
    "价格",
    "费用",
    "安排",
    "链接",
)
_NEGATIVE_MESSAGE_KEYWORDS = (
    "投诉",
    "不满意",
    "退款",
    "退费",
    "退课",
    "太贵",
    "贵了",
    "没人回复",
    "没人联系",
    "生气",
    "失望",
    "问题",
    "故障",
    "异常",
    "取消",
    "算了",
    "不考虑",
    "差评",
    "不好用",
    "被打扰",
)
_FOLLOWUP_DUE_FIELDS = (
    "next_followup_at",
    "next_followup_time",
    "next_touch_at",
    "followup_due_at",
    "remind_at",
)
_SAFE_DISPATCH_STATUSES = {"", "pending", "blocked_quiet_hours", "dispatched", "acked", "cancelled", "converted_before_dispatch"}
_TERMINAL_CARD_STATUSES = {"completed", "dismissed"}
_ACTIVE_CARD_STATUSES = {"open", "draft_ready", "snoozed"}
_CRITICAL_RISK_FLAGS = {"unanswered_question", "negative_sentiment", "service_exception"}
_SUPPORTED_ACTION_TYPES = {
    "generate_reply_draft",
    "create_followup_task",
    "update_followup_segment",
    "update_tags",
    "set_followup_reminder",
}
_ACTION_FEEDBACK_TYPES = {"adopted", "edited_then_sent", "ignored", "misjudged", "unhelpful"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any) -> bool:
    return _normalized_text(value).lower() in {"1", "true", "yes", "on"}


def _config_value(key: str, default: Any = "") -> Any:
    cache: dict[str, Any] | None = None
    if has_app_context():
        existing_cache = g.get("customer_pulse_config_cache")
        if isinstance(existing_cache, dict):
            cache = existing_cache
        else:
            cache = {}
            g.customer_pulse_config_cache = cache
        if key in cache:
            return cache[key]
    stored = get_setting(key)
    if stored not in (None, ""):
        resolved = stored
    else:
        resolved = current_app.config.get(key, default)
    if cache is not None:
        cache[key] = resolved
    return resolved


def _config_bool(key: str, *, default: bool) -> bool:
    raw_value = _config_value(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_bool(raw_value) if raw_value not in (None, "") else default


def _config_int(key: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = _config_value(key, default)
    try:
        resolved = int(raw_value)
    except (TypeError, ValueError):
        resolved = default
    return max(minimum, min(resolved, maximum))


def _high_priority_threshold() -> int:
    return _config_int(
        CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD_KEY,
        default=CUSTOMER_PULSE_DEFAULT_HIGH_PRIORITY_THRESHOLD,
        minimum=1,
        maximum=100,
    )


def _show_low_confidence_suggestions() -> bool:
    return _config_bool(
        CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_KEY,
        default=CUSTOMER_PULSE_DEFAULT_SHOW_LOW_CONFIDENCE,
    )


def _allowed_action_types() -> set[str]:
    raw_value = _config_value(CUSTOMER_PULSE_ALLOWED_ACTION_TYPES_KEY, "")
    if isinstance(raw_value, (list, tuple, set)):
        normalized = {_normalized_text(item) for item in raw_value if _normalized_text(item)}
    else:
        normalized = {
            _normalized_text(item)
            for item in str(raw_value or "").replace("|", ",").split(",")
            if _normalized_text(item)
        }
    filtered = {item for item in normalized if item in _SUPPORTED_ACTION_TYPES}
    return filtered or set(_SUPPORTED_ACTION_TYPES)


def _action_allowed(action_type: str) -> bool:
    return _normalized_text(action_type) in _allowed_action_types()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for pattern in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_followup_time() -> str:
    return (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _soon_followup_time(*, hours: int = 2) -> str:
    return (datetime.now() + timedelta(hours=max(1, int(hours or 0)))).strftime("%Y-%m-%d %H:%M:%S")


def _setting_enabled() -> bool:
    raw_value = _config_value(
        CUSTOMER_PULSE_FLAG_KEY,
        current_app.config.get(CUSTOMER_PULSE_FLAG_KEY, False) if has_app_context() else False,
    )
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value in (None, ""):
        return False
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _feature_policy_map() -> dict[str, Any]:
    payload = _json_loads(_config_value(CUSTOMER_PULSE_FLAG_POLICY_KEY, "{}"), default={})
    if not isinstance(payload, dict):
        return {
            "default_enabled": True,
            "roles": {},
            "userids": {},
            "legacy_internal": {},
            "tenants": {},
        }
    tenants = payload.get("tenants") if isinstance(payload.get("tenants"), dict) else {}
    if not tenants:
        tenants = {
            _normalized_text(key): value
            for key, value in payload.items()
            if _normalized_text(key) and key not in _FEATURE_POLICY_RESERVED_KEYS and isinstance(value, dict)
        }
    return {
        "default_enabled": _normalized_bool(payload.get("default_enabled", True)),
        "roles": payload.get("roles") if isinstance(payload.get("roles"), dict) else {},
        "userids": payload.get("userids") if isinstance(payload.get("userids"), dict) else {},
        "legacy_internal": payload.get("legacy_internal") if isinstance(payload.get("legacy_internal"), dict) else {},
        "tenants": tenants,
    }


def _feature_override_map(section: Any, *keys: str) -> dict[str, bool]:
    if not isinstance(section, dict):
        return {}
    for key in keys:
        value = section.get(key)
        if not isinstance(value, dict):
            continue
        return {
            _normalized_text(actor_key).lower(): _normalized_bool(actor_enabled)
            for actor_key, actor_enabled in value.items()
            if _normalized_text(actor_key)
        }
    return {}


def _feature_gate_context(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if access_context is not None:
        return dict(access_context)
    if has_request_context():
        return dict(current_customer_pulse_request_access_context())
    return {}


def customer_pulse_feature_gate(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    global_enabled = _setting_enabled()
    tenant_key = _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY
    actor_role = _normalized_text(context.get("actor_role") or context.get("role")).lower()
    actor_userid = _normalized_text(context.get("actor_userid") or context.get("user_id")).lower()
    feature_policy = _feature_policy_map()
    tenant_map = feature_policy.get("tenants") if isinstance(feature_policy.get("tenants"), dict) else {}
    global_role_overrides = _feature_override_map(feature_policy, "roles")
    global_user_overrides = _feature_override_map(feature_policy, "userids")
    legacy_mode = bool(context.get("legacy_mode"))
    section_key = CUSTOMER_PULSE_LEGACY_INTERNAL_MODE if legacy_mode else tenant_key
    section = (
        feature_policy.get("legacy_internal")
        if legacy_mode
        else (tenant_map.get(section_key) if isinstance(tenant_map, dict) else {})
    )
    if not isinstance(section, dict):
        section = {}
    section_enabled = (
        _normalized_bool(section.get("enabled"))
        if "enabled" in section
        else _normalized_bool(feature_policy.get("default_enabled", True))
    )
    tenant_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:{section_key}" if "enabled" in section else "global_default"
    actor_enabled = True
    actor_override_source = ""
    section_user_overrides = _feature_override_map(section, "userids", "users")
    section_role_overrides = _feature_override_map(section, "roles")
    if actor_userid and actor_userid in section_user_overrides:
        actor_enabled = bool(section_user_overrides[actor_userid])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:{section_key}:userids"
    elif actor_role and actor_role in section_role_overrides:
        actor_enabled = bool(section_role_overrides[actor_role])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:{section_key}:roles"
    elif actor_userid and actor_userid in global_user_overrides:
        actor_enabled = bool(global_user_overrides[actor_userid])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:userids"
    elif actor_role and actor_role in global_role_overrides:
        actor_enabled = bool(global_role_overrides[actor_role])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:roles"
    enabled = bool(global_enabled and section_enabled and actor_enabled)
    reason = "enabled"
    if not global_enabled:
        reason = "global_disabled"
    elif not section_enabled:
        reason = "tenant_disabled" if not legacy_mode else "legacy_internal_disabled"
    elif not actor_enabled:
        reason = "actor_disabled"
    return {
        "enabled": enabled,
        "reason": reason,
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "policy_key": CUSTOMER_PULSE_FLAG_POLICY_KEY,
        "global_enabled": bool(global_enabled),
        "tenant_enabled": bool(section_enabled),
        "actor_enabled": bool(actor_enabled),
        "tenant_key": tenant_key,
        "actor_userid": actor_userid,
        "actor_role": actor_role,
        "mode": _normalized_text(context.get("mode")) or customer_pulse_tenant_mode(),
        "auth_mode": _normalized_text(context.get("auth_mode")) or customer_pulse_tenant_mode(),
        "legacy_mode": legacy_mode,
        "tenant_scope": section_key,
        "tenant_override_source": tenant_override_source,
        "actor_override_source": actor_override_source,
    }


def is_customer_pulse_inbox_enabled(*, access_context: Mapping[str, Any] | None = None) -> bool:
    return bool(customer_pulse_feature_gate(access_context).get("enabled"))


def customer_pulse_feature_gate_summary(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    gate = customer_pulse_feature_gate(access_context)
    return {
        "enabled": bool(gate.get("enabled")),
        "reason": _normalized_text(gate.get("reason")) or "enabled",
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "policy_key": CUSTOMER_PULSE_FLAG_POLICY_KEY,
        "global_enabled": bool(gate.get("global_enabled")),
        "tenant_enabled": bool(gate.get("tenant_enabled")),
        "actor_enabled": bool(gate.get("actor_enabled")),
        "tenant_key": _normalized_text(gate.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "actor_userid": _normalized_text(gate.get("actor_userid")),
        "actor_role": _normalized_text(gate.get("actor_role")),
        "mode": _normalized_text(gate.get("mode")),
        "auth_mode": _normalized_text(gate.get("auth_mode")),
        "legacy_mode": bool(gate.get("legacy_mode")),
        "tenant_scope": _normalized_text(gate.get("tenant_scope")),
        "tenant_override_source": _normalized_text(gate.get("tenant_override_source")),
        "actor_override_source": _normalized_text(gate.get("actor_override_source")),
    }


def customer_pulse_rollout_whitelist_summary() -> dict[str, Any]:
    feature_policy = _feature_policy_map()
    tenant_map = feature_policy.get("tenants") if isinstance(feature_policy.get("tenants"), dict) else {}
    default_enabled = bool(feature_policy.get("default_enabled"))
    enabled_tenants: list[str] = []
    disabled_tenants: list[str] = []
    tenant_entries: list[dict[str, Any]] = []
    for tenant_key in sorted(_normalized_text(key) for key in tenant_map.keys() if _normalized_text(key)):
        section = tenant_map.get(tenant_key) if isinstance(tenant_map.get(tenant_key), dict) else {}
        tenant_enabled = _normalized_bool(section.get("enabled")) if "enabled" in section else default_enabled
        role_overrides = _feature_override_map(section, "roles")
        user_overrides = _feature_override_map(section, "userids", "users")
        if tenant_enabled:
            enabled_tenants.append(tenant_key)
        else:
            disabled_tenants.append(tenant_key)
        tenant_entries.append(
            {
                "tenant_key": tenant_key,
                "enabled": bool(tenant_enabled),
                "role_override_count": len(role_overrides),
                "user_override_count": len(user_overrides),
            }
        )
    return {
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "policy_key": CUSTOMER_PULSE_FLAG_POLICY_KEY,
        "global_enabled": _setting_enabled(),
        "default_enabled": default_enabled,
        "tenant_mode": customer_pulse_tenant_mode(),
        "external_request_scoped_enforced": customer_pulse_external_request_scoped_enforced(),
        "enabled_tenants": enabled_tenants,
        "disabled_tenants": disabled_tenants,
        "tenants": tenant_entries,
        "whitelist_ready": bool(_setting_enabled()) and not default_enabled and bool(enabled_tenants),
    }


def build_customer_pulse_tenant_rollout_report(
    *,
    days: int = CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
    tenant_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    whitelist = customer_pulse_rollout_whitelist_summary()
    requested_tenant_keys = [_normalized_text(item) for item in (tenant_keys or []) if _normalized_text(item)]
    report_tenant_keys = requested_tenant_keys or list(whitelist.get("enabled_tenants") or [])
    tenant_reports: list[dict[str, Any]] = []
    for tenant_key in report_tenant_keys:
        stats = build_customer_pulse_ops_dashboard_payload(tenant_key=tenant_key, days=days)
        tenant_reports.append(
            {
                "tenant_key": tenant_key,
                "feature_gate": dict(stats.get("feature_gate") or {}),
                "counts": {
                    key: int((stats.get("counts") or {}).get(key, 0) or 0)
                    for key in (
                        "ai_success",
                        "ai_error",
                        "fallback_count",
                        "draft_preview_started",
                        "draft_confirmed",
                        "writeback_success",
                        "unauthorized_denied",
                        "cross_tenant_denied",
                    )
                },
                "rates": {
                    key: float((stats.get("rates") or {}).get(key, 0.0) or 0.0)
                    for key in (
                        "draft_confirm_rate",
                        "fallback_rate",
                        "writeback_success_rate",
                        "ai_error_rate",
                    )
                },
                "window": dict(stats.get("window") or {}),
            }
        )
    return {
        "generated_at": _iso_now(),
        "window_days": max(1, int(days or CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS)),
        "whitelist": whitelist,
        "tenants": tenant_reports,
    }


def _customer_pulse_review_data_source_summary() -> dict[str, Any]:
    database_url = _normalized_text(current_app.config.get("DATABASE_URL"))
    database_path = _normalized_text(current_app.config.get("DATABASE_PATH"))
    project_root = Path(current_app.root_path).parent.resolve()
    if database_url:
        return {
            "backend": "postgres",
            "source_type": "configured_database_url",
            "production_evidence_verified": True,
            "summary": "当前通过 DATABASE_URL 连接数据库，默认视为外部部署数据库来源。",
        }
    resolved_path = Path(database_path).expanduser().resolve() if database_path else Path("")
    source_type = "workspace_local_sqlite"
    production_evidence_verified = False
    if database_path and not str(resolved_path).startswith(str(project_root)):
        source_type = "external_sqlite"
    return {
        "backend": "sqlite",
        "source_type": source_type,
        "database_path": str(resolved_path) if database_path else "",
        "production_evidence_verified": production_evidence_verified,
        "summary": "当前使用本地 SQLite 数据源，不能自动视为已验证的 7 天真实生产数据。",
    }


def _trend_direction(series: list[int]) -> str:
    if len(series) < 2:
        return "flat"
    first = float(series[0] or 0)
    last = float(series[-1] or 0)
    if last - first >= 1:
        return "up"
    if first - last >= 1:
        return "down"
    return "flat"


def _tenant_review_status(
    *,
    ai_error_rate: float,
    fallback_rate: float,
    draft_confirm_rate: float,
    writeback_success_rate: float,
    unauthorized_denied: int,
    cross_tenant_denied: int,
    production_evidence_verified: bool,
    observed_days: int,
) -> dict[str, Any]:
    meets_expansion = (
        production_evidence_verified
        and observed_days >= 7
        and ai_error_rate <= 0.10
        and fallback_rate <= 0.20
        and draft_confirm_rate >= 0.20
        and writeback_success_rate >= 0.95
        and unauthorized_denied <= 0
        and cross_tenant_denied <= 0
    )
    rollback_risk = cross_tenant_denied > 0 and production_evidence_verified
    if rollback_risk:
        return {"label": "风险，建议暂停或回滚", "decision": "rollback"}
    if meets_expansion:
        return {"label": "健康，可扩容参考", "decision": "expand"}
    return {"label": "观察中，继续当前灰度", "decision": "hold"}


def build_customer_pulse_first_wave_review_report(
    *,
    days: int = 7,
    tenant_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_days = max(1, int(days or 7))
    rollout = build_customer_pulse_tenant_rollout_report(days=resolved_days, tenant_keys=tenant_keys)
    data_source = _customer_pulse_review_data_source_summary()
    since = _stats_since(resolved_days)
    tenant_reviews: list[dict[str, Any]] = []
    decision_rank = {"expand": 0, "hold": 1, "rollback": 2}
    overall_decision = "expand"
    for tenant_report in rollout.get("tenants") or []:
        item = dict(tenant_report or {})
        tenant_key = _normalized_text(item.get("tenant_key"))
        daily_rows = repo.count_customer_pulse_metric_events_by_day(
            tenant_key=tenant_key,
            since=since,
            event_types=(
                "ai_success",
                "ai_error",
                "fallback_count",
                "draft_preview_started",
                "draft_confirmed",
                "writeback_success",
                "writeback_failed",
                "unauthorized_denied",
                "cross_tenant_denied",
            ),
        )
        daily_map: dict[str, dict[str, int]] = {}
        for row in daily_rows:
            metric_date = _normalized_text(row.get("metric_date"))
            if not metric_date:
                continue
            bucket = daily_map.setdefault(metric_date, {})
            bucket[_normalized_text(row.get("event_type"))] = int(row.get("total_count") or 0)
        ordered_dates = sorted(daily_map.keys())
        counts = dict(item.get("counts") or {})
        ai_success = int(counts.get("ai_success", 0) or 0)
        ai_error = int(counts.get("ai_error", 0) or 0)
        fallback_count = int(counts.get("fallback_count", 0) or 0)
        draft_preview_started = int(counts.get("draft_preview_started", 0) or 0)
        draft_confirmed = int(counts.get("draft_confirmed", 0) or 0)
        writeback_success = int(counts.get("writeback_success", 0) or 0)
        unauthorized_denied = int(counts.get("unauthorized_denied", 0) or 0)
        cross_tenant_denied = int(counts.get("cross_tenant_denied", 0) or 0)
        writeback_failed = sum(int(daily_map.get(day, {}).get("writeback_failed", 0) or 0) for day in ordered_dates)
        ai_error_rate = _safe_rate(ai_error, ai_success + ai_error)
        fallback_rate = _safe_rate(fallback_count, ai_success + fallback_count)
        draft_confirm_rate = _safe_rate(draft_confirmed, draft_preview_started)
        writeback_success_rate = _safe_rate(writeback_success, writeback_success + writeback_failed)
        review_status = _tenant_review_status(
            ai_error_rate=ai_error_rate,
            fallback_rate=fallback_rate,
            draft_confirm_rate=draft_confirm_rate,
            writeback_success_rate=writeback_success_rate,
            unauthorized_denied=unauthorized_denied,
            cross_tenant_denied=cross_tenant_denied,
            production_evidence_verified=bool(data_source.get("production_evidence_verified")),
            observed_days=len(ordered_dates),
        )
        overall_decision = (
            review_status["decision"]
            if decision_rank[review_status["decision"]] > decision_rank[overall_decision]
            else overall_decision
        )
        tenant_reviews.append(
            {
                "tenant_key": tenant_key,
                "seven_day_totals": {
                    "ai_success": ai_success,
                    "ai_error": ai_error,
                    "fallback_count": fallback_count,
                    "draft_preview_started": draft_preview_started,
                    "draft_confirmed": draft_confirmed,
                    "writeback_success": writeback_success,
                    "writeback_failed": writeback_failed,
                    "unauthorized_denied": unauthorized_denied,
                    "cross_tenant_denied": cross_tenant_denied,
                },
                "daily_average": {
                    "ai_success": round(ai_success / resolved_days, 4),
                    "ai_error": round(ai_error / resolved_days, 4),
                    "fallback_count": round(fallback_count / resolved_days, 4),
                    "draft_preview_started": round(draft_preview_started / resolved_days, 4),
                    "draft_confirmed": round(draft_confirmed / resolved_days, 4),
                    "writeback_success": round(writeback_success / resolved_days, 4),
                },
                "rates": {
                    "ai_error_rate": ai_error_rate,
                    "fallback_rate": fallback_rate,
                    "draft_confirm_rate": draft_confirm_rate,
                    "writeback_success_rate": writeback_success_rate,
                },
                "trend": {
                    "observed_days": len(ordered_dates),
                    "active_dates": ordered_dates,
                    "draft_preview_started": _trend_direction(
                        [int(daily_map.get(day, {}).get("draft_preview_started", 0) or 0) for day in ordered_dates]
                    ),
                    "draft_confirmed": _trend_direction(
                        [int(daily_map.get(day, {}).get("draft_confirmed", 0) or 0) for day in ordered_dates]
                    ),
                    "fallback_count": _trend_direction(
                        [int(daily_map.get(day, {}).get("fallback_count", 0) or 0) for day in ordered_dates]
                    ),
                },
                "meets_expansion_gate": review_status["decision"] == "expand",
                "status": review_status["label"],
                "decision": review_status["decision"],
            }
        )
    final_decision = overall_decision
    if not bool(data_source.get("production_evidence_verified")):
        final_decision = "hold"
    return {
        "generated_at": _iso_now(),
        "window_days": resolved_days,
        "data_source": data_source,
        "rollout": rollout,
        "tenants": tenant_reviews,
        "final_decision": final_decision,
    }


def _priority_label(priority: str) -> str:
    return {
        "high": "高优先级",
        "normal": "常规",
        "low": "低优先级",
    }.get(_normalized_text(priority), "常规")


def _card_status_label(status: str) -> str:
    return {
        "open": "待处理",
        "draft_ready": "草稿已生成",
        "snoozed": "已设置提醒",
        "completed": "已完成",
        "dismissed": "已忽略",
    }.get(_normalized_text(status), "待处理")


def _action_label(action_type: str) -> str:
    return {
        "generate_reply_draft": "生成回复草稿",
        "create_followup_task": "创建跟进任务",
        "update_followup_segment": "更新跟进阶段",
        "update_tags": "更新客户标签",
        "set_followup_reminder": "设置下次提醒",
    }.get(_normalized_text(action_type), "人工确认")


def _stage_label(main_stage: str, sub_stage: str) -> str:
    key = "/".join(part for part in [_normalized_text(main_stage), _normalized_text(sub_stage)] if part)
    mapping = {
        "pool/new_user": "新用户池",
        "pool/inactive_normal": "未激活普通池",
        "pool/inactive_focus": "未激活重点跟进池",
        "pool/active_normal": "激活普通池",
        "pool/active_focus": "激活重点跟进池",
        "pool/silent": "沉默池",
        "converted/enrolled": "已确认成交",
    }
    return mapping.get(key, key or "未分类")


def _segment_label(segment: str) -> str:
    return {
        "unknown": "未知",
        "normal": "普通",
        "core": "Core",
        "top": "Top",
        "focus": "重点跟进",
    }.get(_normalized_text(segment).lower(), _normalized_text(segment) or "未知")


def _safe_preview(value: Any, *, max_length: int = 80) -> str:
    text = _normalized_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _dedupe_evidence(items: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            _normalized_text(item.get("title")),
            _normalized_text(item.get("detail")),
            _normalized_text(item.get("event_time")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "title": _normalized_text(item.get("title")) or "证据",
                "detail": _normalized_text(item.get("detail")) or "暂无详情",
                "event_time": _normalized_text(item.get("event_time")),
                "source": _normalized_text(item.get("source")),
            }
        )
        if len(result) >= limit:
            break
    return result


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _explicit_tenant_context_from_key(tenant_key: str) -> CustomerPulseTenantContext:
    normalized_tenant_key = _normalized_text(tenant_key)
    return {
        "mode": CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
        "auth_mode": CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
        "valid": True,
        "legacy_mode": False,
        "tenant_key": normalized_tenant_key,
        "user_id": "",
        "role": "",
        "source": "explicit_tenant_key",
        "tenant_source": "explicit_tenant_key",
        "user_source": "",
        "role_source": "",
        "actor_userid": "",
        "actor_role": "",
        "operator": "crm_console",
        "policy": {},
        "allowed_owner_userids": [],
        "member_userids": [],
        "viewer_roles": [],
        "operator_roles": [],
        "internal_roles": [],
        "can_view_all": True,
        "error_code": "",
        "error_message": "",
        "http_status": 200,
    }


def _resolved_tenant_context(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> CustomerPulseTenantContext:
    context = dict(tenant_context or {})
    normalized_tenant_key = _normalized_text(tenant_key)
    if not context:
        if normalized_tenant_key:
            context = _explicit_tenant_context_from_key(normalized_tenant_key)
    elif normalized_tenant_key:
        context_tenant_key = customer_pulse_context_tenant_key(context, require_valid=not bool(context.get("legacy_mode")))
        if context_tenant_key and normalized_tenant_key != context_tenant_key:
            raise CustomerPulseAccessDenied(
                "显式 tenant_key 与 tenant_context 中的 tenant_key 不一致，拒绝继续访问 Customer Pulse。",
                code="tenant_context_conflict",
                http_status=400,
            )
    if not context:
        raise CustomerPulseAccessDenied(
            "当前调用必须显式传入 tenant_context 或 tenant_key，拒绝继续访问 Customer Pulse。",
            code="tenant_context_required",
            http_status=403,
        )
    context_tenant_key = customer_pulse_context_tenant_key(context, require_valid=not bool(context.get("legacy_mode")))
    return CustomerPulseTenantContext(context)


def _resolved_tenant_key(*, tenant_context: dict[str, Any] | None = None, tenant_key: str = "") -> str:
    context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    if bool(context.get("legacy_mode")) and customer_pulse_tenant_mode() == CUSTOMER_PULSE_LEGACY_INTERNAL_MODE:
        return CUSTOMER_PULSE_TENANT_KEY
    resolved_tenant_key = customer_pulse_context_tenant_key(context, require_valid=not bool(context.get("legacy_mode")))
    if resolved_tenant_key:
        return resolved_tenant_key
    raise CustomerPulseAccessDenied(
        "当前环境要求显式 tenant_key，拒绝继续访问 Customer Pulse。",
        code=_normalized_text(context.get("error_code")) or "tenant_context_required",
        http_status=403,
    )


def _resolved_tenant_context_summary(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    return customer_pulse_tenant_context_summary(
        _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    )


def _execution_key() -> str:
    return f"pulse-exec-{uuid.uuid4().hex}"


def _undo_until() -> str:
    return (datetime.now() + timedelta(minutes=CUSTOMER_PULSE_UNDO_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")


def _card_state_snapshot(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_status": _normalized_text(card.get("card_status")),
        "draft_message": _normalized_text(card.get("draft_message")),
        "need_human_confirmation": bool(card.get("need_human_confirmation")),
        "due_at": _normalized_text(card.get("due_at")),
        "snooze_until": _normalized_text(card.get("snooze_until")),
        "resolved_at": _normalized_text(card.get("resolved_at")),
        "resolution_note": _normalized_text(card.get("resolution_note")),
    }


def _card_state_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_status": _normalized_text(snapshot.get("card_status")),
        "need_human_confirmation": bool(snapshot.get("need_human_confirmation")),
        "due_at": _normalized_text(snapshot.get("due_at")),
        "snooze_until": _normalized_text(snapshot.get("snooze_until")),
        "resolved_at": _normalized_text(snapshot.get("resolved_at")),
        "resolution_note": _normalized_text(snapshot.get("resolution_note")),
        "draft_message_preview": customer_pulse_mask_pii(snapshot.get("draft_message"), max_length=60),
    }


def _resource_summary(*, resource_type: str, resource_id: Any) -> dict[str, Any]:
    return {
        "resource_type": _normalized_text(resource_type) or CUSTOMER_PULSE_RESOURCE_CARD,
        "resource_id": _normalized_text(resource_id),
    }


def _actor_summary(
    *,
    tenant_context: dict[str, Any] | None = None,
    operator: str = "",
) -> dict[str, Any]:
    resolved_context = dict(tenant_context or {})
    return {
        "actor_userid": _normalized_text(resolved_context.get("actor_userid") or resolved_context.get("user_id")),
        "actor_role": _normalized_text(resolved_context.get("actor_role") or resolved_context.get("role")),
        "operator": _normalized_text(operator) or _normalized_text(resolved_context.get("operator")),
        "auth_mode": _normalized_text(resolved_context.get("auth_mode") or resolved_context.get("mode")),
        "source": _normalized_text(resolved_context.get("source")),
    }


def _ai_audit_labels_from_candidate(candidate: dict[str, Any], action_payload: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    payload = dict(action_payload or {})
    if isinstance(payload.get("ai_recommendation"), dict) or _normalized_text(candidate.get("source")) == "ai":
        labels.append(_EXECUTION_AUDIT_AI_SUGGESTED)
    return labels


def _execution_audit_labels(
    *,
    base_labels: list[str],
    edited_fields: list[str],
) -> list[str]:
    labels = [item for item in base_labels if _normalized_text(item)]
    labels.append(_EXECUTION_AUDIT_HUMAN_EDITED if edited_fields else _EXECUTION_AUDIT_HUMAN_CONFIRMED)
    return list(dict.fromkeys(labels))


def _guardrail_summary(
    *,
    execution_labels: list[str],
    unsafe_input_fields: list[str],
    text_guardrail_hits: list[str],
    ai_guardrails: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ai_payload = dict(ai_guardrails or {})
    return {
        "audit_labels": list(dict.fromkeys([_normalized_text(item) for item in execution_labels if _normalized_text(item)])),
        "unsafe_input_fields": [_normalized_text(item) for item in unsafe_input_fields if _normalized_text(item)],
        "text_guardrail_hits": [_normalized_text(item) for item in text_guardrail_hits if _normalized_text(item)],
        "ai_guardrails": {
            "blocked": bool(ai_payload.get("blocked")),
            "input_violations": list(ai_payload.get("input_violations") or []),
            "output_violations": list(ai_payload.get("output_violations") or []),
        },
    }


def _request_payload_audit_summary(
    *,
    action_type: str,
    request_payload: dict[str, Any],
    tenant_context: dict[str, Any],
    operator: str,
    card: dict[str, Any],
    execution_labels: list[str],
    unsafe_input_fields: list[str],
    text_guardrail_hits: list[str],
) -> dict[str, Any]:
    ai_payload = dict(((card.get("snapshot") or {}).get("ai_payload") or {})) if isinstance((card.get("snapshot") or {}).get("ai_payload"), dict) else {}
    ai_recommendation_payload = dict((card.get("suggested_action_payload") or {}).get("ai_recommendation") or {})
    safe_field_updates = dict(ai_recommendation_payload.get("safe_field_updates") or {})
    return {
        "actor": _actor_summary(tenant_context=tenant_context, operator=operator),
        "resource": _resource_summary(resource_type=CUSTOMER_PULSE_RESOURCE_CARD, resource_id=card.get("id")),
        "tenant_context": customer_pulse_tenant_context_summary(tenant_context),
        "action_type": _normalized_text(action_type),
        "request_fields": sorted(request_payload.keys()),
        "safe_field_update_keys": sorted(
            key
            for key, value in safe_field_updates.items()
            if value not in (None, "", [], {})
        ),
        "guardrails": _guardrail_summary(
            execution_labels=execution_labels,
            unsafe_input_fields=unsafe_input_fields,
            text_guardrail_hits=text_guardrail_hits,
            ai_guardrails=ai_payload.get("guardrails") if isinstance(ai_payload.get("guardrails"), dict) else {},
        ),
    }


def _result_payload_audit_summary(
    *,
    action_type: str,
    card_before: dict[str, Any],
    card_after: dict[str, Any] | None,
    execution_labels: list[str],
    edited_fields: list[str],
    status: str,
    error_message: str = "",
    rollback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "action_type": _normalized_text(action_type),
        "status": _normalized_text(status),
        "edited_fields": [_normalized_text(item) for item in edited_fields if _normalized_text(item)],
        "labels": list(dict.fromkeys([_normalized_text(item) for item in execution_labels if _normalized_text(item)])),
        "before": _card_state_summary(card_before),
        "after": _card_state_summary(card_after or {}),
        "error_message": _normalized_text(error_message),
        "rollback": dict(rollback_payload or {}),
    }


def _execution_rollback_payload(
    *,
    action_type: str,
    pre_card_snapshot: dict[str, Any],
    undo_until: str = "",
    status: str = "pending",
    activity_log_id: int = 0,
) -> dict[str, Any]:
    return {
        "resource_type": CUSTOMER_PULSE_RESOURCE_CARD,
        "resource_id": "",
        "action_type": _normalized_text(action_type),
        "undo_supported": _action_requires_undo_window(action_type),
        "undo_until": _normalized_text(undo_until),
        "status": _normalized_text(status),
        "activity_log_id": int(activity_log_id or 0),
        "card_before": _card_state_summary(pre_card_snapshot),
    }


def _unsafe_execution_input_fields(action_type: str, action_payload: dict[str, Any]) -> list[str]:
    normalized_action_type = _normalized_text(action_type)
    allowed_fields = set(_EXECUTION_ALLOWED_FIELDS.get(normalized_action_type, set()))
    unexpected_fields = {
        _normalized_text(key)
        for key in dict(action_payload or {}).keys()
        if _normalized_text(key) and _normalized_text(key) not in allowed_fields and _normalized_text(key) not in _EXECUTION_META_FIELDS
    }
    forbidden = sorted(
        key
        for key in unexpected_fields
        if key in _EXECUTION_FORBIDDEN_FIELDS or key.endswith("_json") or key.endswith("_payload")
    )
    return forbidden


def _draft_execution_guardrail_hits(action_type: str, action_payload: dict[str, Any]) -> list[str]:
    if _normalized_text(action_type) != "generate_reply_draft":
        return []
    return customer_pulse_text_guardrail_hits(action_payload.get("draft_message"))


def _restore_card_state(
    card_id: int,
    snapshot: dict[str, Any],
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    return repo.update_customer_pulse_card(
        int(card_id),
        tenant_key=_resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key),
        card_status=_normalized_text(snapshot.get("card_status")) or "open",
        draft_message=_normalized_text(snapshot.get("draft_message")),
        need_human_confirmation=bool(snapshot.get("need_human_confirmation")),
        due_at=_normalized_text(snapshot.get("due_at")),
        snooze_until=_normalized_text(snapshot.get("snooze_until")),
        resolved_at=_normalized_text(snapshot.get("resolved_at")),
        resolution_note=_normalized_text(snapshot.get("resolution_note")),
    )


def _action_requires_undo_window(action_type: str) -> bool:
    return _normalized_text(action_type) in {
        "generate_reply_draft",
        "create_followup_task",
        "update_followup_segment",
        "update_tags",
        "set_followup_reminder",
    }


def _present_execution_log(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    request_payload = _json_loads(row.get("request_payload_json"), default={})
    if not isinstance(request_payload, dict):
        request_payload = {}
    result_payload = _json_loads(row.get("result_payload_json"), default={})
    if not isinstance(result_payload, dict):
        result_payload = {}
    tenant_context = _json_loads(row.get("tenant_context_json"), default={})
    if not isinstance(tenant_context, dict):
        tenant_context = {}
    audit_labels = _json_loads(row.get("audit_labels_json"), default=[])
    if not isinstance(audit_labels, list):
        audit_labels = []
    rollback_payload = _json_loads(row.get("rollback_payload_json"), default={})
    if not isinstance(rollback_payload, dict):
        rollback_payload = {}
    request_summary = dict(request_payload.get("audit") or {}) if isinstance(request_payload.get("audit"), dict) else {}
    result_summary = dict(result_payload.get("audit") or {}) if isinstance(result_payload.get("audit"), dict) else {}
    undo_until = _normalized_text(row.get("undo_until"))
    undo_supported = _action_requires_undo_window(row.get("action_type"))
    undo_available = False
    if undo_supported and _normalized_text(row.get("execution_status")) == "confirmed" and not _normalized_text(row.get("undone_at")):
        undo_deadline = _parse_datetime(undo_until)
        undo_available = bool(undo_deadline and undo_deadline >= datetime.now())
    return {
        "id": int(row.get("id") or 0),
        "card_id": int(row.get("card_id") or 0),
        "external_userid": _normalized_text(row.get("external_userid")),
        "action_type": _normalized_text(row.get("action_type")),
        "action_label": _action_label(row.get("action_type")),
        "execution_status": _normalized_text(row.get("execution_status")),
        "channel_type": _normalized_text(row.get("channel_type")),
        "operator": _normalized_text(row.get("operator")),
        "actor_userid": _normalized_text(row.get("actor_userid")),
        "actor_role": _normalized_text(row.get("actor_role")),
        "tenant_key": _normalized_text(row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "tenant_context": tenant_context,
        "resource_type": _normalized_text(row.get("resource_type")) or CUSTOMER_PULSE_RESOURCE_CARD,
        "resource_id": _normalized_text(row.get("resource_id")),
        "execution_key": _normalized_text(row.get("execution_key")),
        "idempotency_key": _normalized_text(row.get("idempotency_key")),
        "activity_log_id": int(row.get("activity_log_id") or 0) if row.get("activity_log_id") not in (None, "") else 0,
        "outbound_task_id": int(row.get("outbound_task_id") or 0) if row.get("outbound_task_id") not in (None, "") else 0,
        "audit_labels": [_normalized_text(item) for item in audit_labels if _normalized_text(item)],
        "undo_status": _normalized_text(row.get("undo_status")),
        "undo_until": undo_until,
        "undone_at": _normalized_text(row.get("undone_at")),
        "undo_supported": undo_supported,
        "undo_available": undo_available,
        "request_payload": request_payload,
        "request_summary": request_summary,
        "result_payload": result_payload,
        "result_summary": result_summary,
        "rollback_payload": rollback_payload,
        "error_message": _normalized_text(row.get("error_message")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _build_action_idempotency_key(card_id: int, action_type: str, payload: dict[str, Any]) -> str:
    normalized_payload = _json_dump(payload)
    digest = hashlib.sha256(f"{int(card_id)}:{_normalized_text(action_type)}:{normalized_payload}".encode("utf-8")).hexdigest()
    return f"pulse-card-{int(card_id)}-{_normalized_text(action_type)}-{digest[:24]}"


def _edited_fields(reference_payload: dict[str, Any], actual_payload: dict[str, Any]) -> list[str]:
    keys = sorted(set(reference_payload.keys()) | set(actual_payload.keys()))
    changed: list[str] = []
    for key in keys:
        if _json_dump(reference_payload.get(key)) != _json_dump(actual_payload.get(key)):
            changed.append(key)
    return changed


def _record_metric_event(
    *,
    event_type: str,
    event_source: str,
    card: dict[str, Any] | None = None,
    execution_log_id: int | None = None,
    action_type: str = "",
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _normalized_text(event_type):
        return {}
    card = dict(card or {})
    resolved_tenant_key = (
        _resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key)
        or _normalized_text(card.get("tenant_key"))
        or CUSTOMER_PULSE_TENANT_KEY
    )
    return repo.insert_customer_pulse_metric_event(
        card_id=int(card.get("id") or 0) or None,
        execution_log_id=execution_log_id,
        external_userid=_normalized_text(card.get("external_userid")),
        owner_userid=_normalized_text(card.get("owner_userid")),
        action_type=_normalized_text(action_type) or _normalized_text(card.get("suggested_action_type")),
        event_type=event_type,
        event_source=event_source,
        tenant_key=resolved_tenant_key,
        operator=_normalized_text(operator),
        payload=payload or {},
    )


def _record_action_feedback(
    *,
    card: dict[str, Any],
    feedback_type: str,
    feedback_source: str,
    operator: str,
    action_type: str = "",
    execution_log_id: int | None = None,
    note: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_feedback_type = _normalized_text(feedback_type)
    if normalized_feedback_type not in _ACTION_FEEDBACK_TYPES:
        return {}
    resolved_tenant_key = (
        _resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key)
        or _normalized_text(card.get("tenant_key"))
        or CUSTOMER_PULSE_TENANT_KEY
    )
    return repo.insert_customer_pulse_action_feedback(
        card_id=int(card.get("id") or 0),
        execution_log_id=execution_log_id,
        external_userid=_normalized_text(card.get("external_userid")),
        owner_userid=_normalized_text(card.get("owner_userid")),
        action_type=_normalized_text(action_type) or _normalized_text(card.get("suggested_action_type")),
        feedback_type=normalized_feedback_type,
        feedback_source=_normalized_text(feedback_source),
        tenant_key=resolved_tenant_key,
        operator=_normalized_text(operator),
        note=_normalized_text(note),
        payload=payload or {},
    )


def _card_hidden_by_low_confidence(card: dict[str, Any]) -> bool:
    if _show_low_confidence_suggestions():
        return False
    snapshot = dict(card.get("snapshot") or {})
    ai_payload = dict(snapshot.get("ai_payload") or {}) if isinstance(snapshot.get("ai_payload"), dict) else {}
    return _normalized_text(ai_payload.get("fallback_reason")) == "low_confidence"


def _apply_action_allowlist(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_types = _allowed_action_types()
    return [
        dict(item)
        for item in candidates
        if isinstance(item, dict) and _normalized_text(item.get("action_type")) in allowed_types
    ]


def _customer_pulse_metrics_summary(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, int]:
    counts = repo.count_customer_pulse_metric_events(
        tenant_key=_resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key),
        owner_userids=owner_userids,
        event_types=(
            "ai_success",
            "fallback_count",
            "card_exposed",
            "card_clicked",
            "draft_preview_started",
            "draft_confirmed",
            "followup_task_created",
            "followup_segment_updated",
            "card_ignored",
            "ai_error",
            "writeback_success",
            "writeback_failed",
        )
    )
    return {
        "ai_success": int(counts.get("ai_success", 0) or 0),
        "fallback_count": int(counts.get("fallback_count", 0) or 0),
        "card_exposed": int(counts.get("card_exposed", 0) or 0),
        "card_clicked": int(counts.get("card_clicked", 0) or 0),
        "draft_preview_started": int(counts.get("draft_preview_started", 0) or 0),
        "draft_confirmed": int(counts.get("draft_confirmed", 0) or 0),
        "followup_task_created": int(counts.get("followup_task_created", 0) or 0),
        "followup_segment_updated": int(counts.get("followup_segment_updated", 0) or 0),
        "card_ignored": int(counts.get("card_ignored", 0) or 0),
        "ai_error": int(counts.get("ai_error", 0) or 0),
        "writeback_success": int(counts.get("writeback_success", 0) or 0),
        "writeback_failed": int(counts.get("writeback_failed", 0) or 0),
    }


def _stats_since(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days or 0)))).strftime("%Y-%m-%d %H:%M:%S")


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _customer_pulse_dependency_status(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = dict(access_context or {})
    tenant_mode = customer_pulse_tenant_mode()
    external_request_scoped_enforced = customer_pulse_external_request_scoped_enforced()
    tenant_policy_text = _normalized_text(_config_value("CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON", ""))
    feature_policy_text = _normalized_text(_config_value(CUSTOMER_PULSE_FLAG_POLICY_KEY, ""))
    permissions = customer_pulse_permission_summary(context)
    return {
        "tenant_mode": {
            "ready": tenant_mode in {CUSTOMER_PULSE_LEGACY_INTERNAL_MODE, CUSTOMER_PULSE_REQUEST_SCOPED_MODE}
            and (not external_request_scoped_enforced or tenant_mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE),
            "value": tenant_mode,
            "label": "租户模式",
        },
        "external_guard": {
            "ready": not external_request_scoped_enforced or tenant_mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
            "value": (
                "request_scoped_enforced"
                if external_request_scoped_enforced and tenant_mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE
                else ("legacy_internal_blocked" if external_request_scoped_enforced else "not_enforced")
            ),
            "label": "外部环境 request-scoped 保护",
        },
        "rbac": {
            "ready": bool(context.get("legacy_mode")) or bool(tenant_policy_text),
            "value": "legacy_full_access" if bool(context.get("legacy_mode")) else ("policy_loaded" if tenant_policy_text else "missing_policy"),
            "label": "RBAC / owner scope",
        },
        "audit": {
            "ready": True,
            "value": "admin_operation_logs + customer_pulse_execution_logs",
            "label": "审计",
        },
        "metrics": {
            "ready": True,
            "value": "customer_pulse_metric_events",
            "label": "埋点 / 统计",
        },
        "seed_demo": {
            "ready": True,
            "value": "scripts/seed_customer_pulse_demo.py",
            "label": "Demo / Fixture",
        },
        "alerts": {
            "ready": True,
            "value": "stats_api_available" if permissions.get("inbox_view") else "stats_api_requires_inbox_view",
            "label": "告警入口",
        },
        "flag_policy": {
            "ready": True,
            "value": "configured" if feature_policy_text else "global_only",
            "label": "灰度策略",
        },
    }


def build_customer_pulse_ops_dashboard_payload(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    owner_userids: list[str] | tuple[str, ...] | None = None,
    days: int = CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    resolved_days = max(1, min(int(days or CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS), 90))
    since = _stats_since(resolved_days)
    counts = repo.count_customer_pulse_metric_events(
        tenant_key=resolved_tenant_key,
        owner_userids=owner_userids,
        since=since,
        event_types=(
            "action_executed",
            "ai_error",
            "ai_success",
            "ai_recommendation_completed",
            "card_clicked",
            "card_exposed",
            "draft_preview_started",
            "draft_confirmed",
            "fallback_count",
            "followup_segment_updated",
            "followup_task_created",
            "writeback_failed",
            "writeback_success",
        ),
    )
    security_counts = repo.count_customer_pulse_metric_events(
        tenant_key=resolved_tenant_key,
        since=since,
        event_types=("access_denied", "cross_tenant_denied", "unauthorized_denied"),
    )
    exposures = int(counts.get("card_exposed", 0) or 0)
    executions = int(counts.get("action_executed", 0) or 0)
    ai_success = int(counts.get("ai_success", 0) or 0)
    card_clicks = int(counts.get("card_clicked", 0) or 0)
    draft_preview_started = int(counts.get("draft_preview_started", 0) or 0)
    draft_confirms = int(counts.get("draft_confirmed", 0) or 0)
    fallback_count = int(counts.get("fallback_count", 0) or 0)
    writeback_success = int(counts.get("writeback_success", 0) or 0)
    writeback_failed = int(counts.get("writeback_failed", 0) or 0)
    ai_errors = int(counts.get("ai_error", 0) or 0)
    ai_completed = int(counts.get("ai_recommendation_completed", 0) or 0)
    unauthorized_denied = int(security_counts.get("unauthorized_denied", 0) or 0)
    cross_tenant_denied = int(security_counts.get("cross_tenant_denied", 0) or 0)
    execution_rate = _safe_rate(executions, exposures)
    draft_confirm_rate = _safe_rate(draft_confirms, draft_preview_started or card_clicks)
    fallback_rate = _safe_rate(fallback_count, ai_completed)
    writeback_success_rate = _safe_rate(writeback_success, writeback_success + writeback_failed)
    ai_error_rate = _safe_rate(ai_errors, ai_completed)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    dependencies = _customer_pulse_dependency_status(resolved_context)
    return {
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "feature_gate": feature_gate,
        "dependencies": dependencies,
        "window": {
            "days": resolved_days,
            "since": since,
        },
        "counts": {
            "card_exposed": exposures,
            "action_executed": executions,
            "ai_success": ai_success,
            "draft_confirmed": draft_confirms,
            "draft_preview_started": draft_preview_started,
            "fallback_count": fallback_count,
            "writeback_success": writeback_success,
            "writeback_failed": writeback_failed,
            "ai_error": ai_errors,
            "ai_recommendation_completed": ai_completed,
            "unauthorized_denied": int(security_counts.get("unauthorized_denied", 0) or 0),
            "cross_tenant_denied": int(security_counts.get("cross_tenant_denied", 0) or 0),
            "followup_task_created": int(counts.get("followup_task_created", 0) or 0),
            "followup_segment_updated": int(counts.get("followup_segment_updated", 0) or 0),
            "card_clicked": card_clicks,
            "access_denied": int(security_counts.get("access_denied", 0) or 0),
        },
        "rates": {
            "execution_rate": execution_rate,
            "draft_confirm_rate": draft_confirm_rate,
            "fallback_rate": fallback_rate,
            "writeback_success_rate": writeback_success_rate,
            "ai_error_rate": ai_error_rate,
        },
        "summary_cards": [
            {
                "key": "card_exposed",
                "label": f"最近 {resolved_days} 天曝光",
                "value": exposures,
                "description": "行动卡被展示的总次数。",
            },
            {
                "key": "execution_rate",
                "label": "执行率",
                "value": f"{round(execution_rate * 100, 1)}%",
                "description": f"{executions} 次执行 / {exposures} 次曝光",
            },
            {
                "key": "draft_confirm_rate",
                "label": "草稿确认率",
                "value": f"{round(draft_confirm_rate * 100, 1)}%",
                "description": f"{draft_confirms} 次确认 / {card_clicks} 次点击",
            },
            {
                "key": "writeback_success_rate",
                "label": "写回成功率",
                "value": f"{round(writeback_success_rate * 100, 1)}%",
                "description": f"{writeback_success} 成功 / {writeback_success + writeback_failed} 次写回",
            },
            {
                "key": "ai_error_rate",
                "label": "AI 错误率",
                "value": f"{round(ai_error_rate * 100, 1)}%",
                "description": f"{ai_errors} 次错误 / {ai_completed} 次 AI 推荐",
            },
                {
                    "key": "unauthorized_denied",
                    "label": "越权拒绝",
                    "value": unauthorized_denied,
                "description": "权限不足导致的拒绝次数。",
            },
                {
                    "key": "cross_tenant_denied",
                    "label": "跨租户拒绝",
                    "value": cross_tenant_denied,
                "description": "跨租户读取或探测被拦截的次数。",
            },
        ],
        "rollout_cards": [
            {
                "key": "feature_gate",
                "label": "灰度状态",
                "value": "已开启" if feature_gate["enabled"] else "未开启",
                "description": f"reason={feature_gate['reason']} · tenant={feature_gate['tenant_key']}",
            },
            {
                "key": "tenant_mode",
                "label": "Tenant Mode",
                "value": dependencies["tenant_mode"]["value"],
                "description": "legacy internal 与 request-scoped 显式区分。",
            },
            {
                "key": "rbac",
                "label": "RBAC",
                "value": "已就绪" if dependencies["rbac"]["ready"] else "未就绪",
                "description": str(dependencies["rbac"]["value"]),
            },
            {
                "key": "audit_metrics",
                "label": "审计 / 指标",
                "value": "已就绪",
                "description": "execution log、audit log、metric events 已贯通。",
            },
        ],
    }


def _normalize_action_execution_payload(
    *,
    card: dict[str, Any],
    action_type: str,
    candidate: dict[str, Any],
    action_payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_action_type = _normalized_text(action_type)
    if normalized_action_type == "generate_reply_draft":
        return {
            "draft_message": _normalized_text(action_payload.get("draft_message")) or _normalized_text(card.get("draft_message")),
        }
    if normalized_action_type == "create_followup_task":
        return {
            "task_title": _normalized_text(action_payload.get("task_title")) or _normalized_text(candidate.get("title")) or _normalized_text(card.get("title")),
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    if normalized_action_type == "update_followup_segment":
        return {
            "followup_segment": _normalized_text(action_payload.get("followup_segment")) or "focus",
        }
    if normalized_action_type == "update_tags":
        add_tag_ids = sorted(
            {
                _normalized_text(item)
                for item in (action_payload.get("add_tag_ids") or action_payload.get("add_tag") or [])
                if _normalized_text(item)
            }
        )
        remove_tag_ids = sorted(
            {
                _normalized_text(item)
                for item in (action_payload.get("remove_tag_ids") or action_payload.get("remove_tag") or [])
                if _normalized_text(item)
            }
        )
        return {
            "add_tag_ids": add_tag_ids,
            "remove_tag_ids": remove_tag_ids,
        }
    if normalized_action_type == "set_followup_reminder":
        return {
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    raise ValueError("unsupported action_type")


def _assert_action_scope(card: dict[str, Any], action_payload: dict[str, Any]) -> None:
    requested_external_userid = _normalized_text(action_payload.get("external_userid"))
    if requested_external_userid and requested_external_userid != _normalized_text(card.get("external_userid")):
        raise ValueError("外部客户标识与当前行动卡不一致")
    raw_external_userids = action_payload.get("external_userids") or []
    if isinstance(raw_external_userids, list):
        normalized_external_userids = [_normalized_text(item) for item in raw_external_userids if _normalized_text(item)]
        if normalized_external_userids and normalized_external_userids != [_normalized_text(card.get("external_userid"))]:
            raise ValueError("不允许跨客户执行 AI 推进行动")
    requested_owner_userid = _normalized_text(action_payload.get("owner_userid"))
    if requested_owner_userid and requested_owner_userid != _normalized_text(card.get("owner_userid")):
        raise ValueError("owner_userid 与当前客户负责人不一致")


def _signal_priority(points: float) -> str:
    numeric = float(points or 0)
    if numeric >= 24:
        return "high"
    if numeric >= 10:
        return "normal"
    return "low"


def _priority_from_score(priority_score: float, *, risk_keys: set[str]) -> str:
    score = float(priority_score or 0)
    high_priority_threshold = float(_high_priority_threshold())
    if score >= high_priority_threshold:
        return "high"
    if score >= max(high_priority_threshold - 25, 35) and risk_keys.intersection(_CRITICAL_RISK_FLAGS):
        return "high"
    if score >= 35:
        return "normal"
    return "low"


def _message_direction(message_row: dict[str, Any], *, external_userid: str) -> str:
    sender = _normalized_text(message_row.get("sender"))
    return "inbound" if sender == _normalized_text(external_userid) else "outbound"


def _contains_any_keyword(content: str, keywords: tuple[str, ...]) -> bool:
    normalized = _normalized_text(content)
    return bool(normalized) and any(keyword in normalized for keyword in keywords)


def _hours_since(moment_text: str) -> float | None:
    moment = _parse_datetime(moment_text)
    if not moment:
        return None
    return max((datetime.now() - moment).total_seconds() / 3600, 0.0)


def _days_since(moment_text: str) -> int | None:
    moment = _parse_datetime(moment_text)
    if not moment:
        return None
    return max((datetime.now() - moment).days, 0)


def _followup_segment_from_marketing_state(marketing_state: dict[str, Any]) -> str:
    payload = _json_loads(marketing_state.get("state_payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    return _normalized_text(
        payload.get("manual_followup_segment")
        or payload.get("followup_segment")
        or payload.get("current_segment")
    ).lower()


def _known_followup_due_at(marketing_state: dict[str, Any], existing_card: dict[str, Any]) -> str:
    existing_status = _normalized_text(existing_card.get("card_status"))
    existing_resolution_note = _normalized_text(existing_card.get("resolution_note"))
    if existing_status == "snoozed" or existing_resolution_note in {
        "next_followup_reminder_set",
        "local_followup_task_created",
    }:
        due_at = _normalized_text(existing_card.get("snooze_until")) or _normalized_text(existing_card.get("due_at"))
        if due_at:
            return due_at
    payload = _json_loads(marketing_state.get("state_payload_json"), default={})
    if not isinstance(payload, dict):
        return ""
    for field_name in _FOLLOWUP_DUE_FIELDS:
        value = _normalized_text(payload.get(field_name))
        if value:
            return value
    return ""


def _ai_assist_payload(ai_row: dict[str, Any]) -> dict[str, Any]:
    if not ai_row:
        return {
            "available": False,
            "confidence": 0.0,
            "draft_message": "",
            "reason": "",
            "output_type": "",
            "output_id": "",
        }
    confidence = float(ai_row.get("confidence") or 0)
    normalized_output = _json_loads(ai_row.get("normalized_output_json"), default={})
    if not isinstance(normalized_output, dict):
        normalized_output = {}
    return {
        "available": confidence >= 0.75,
        "confidence": confidence,
        "draft_message": _normalized_text(
            normalized_output.get("draft_reply")
            or normalized_output.get("draftText")
            or ai_row.get("rendered_output_text")
            or normalized_output.get("reply")
        ),
        "reason": _normalized_text(
            ai_row.get("reason") or normalized_output.get("summary") or normalized_output.get("whyNow")
        ),
        "output_type": _normalized_text(ai_row.get("output_type")),
        "output_id": _normalized_text(ai_row.get("output_id") or ai_row.get("id")),
        "created_at": _normalized_text(ai_row.get("created_at")),
    }


def _make_signal(
    *,
    tenant_key: str,
    external_userid: str,
    owner_userid: str,
    signal_type: str,
    signal_source: str,
    score: float,
    summary: str,
    source_ref_type: str,
    source_ref_id: str,
    source_updated_at: str,
    payload: dict[str, Any],
    evidence: list[dict[str, Any]],
    flag_bucket: str,
    flag_key: str,
    flag_label: str,
) -> dict[str, Any]:
    return {
        "signal_key": customer_pulse_scoped_key(tenant_key=tenant_key, base_key=f"{external_userid}:{signal_type}"),
        "tenant_key": _resolved_tenant_key(tenant_key=tenant_key),
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "signal_type": signal_type,
        "signal_source": signal_source,
        "priority": _signal_priority(score),
        "score": float(score or 0),
        "summary": _normalized_text(summary),
        "source_ref_type": _normalized_text(source_ref_type),
        "source_ref_id": _normalized_text(source_ref_id),
        "source_updated_at": _normalized_text(source_updated_at),
        "payload": {
            **dict(payload or {}),
            "flag_bucket": _normalized_text(flag_bucket),
            "flag_key": _normalized_text(flag_key),
            "flag_label": _normalized_text(flag_label),
        },
        "evidence": _dedupe_evidence(list(evidence or []), limit=3),
    }


def _build_rule_based_draft_message(*, customer_name: str, summary: str, evidence: list[dict[str, Any]]) -> str:
    evidence_detail = next((_normalized_text(item.get("detail")) for item in evidence if _normalized_text(item.get("detail"))), "")
    greeting_name = _normalized_text(customer_name) or "你"
    lines = [f"{greeting_name}，你好。"]
    if evidence_detail:
        lines.append(f"我先根据你刚才提到的情况整理了一版草稿：{evidence_detail}")
    elif _normalized_text(summary):
        lines.append(f"我先根据你目前的进展整理了一版草稿：{_normalized_text(summary)}")
    else:
        lines.append("我先根据你最近的情况整理了一版草稿，供人工确认后再发送。")
    lines.append("如果你方便，我可以继续按你当前最关心的问题帮你梳理下一步。")
    return "\n".join(lines)


def _load_context(
    external_userid: str,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    summary = repo.get_customer_pulse_customer_summary(external_userid)
    marketing_state = repo.get_customer_marketing_state_current(external_userid) or {}
    value_segment = repo.get_customer_value_segment_current(external_userid) or {}
    class_status = repo.get_class_user_status_current(external_userid) or {}
    owner_binding = repo.get_customer_owner_binding(external_userid) or {}
    reply_row = repo.get_latest_reply_monitor_row(external_userid) or {}
    ai_row = repo.get_latest_ai_output_row(external_userid) or {}
    tag_rows = repo.list_contact_tag_rows(external_userid, limit=20)
    messages = repo.list_recent_archived_message_rows(external_userid, limit=20)
    questionnaire_rows = repo.list_recent_questionnaire_rows(external_userid, limit=5)
    dispatch_rows = repo.list_recent_conversion_dispatch_rows(external_userid, limit=5)
    latest_snapshot = repo.get_latest_customer_pulse_snapshot_for_external_userid(external_userid, tenant_key=resolved_tenant_key) or {}
    existing_card = repo.get_latest_customer_pulse_card_for_external_userid(external_userid, tenant_key=resolved_tenant_key) or {}
    ai_assist = _ai_assist_payload(ai_row)
    return {
        "summary": summary,
        "marketing_state": marketing_state,
        "value_segment": value_segment,
        "class_status": class_status,
        "owner_binding": owner_binding,
        "reply_row": reply_row,
        "ai_row": ai_row,
        "ai_assist": ai_assist,
        "tag_rows": tag_rows,
        "messages": messages,
        "questionnaire_rows": questionnaire_rows,
        "dispatch_rows": dispatch_rows,
        "latest_snapshot": latest_snapshot,
        "existing_card": existing_card,
        "tenant_key": resolved_tenant_key,
        "tenant_context": resolved_context,
    }


def _build_rule_signals(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = context["summary"]
    marketing_state = context["marketing_state"]
    value_segment = context["value_segment"]
    class_status = context["class_status"]
    owner_binding = context["owner_binding"]
    reply_row = context["reply_row"]
    tag_rows = context["tag_rows"]
    messages = context["messages"]
    questionnaire_rows = context["questionnaire_rows"]
    dispatch_rows = context["dispatch_rows"]
    existing_card = context["existing_card"]

    tenant_key = _resolved_tenant_key(
        tenant_context=context.get("tenant_context"),
        tenant_key=_normalized_text(context.get("tenant_key")),
    )
    external_userid = _normalized_text(summary.get("external_userid"))
    owner_userid = _normalized_text(summary.get("owner_userid"))
    stage_key = "/".join(
        part
        for part in [
            _normalized_text(marketing_state.get("main_stage")),
            _normalized_text(marketing_state.get("sub_stage")),
        ]
        if part
    )
    value_segment_name = _normalized_text(value_segment.get("segment")).lower()
    current_followup_segment = _followup_segment_from_marketing_state(marketing_state)

    inbound_messages = [row for row in messages if _message_direction(row, external_userid=external_userid) == "inbound"]
    outbound_messages = [row for row in messages if _message_direction(row, external_userid=external_userid) == "outbound"]
    latest_inbound = inbound_messages[0] if inbound_messages else {}
    latest_outbound = outbound_messages[0] if outbound_messages else {}
    last_interaction_at = _normalized_text((messages[0] if messages else {}).get("send_time"))
    last_inbound_at = _normalized_text(latest_inbound.get("send_time"))
    last_outbound_at = _normalized_text(latest_outbound.get("send_time"))
    known_followup_due_at = _known_followup_due_at(marketing_state, existing_card)

    signals: list[dict[str, Any]] = []

    reply_status = _normalized_text(reply_row.get("status")).lower()
    reply_snapshot = _json_loads(reply_row.get("payload_snapshot_json"), default={})
    if not isinstance(reply_snapshot, dict):
        reply_snapshot = {}
    waiting_hours = _hours_since(reply_row.get("last_inbound_at") or reply_row.get("updated_at") or reply_row.get("created_at"))
    if reply_row and reply_status not in {"done", "resolved", "completed", "cancelled"}:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="unanswered_question",
                signal_source="automation_reply_monitor_queue",
                score=36 if (waiting_hours or 0) < 24 else 42,
                summary="客户存在未处理问题，当前应优先给出可确认的回复草稿。",
                source_ref_type="automation_reply_monitor_queue",
                source_ref_id=_normalized_text(reply_row.get("id")),
                source_updated_at=_normalized_text(reply_row.get("updated_at") or reply_row.get("created_at")),
                payload={
                    "reply_queue_status": reply_status or "pending",
                    "waiting_hours": round(float(waiting_hours or 0), 1),
                    "message_count": int(reply_row.get("message_count") or 0),
                    "not_before": _normalized_text(reply_row.get("not_before")),
                },
                evidence=[
                    {
                        "title": "待回复窗口",
                        "detail": _safe_preview(
                            reply_snapshot.get("latest_inbound_summary")
                            or reply_snapshot.get("last_message_summary")
                            or latest_inbound.get("content")
                            or "客户有待回复消息"
                        ),
                        "event_time": _normalized_text(reply_row.get("last_inbound_at") or reply_row.get("updated_at")),
                        "source": "automation_reply_monitor_queue",
                    }
                ],
                flag_bucket="risk",
                flag_key="unanswered_question",
                flag_label="存在未回复问题",
            )
        )
    elif latest_inbound:
        latest_inbound_time = _parse_datetime(latest_inbound.get("send_time"))
        latest_outbound_time = _parse_datetime(latest_outbound.get("send_time"))
        latest_inbound_content = _normalized_text(latest_inbound.get("content"))
        if (
            latest_inbound_time
            and latest_inbound_time >= datetime.now() - timedelta(hours=72)
            and (not latest_outbound_time or latest_inbound_time > latest_outbound_time)
            and _contains_any_keyword(latest_inbound_content, _QUESTION_HINT_KEYWORDS)
        ):
            signals.append(
                _make_signal(
                    tenant_key=tenant_key,
                    external_userid=external_userid,
                    owner_userid=owner_userid,
                    signal_type="unanswered_question",
                    signal_source="archived_messages",
                    score=30,
                    summary="最近一轮客户提问后尚未形成有效回复，建议先处理这条对话。",
                    source_ref_type="archived_messages",
                    source_ref_id=_normalized_text(latest_inbound.get("id") or latest_inbound.get("msgid")),
                    source_updated_at=_normalized_text(latest_inbound.get("send_time")),
                    payload={
                        "waiting_hours": round(float(_hours_since(latest_inbound.get("send_time")) or 0), 1),
                    },
                    evidence=[
                        {
                            "title": "最近一条客户消息",
                            "detail": _safe_preview(latest_inbound_content),
                            "event_time": _normalized_text(latest_inbound.get("send_time")),
                            "source": "archived_messages",
                        }
                    ],
                    flag_bucket="risk",
                    flag_key="unanswered_question",
                    flag_label="存在未回复问题",
                )
            )

    negative_message = next(
        (
            row
            for row in inbound_messages
            if _contains_any_keyword(row.get("content"), _NEGATIVE_MESSAGE_KEYWORDS)
            and (_parse_datetime(row.get("send_time")) or datetime.min) >= datetime.now() - timedelta(days=7)
        ),
        {},
    )
    if negative_message:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="negative_sentiment",
                signal_source="archived_messages",
                score=28,
                summary="客户近期表达了负向情绪或投诉倾向，建议先人工介入。",
                source_ref_type="archived_messages",
                source_ref_id=_normalized_text(negative_message.get("id") or negative_message.get("msgid")),
                source_updated_at=_normalized_text(negative_message.get("send_time")),
                payload={"matched_keywords": [item for item in _NEGATIVE_MESSAGE_KEYWORDS if item in _normalized_text(negative_message.get("content"))]},
                evidence=[
                    {
                        "title": "近期负向表达",
                        "detail": _safe_preview(negative_message.get("content")),
                        "event_time": _normalized_text(negative_message.get("send_time")),
                        "source": "archived_messages",
                    }
                ],
                flag_bucket="risk",
                flag_key="negative_sentiment",
                flag_label="近期负向情绪/投诉",
            )
        )

    latest_questionnaire = questionnaire_rows[0] if questionnaire_rows else {}
    questionnaire_status = _normalized_text(latest_questionnaire.get("scrm_apply_status")).lower()
    questionnaire_error = _normalized_text(latest_questionnaire.get("scrm_apply_error"))
    latest_dispatch = dispatch_rows[0] if dispatch_rows else {}
    dispatch_status = _normalized_text(latest_dispatch.get("dispatch_status")).lower()
    dispatch_age_hours = _hours_since(
        latest_dispatch.get("dispatched_at") or latest_dispatch.get("updated_at") or latest_dispatch.get("created_at")
    )
    class_sync_status = _normalized_text(class_status.get("wecom_tag_sync_status")).lower()
    service_exception_evidence: list[dict[str, Any]] = []
    service_exception_payload: dict[str, Any] = {}
    if questionnaire_status in {"failed", "error"} or questionnaire_error:
        service_exception_payload["questionnaire_apply_status"] = questionnaire_status or "failed"
        service_exception_payload["questionnaire_apply_error"] = questionnaire_error
        service_exception_evidence.append(
            {
                "title": "问卷结果回写异常",
                "detail": questionnaire_error or f"状态 {questionnaire_status}",
                "event_time": _normalized_text(latest_questionnaire.get("scrm_apply_at") or latest_questionnaire.get("submitted_at")),
                "source": "questionnaire_scrm_apply_logs",
            }
        )
    if dispatch_status not in _SAFE_DISPATCH_STATUSES and dispatch_status:
        service_exception_payload["dispatch_status"] = dispatch_status
        service_exception_evidence.append(
            {
                "title": "转化派发异常",
                "detail": _normalized_text(latest_dispatch.get("dispatch_note")) or f"状态 {dispatch_status}",
                "event_time": _normalized_text(latest_dispatch.get("updated_at") or latest_dispatch.get("created_at")),
                "source": "conversion_dispatch_log",
            }
        )
    elif dispatch_status in {"pending", "blocked_quiet_hours"} and (dispatch_age_hours or 0) >= 24:
        service_exception_payload["dispatch_status"] = dispatch_status
        service_exception_payload["dispatch_wait_hours"] = round(float(dispatch_age_hours or 0), 1)
        service_exception_evidence.append(
            {
                "title": "转化派发停留过久",
                "detail": f"状态 {dispatch_status} · 已等待 {round(float(dispatch_age_hours or 0), 1)} 小时",
                "event_time": _normalized_text(latest_dispatch.get("updated_at") or latest_dispatch.get("created_at")),
                "source": "conversion_dispatch_log",
            }
        )
    if class_sync_status == "failed":
        service_exception_payload["tag_sync_status"] = class_sync_status
        service_exception_payload["tag_sync_error"] = _normalized_text(class_status.get("wecom_tag_sync_error"))
        service_exception_evidence.append(
            {
                "title": "标签同步异常",
                "detail": _normalized_text(class_status.get("wecom_tag_sync_error")) or "报名/班级状态标签同步失败",
                "event_time": _normalized_text(class_status.get("updated_at") or class_status.get("set_at")),
                "source": "class_user_status_current",
            }
        )
    if service_exception_evidence:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="service_exception",
                signal_source=service_exception_evidence[0]["source"],
                score=24,
                summary="客户最近存在服务或派发异常，建议先人工确认并补动作。",
                source_ref_type=service_exception_evidence[0]["source"],
                source_ref_id=_normalized_text(latest_questionnaire.get("id") or latest_dispatch.get("id") or class_status.get("external_userid")),
                source_updated_at=_normalized_text(
                    latest_questionnaire.get("scrm_apply_at")
                    or latest_dispatch.get("updated_at")
                    or class_status.get("updated_at")
                    or latest_questionnaire.get("submitted_at")
                ),
                payload=service_exception_payload,
                evidence=service_exception_evidence,
                flag_bucket="risk",
                flag_key="service_exception",
                flag_label="订单/服务异常",
            )
        )

    detail_parts = []
    if stage_key:
        detail_parts.append(_stage_label(marketing_state.get("main_stage"), marketing_state.get("sub_stage")))
    if value_segment_name:
        detail_parts.append(f"价值分层 {_segment_label(value_segment_name)}")
    if value_segment_name in _HIGH_INTENT_SEGMENTS or stage_key in _HIGH_INTENT_STAGE_KEYS:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="high_intent_stage",
                signal_source="customer_marketing_state_current",
                score=18,
                summary="客户处于高优先级推进段，今天的推进收益更高。",
                source_ref_type="customer_marketing_state_current",
                source_ref_id=_normalized_text(marketing_state.get("id") or value_segment.get("id")),
                source_updated_at=_normalized_text(marketing_state.get("updated_at") or value_segment.get("updated_at")),
                payload={
                    "main_stage": _normalized_text(marketing_state.get("main_stage")),
                    "sub_stage": _normalized_text(marketing_state.get("sub_stage")),
                    "segment": value_segment_name,
                    "current_followup_segment": current_followup_segment,
                },
                evidence=[
                    {
                        "title": "当前推进阶段",
                        "detail": " · ".join(detail_parts) or "命中高意向阶段规则",
                        "event_time": _normalized_text(marketing_state.get("updated_at") or value_segment.get("updated_at")),
                        "source": "customer_marketing_state_current",
                    }
                ],
                flag_bucket="opportunity",
                flag_key="high_intent_stage",
                flag_label="高意向阶段",
            )
        )

    high_intent_tags = [
        _normalized_text(item.get("tag_name") or item.get("tag_id"))
        for item in tag_rows
        if any(keyword in _normalized_text(item.get("tag_name") or item.get("tag_id")) for keyword in _HIGH_INTENT_TAG_KEYWORDS)
    ]
    if high_intent_tags:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="high_intent_tag",
                signal_source="contact_tags",
                score=10,
                summary="客户标签显示当前仍需推进，可直接复用到行动卡解释。",
                source_ref_type="contact_tags",
                source_ref_id="",
                source_updated_at=_normalized_text((tag_rows[0] if tag_rows else {}).get("created_at")),
                payload={"tag_names": high_intent_tags},
                evidence=[
                    {
                        "title": "命中客户标签",
                        "detail": "、".join(high_intent_tags[:3]),
                        "event_time": _normalized_text((tag_rows[0] if tag_rows else {}).get("created_at")),
                        "source": "contact_tags",
                    }
                ],
                flag_bucket="opportunity",
                flag_key="high_intent_tag",
                flag_label="高意向标签",
            )
        )

    high_intent_message = next(
        (
            row
            for row in inbound_messages
            if _contains_any_keyword(row.get("content"), _HIGH_INTENT_MESSAGE_KEYWORDS)
            and (_parse_datetime(row.get("send_time")) or datetime.min) >= datetime.now() - timedelta(days=7)
        ),
        {},
    )
    latest_questionnaire_time = _parse_datetime(latest_questionnaire.get("submitted_at"))
    if high_intent_message or (latest_questionnaire and latest_questionnaire_time and latest_questionnaire_time >= datetime.now() - timedelta(days=7)):
        evidence: list[dict[str, Any]] = []
        if high_intent_message:
            evidence.append(
                {
                    "title": "近期高意向表达",
                    "detail": _safe_preview(high_intent_message.get("content")),
                    "event_time": _normalized_text(high_intent_message.get("send_time")),
                    "source": "archived_messages",
                }
            )
        if latest_questionnaire:
            evidence.append(
                {
                    "title": "近期问卷提交",
                    "detail": f"{_normalized_text(latest_questionnaire.get('questionnaire_title') or latest_questionnaire.get('questionnaire_name')) or '问卷'} · score={latest_questionnaire.get('total_score') or 0}",
                    "event_time": _normalized_text(latest_questionnaire.get("submitted_at")),
                    "source": "questionnaire_submissions",
                }
            )
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="high_intent_behavior",
                signal_source="archived_messages" if high_intent_message else "questionnaire_submissions",
                score=16,
                summary="客户最近出现高意向行为，今天处理更容易推动下一步。",
                source_ref_type="archived_messages" if high_intent_message else "questionnaire_submissions",
                source_ref_id=_normalized_text(high_intent_message.get("id") or latest_questionnaire.get("id")),
                source_updated_at=_normalized_text(high_intent_message.get("send_time") or latest_questionnaire.get("submitted_at")),
                payload={
                    "questionnaire_score": latest_questionnaire.get("total_score"),
                    "has_high_intent_message": bool(high_intent_message),
                },
                evidence=evidence,
                flag_bucket="opportunity",
                flag_key="high_intent_behavior",
                flag_label="近期高意向行为",
            )
        )

    stage_anchor = (
        _normalized_text(marketing_state.get("entered_at"))
        or _normalized_text(marketing_state.get("updated_at"))
        or _normalized_text(marketing_state.get("last_message_at"))
    )
    stage_stalled_days = _days_since(stage_anchor)
    if stage_stalled_days is not None and stage_stalled_days >= 3 and stage_key != "converted/enrolled":
        points = 12 if stage_stalled_days < 7 else 20 if stage_stalled_days < 14 else 28
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="stage_stalled",
                signal_source="customer_marketing_state_current",
                score=points,
                summary=f"客户在当前阶段已停留 {stage_stalled_days} 天，推进节奏明显变慢。",
                source_ref_type="customer_marketing_state_current",
                source_ref_id=_normalized_text(marketing_state.get("id")),
                source_updated_at=_normalized_text(marketing_state.get("updated_at") or stage_anchor),
                payload={
                    "stage_stalled_days": stage_stalled_days,
                    "stage_key": stage_key,
                },
                evidence=[
                    {
                        "title": "阶段停滞",
                        "detail": f"{_stage_label(marketing_state.get('main_stage'), marketing_state.get('sub_stage'))} 已停留 {stage_stalled_days} 天",
                        "event_time": stage_anchor,
                        "source": "customer_marketing_state_current",
                    }
                ],
                flag_bucket="risk",
                flag_key="stage_stalled",
                flag_label="阶段停滞",
            )
        )

    if not known_followup_due_at and (
        any(item["signal_type"] == "high_intent_stage" for item in signals)
        or any(item["signal_type"] == "stage_stalled" for item in signals)
        or any(item["signal_type"] == "unanswered_question" for item in signals)
    ):
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="missing_followup_time",
                signal_source="customer_marketing_state_current",
                score=14,
                summary="当前客户没有明确的下一次跟进时间，容易继续停滞。",
                source_ref_type="customer_marketing_state_current",
                source_ref_id=_normalized_text(marketing_state.get("id") or existing_card.get("id")),
                source_updated_at=_normalized_text(marketing_state.get("updated_at") or existing_card.get("updated_at")),
                payload={"known_followup_due_at": known_followup_due_at},
                evidence=[
                    {
                        "title": "缺少下次跟进时间",
                        "detail": "营销状态与现有行动卡中都没有明确的下一次跟进时间",
                        "event_time": _normalized_text(marketing_state.get("updated_at") or existing_card.get("updated_at")),
                        "source": "customer_marketing_state_current",
                    }
                ],
                flag_bucket="risk",
                flag_key="missing_followup_time",
                flag_label="缺少下次跟进时间",
            )
        )

    interaction_gap_days = _days_since(last_interaction_at)
    if (
        interaction_gap_days is not None
        and interaction_gap_days >= 7
        and (
            value_segment_name in _HIGH_INTENT_SEGMENTS
            or stage_key in _HIGH_INTENT_STAGE_KEYS
            or bool(marketing_state.get("eligible_for_conversion"))
        )
    ):
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="interaction_stale",
                signal_source="archived_messages",
                score=12,
                summary=f"最近 {interaction_gap_days} 天没有新的有效互动，客户可能正在流失。",
                source_ref_type="archived_messages",
                source_ref_id=_normalized_text((messages[0] if messages else {}).get("id")),
                source_updated_at=last_interaction_at,
                payload={"interaction_gap_days": interaction_gap_days},
                evidence=[
                    {
                        "title": "最近互动时间",
                        "detail": last_interaction_at or "暂无消息记录",
                        "event_time": last_interaction_at,
                        "source": "archived_messages",
                    }
                ],
                flag_bucket="risk",
                flag_key="interaction_stale",
                flag_label="最近互动间隔过长",
            )
        )

    if interaction_gap_days is not None and interaction_gap_days <= 1 and (
        value_segment_name in _HIGH_INTENT_SEGMENTS or any(item["signal_type"] == "unanswered_question" for item in signals)
    ):
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="recent_engagement",
                signal_source="archived_messages",
                score=8,
                summary="客户最近 24 小时内仍在互动，及时处理更容易转成下一步动作。",
                source_ref_type="archived_messages",
                source_ref_id=_normalized_text((messages[0] if messages else {}).get("id")),
                source_updated_at=last_interaction_at,
                payload={"last_interaction_at": last_interaction_at},
                evidence=[
                    {
                        "title": "最近互动",
                        "detail": _safe_preview((messages[0] if messages else {}).get("content")),
                        "event_time": last_interaction_at,
                        "source": "archived_messages",
                    }
                ],
                flag_bucket="opportunity",
                flag_key="recent_engagement",
                flag_label="最近仍有互动",
            )
        )

    owner_change_days = _days_since(owner_binding.get("updated_at") or summary.get("binding_updated_at"))
    first_owner = _normalized_text(owner_binding.get("first_owner_userid") or summary.get("first_owner_userid"))
    last_owner = _normalized_text(owner_binding.get("last_owner_userid") or summary.get("last_owner_userid"))
    if first_owner and last_owner and first_owner != last_owner and owner_change_days is not None and owner_change_days <= 14:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="owner_changed_recently",
                signal_source="external_contact_bindings",
                score=8,
                summary="客户负责人近期发生变更，交接阶段容易漏掉跟进动作。",
                source_ref_type="external_contact_bindings",
                source_ref_id=external_userid,
                source_updated_at=_normalized_text(owner_binding.get("updated_at") or summary.get("binding_updated_at")),
                payload={
                    "first_owner_userid": first_owner,
                    "last_owner_userid": last_owner,
                    "owner_change_days": owner_change_days,
                },
                evidence=[
                    {
                        "title": "负责人变更",
                        "detail": f"{first_owner} -> {last_owner}",
                        "event_time": _normalized_text(owner_binding.get("updated_at") or summary.get("binding_updated_at")),
                        "source": "external_contact_bindings",
                    }
                ],
                flag_bucket="risk",
                flag_key="owner_changed_recently",
                flag_label="负责人近期变更",
            )
        )

    metrics = {
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "last_interaction_at": last_interaction_at,
        "last_inbound_at": last_inbound_at,
        "last_outbound_at": last_outbound_at,
        "interaction_gap_days": interaction_gap_days,
        "stage_stalled_days": stage_stalled_days,
        "known_followup_due_at": known_followup_due_at,
        "current_followup_segment": current_followup_segment,
        "stage_key": stage_key,
        "value_segment": value_segment_name,
    }
    return signals, metrics


def _persist_signals(
    external_userid: str,
    *,
    signals: list[dict[str, Any]],
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    active_signal_keys: list[str] = []
    resolved_tenant_key = _resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key)
    for signal in signals:
        active_signal_keys.append(signal["signal_key"])
        persisted.append(
            repo.upsert_customer_pulse_signal_event(
                signal_key=signal["signal_key"],
                tenant_key=resolved_tenant_key,
                external_userid=signal["external_userid"],
                owner_userid=signal["owner_userid"],
                signal_type=signal["signal_type"],
                signal_source=signal["signal_source"],
                signal_status="open",
                priority=signal["priority"],
                evidence=signal["evidence"],
                source_ref_type=signal["source_ref_type"],
                source_ref_id=signal["source_ref_id"],
                source_updated_at=signal["source_updated_at"],
                score=float(signal.get("score") or 0),
                summary=signal["summary"],
                payload=signal["payload"],
            )
        )
    repo.resolve_customer_pulse_stale_signals_by_tenant(
        external_userid,
        active_signal_keys=active_signal_keys,
        tenant_key=resolved_tenant_key,
    )
    return persisted


def _build_scoring(signals: list[dict[str, Any]], *, metrics: dict[str, Any]) -> dict[str, Any]:
    if not signals:
        return {
            "priority_score": 0.0,
            "priority": "low",
            "risk_flags": [],
            "opportunity_flags": [],
            "score_breakdown": [],
            "confidence": None,
            "source_updated_at": "",
        }
    ordered_signals = sorted(signals, key=lambda item: (float(item.get("score") or 0), _normalized_text(item.get("source_updated_at"))), reverse=True)
    raw_score = sum(float(item.get("score") or 0) for item in ordered_signals)
    priority_score = round(min(raw_score, 100.0), 2)
    risk_flags: list[dict[str, Any]] = []
    opportunity_flags: list[dict[str, Any]] = []
    score_breakdown: list[dict[str, Any]] = []
    seen_flag_keys: set[str] = set()
    risk_keys: set[str] = set()
    for signal in ordered_signals:
        payload = _json_loads(signal.get("payload_json") or signal.get("payload"), default={})
        if not isinstance(payload, dict):
            payload = {}
        flag_bucket = _normalized_text(payload.get("flag_bucket"))
        flag_key = _normalized_text(payload.get("flag_key"))
        flag_label = _normalized_text(payload.get("flag_label")) or flag_key or _normalized_text(signal.get("signal_type"))
        evidence = _dedupe_evidence(_json_loads(signal.get("evidence_json") or signal.get("evidence"), default=[]), limit=2)
        score_entry = {
            "signal_type": _normalized_text(signal.get("signal_type")),
            "label": flag_label,
            "category": flag_bucket or "neutral",
            "score": round(float(signal.get("score") or 0), 2),
            "summary": _normalized_text(signal.get("summary")),
            "evidence": evidence,
        }
        score_breakdown.append(score_entry)
        if not flag_key or flag_key in seen_flag_keys:
            continue
        seen_flag_keys.add(flag_key)
        flag_entry = {
            "key": flag_key,
            "label": flag_label,
            "score": round(float(signal.get("score") or 0), 2),
            "summary": _normalized_text(signal.get("summary")),
            "evidence": evidence,
        }
        if flag_bucket == "risk":
            risk_keys.add(flag_key)
            risk_flags.append(flag_entry)
        elif flag_bucket == "opportunity":
            opportunity_flags.append(flag_entry)

    priority = _priority_from_score(priority_score, risk_keys=risk_keys)
    confidence = round(min(0.98, max(priority_score / 100, 0.35)), 4)
    source_updated_at = max(
        [_normalized_text(item.get("source_updated_at")) for item in ordered_signals if _normalized_text(item.get("source_updated_at"))],
        default=_normalized_text(metrics.get("last_interaction_at")),
    )
    return {
        "priority_score": priority_score,
        "priority": priority,
        "risk_flags": risk_flags,
        "opportunity_flags": opportunity_flags,
        "score_breakdown": score_breakdown,
        "confidence": confidence,
        "source_updated_at": source_updated_at,
    }


def _build_action_candidates(context: dict[str, Any], *, scoring: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    summary = context["summary"]
    marketing_state = context["marketing_state"]
    value_segment = context["value_segment"]
    ai_assist = context["ai_assist"]
    risk_keys = {item["key"] for item in scoring["risk_flags"]}
    opportunity_keys = {item["key"] for item in scoring["opportunity_flags"]}
    evidence = _dedupe_evidence(
        [
            evidence_item
            for flag in [*scoring["risk_flags"], *scoring["opportunity_flags"]]
            for evidence_item in flag.get("evidence", [])
            if isinstance(evidence_item, dict)
        ],
        limit=4,
    )

    candidates: list[dict[str, Any]] = []
    seen_action_types: set[str] = set()

    def add_candidate(
        *,
        action_type: str,
        title: str,
        reason: str,
        payload: dict[str, Any],
        candidate_score: float,
        evidence_items: list[dict[str, Any]] | None = None,
    ) -> None:
        if action_type in seen_action_types:
            return
        seen_action_types.add(action_type)
        candidates.append(
            {
                "rank": len(candidates) + 1,
                "action_type": action_type,
                "action_label": _action_label(action_type),
                "title": _normalized_text(title) or _action_label(action_type),
                "reason": _normalized_text(reason),
                "candidate_score": round(float(candidate_score or 0), 2),
                "need_human_confirmation": True,
                "payload": dict(payload or {}),
                "evidence": _dedupe_evidence(list(evidence_items or evidence), limit=3),
            }
        )

    customer_name = _normalized_text(summary.get("customer_name")) or _normalized_text(summary.get("external_userid"))
    primary_reason = "；".join(
        [
            "、".join(item["label"] for item in scoring["risk_flags"][:2]) if scoring["risk_flags"] else "",
            "、".join(item["label"] for item in scoring["opportunity_flags"][:2]) if scoring["opportunity_flags"] else "",
        ]
    ).strip("；")

    if risk_keys.intersection({"negative_sentiment", "service_exception"}):
        add_candidate(
            action_type="create_followup_task",
            title="优先安排人工介入",
            reason=primary_reason or "客户当前存在投诉、异常或服务风险，需要人工先接住。",
            payload={
                "task_title": "人工跟进客户异常/投诉",
                "due_at": _soon_followup_time(hours=2),
            },
            candidate_score=scoring["priority_score"] + 5,
        )

    if "unanswered_question" in risk_keys:
        draft_message = _normalized_text(ai_assist.get("draft_message"))
        if not draft_message:
            draft_message = _build_rule_based_draft_message(
                customer_name=customer_name,
                summary=primary_reason or "客户近期有待处理问题",
                evidence=evidence,
            )
        add_candidate(
            action_type="generate_reply_draft",
            title="先生成一版回复草稿",
            reason=primary_reason or "客户最近的问题还没有被接住，先准备一版草稿供人工确认。",
            payload={
                "channel_type": "existing_customer_channel",
                "draft_message": draft_message,
                "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
                "due_at": _normalized_text(context["reply_row"].get("not_before"))
                or _normalized_text(metrics.get("last_inbound_at"))
                or _normalized_text(scoring.get("source_updated_at")),
            },
            candidate_score=scoring["priority_score"] + (5 if ai_assist.get("available") else 0),
        )

    current_followup_segment = _followup_segment_from_marketing_state(marketing_state)
    value_segment_name = _normalized_text(value_segment.get("segment")).lower()
    if opportunity_keys.intersection({"high_intent_stage", "high_intent_behavior"}) and current_followup_segment != "focus" and value_segment_name in {
        "top",
        "core",
        "focus",
    }:
        add_candidate(
            action_type="update_followup_segment",
            title="升级为重点跟进",
            reason=primary_reason or "客户已进入高意向推进段，当前应切到重点跟进。",
            payload={"followup_segment": "focus"},
            candidate_score=scoring["priority_score"],
        )

    if risk_keys.intersection({"stage_stalled", "missing_followup_time", "interaction_stale"}):
        add_candidate(
            action_type="set_followup_reminder",
            title="补上下次跟进提醒",
            reason=primary_reason or "当前推进节奏已经变慢，需要明确下一次跟进时间。",
            payload={"due_at": _normalized_text(metrics.get("known_followup_due_at")) or _next_followup_time()},
            candidate_score=max(scoring["priority_score"] - 3, 0),
        )

    if (
        opportunity_keys.intersection({"high_intent_stage", "high_intent_behavior", "high_intent_tag"})
        and risk_keys.intersection({"stage_stalled", "interaction_stale", "missing_followup_time"})
    ):
        add_candidate(
            action_type="create_followup_task",
            title="补一个高优先级跟进任务",
            reason=primary_reason or "客户有推进价值，但最近缺少明确动作，建议先补任务。",
            payload={
                "task_title": "跟进高意向客户",
                "due_at": _next_followup_time(),
            },
            candidate_score=max(scoring["priority_score"] - 1, 0),
        )

    if not candidates and scoring["priority_score"] >= 25:
        add_candidate(
            action_type="set_followup_reminder",
            title="安排下一次跟进提醒",
            reason=primary_reason or "当前没有更强动作，先补一个明确提醒并等待人工确认。",
            payload={"due_at": _next_followup_time()},
            candidate_score=scoring["priority_score"],
        )
    return candidates


def _merge_ai_recommendation_into_candidates(
    *,
    candidates: list[dict[str, Any]],
    recommendation_result: dict[str, Any],
    default_evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if _normalized_text(recommendation_result.get("status")) != "accepted":
        return candidates, default_evidence
    recommendation = recommendation_result.get("recommendation") or {}
    if not isinstance(recommendation, dict):
        return candidates, default_evidence
    action_type = _normalized_text(recommendation.get("actionType"))
    if not action_type:
        return candidates, default_evidence
    match_index = next(
        (index for index, item in enumerate(candidates) if _normalized_text(item.get("action_type")) == action_type),
        -1,
    )
    if match_index < 0:
        return candidates, default_evidence

    merged_candidates = [dict(item) for item in candidates]
    matched_candidate = dict(merged_candidates.pop(match_index))
    matched_candidate["source"] = "ai"
    matched_candidate["title"] = _normalized_text(recommendation.get("actionTitle")) or _normalized_text(matched_candidate.get("title"))
    matched_candidate["reason"] = _normalized_text(recommendation.get("whyNow")) or _normalized_text(recommendation.get("summary")) or _normalized_text(
        matched_candidate.get("reason")
    )
    matched_candidate["why_now"] = _normalized_text(recommendation.get("whyNow"))
    matched_candidate["ai_summary"] = _normalized_text(recommendation.get("summary"))
    matched_candidate["candidate_score"] = round(
        max(float(matched_candidate.get("candidate_score") or 0), float(recommendation.get("confidence") or 0) * 100),
        2,
    )
    matched_candidate["evidence"] = _dedupe_evidence(
        [
            *list(recommendation_result.get("resolved_evidence") or []),
            *list(matched_candidate.get("evidence") or []),
            *list(default_evidence or []),
        ],
        limit=4,
    )
    payload = dict(matched_candidate.get("payload") or {})
    safe_field_updates = recommendation.get("safeFieldUpdates") if isinstance(recommendation.get("safeFieldUpdates"), dict) else {}
    if action_type == "generate_reply_draft":
        draft_message = _normalized_text(recommendation.get("draftText"))
        if draft_message:
            payload["draft_message"] = draft_message
    if action_type == "update_followup_segment" and _normalized_text(safe_field_updates.get("followupSegment")):
        payload["followup_segment"] = _normalized_text(safe_field_updates.get("followupSegment"))
    if action_type in {"set_followup_reminder", "create_followup_task"} and _normalized_text(safe_field_updates.get("nextFollowupAt")):
        payload["due_at"] = _normalized_text(safe_field_updates.get("nextFollowupAt"))
    if action_type == "update_tags":
        payload["add_tag_ids"] = [
            _normalized_text(item) for item in (safe_field_updates.get("addTagIds") or []) if _normalized_text(item)
        ]
        payload["remove_tag_ids"] = [
            _normalized_text(item) for item in (safe_field_updates.get("removeTagIds") or []) if _normalized_text(item)
        ]
    payload["ai_recommendation"] = {
        "summary": _normalized_text(recommendation.get("summary")),
        "why_now": _normalized_text(recommendation.get("whyNow")),
        "confidence": round(float(recommendation.get("confidence") or 0), 4),
        "evidence_refs": recommendation.get("evidenceRefs") or [],
        "safe_field_updates": safe_field_updates,
        "provider": _normalized_text(recommendation_result.get("provider")),
    }
    matched_candidate["payload"] = payload
    merged_candidates.insert(0, matched_candidate)
    primary_evidence = _dedupe_evidence(
        [
            *list(recommendation_result.get("resolved_evidence") or []),
            *list(default_evidence or []),
        ],
        limit=6,
    )
    return merged_candidates, primary_evidence or default_evidence


def _suppress_reply_draft_when_ai_is_untrusted(
    *,
    candidates: list[dict[str, Any]],
    recommendation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    if not candidates:
        return candidates
    if _normalized_text(recommendation_result.get("status")) != "fallback":
        return candidates
    fallback_reason = _normalized_text(recommendation_result.get("fallback_reason"))
    if fallback_reason not in {"low_confidence", "invalid_or_blocked_ai_output"}:
        return candidates
    first_candidate = dict(candidates[0])
    if _normalized_text(first_candidate.get("action_type")) != "generate_reply_draft":
        return candidates
    payload = dict(first_candidate.get("payload") or {})
    payload["draft_message"] = ""
    payload["draft_blocked_by_ai"] = True
    payload["draft_block_reason"] = fallback_reason
    payload["draft_notice"] = "AI 置信度不足或命中风控，当前不默认生成外发草稿，请人工编辑后再保存草稿。"
    first_candidate["payload"] = payload
    first_candidate["draft_blocked_by_ai"] = True
    return [first_candidate, *[dict(item) for item in candidates[1:]]]


def _card_title(primary_candidate: dict[str, Any]) -> str:
    if _normalized_text(primary_candidate.get("source")) == "ai" and _normalized_text(primary_candidate.get("title")):
        return _normalized_text(primary_candidate.get("title"))
    mapping = {
        "generate_reply_draft": "今天先处理客户回复",
        "create_followup_task": "优先安排客户跟进动作",
        "update_followup_segment": "建议升级为重点跟进",
        "set_followup_reminder": "安排下一次跟进提醒",
        "update_tags": "补齐客户标签",
    }
    action_type = _normalized_text(primary_candidate.get("action_type"))
    return mapping.get(action_type, _normalized_text(primary_candidate.get("title")) or "客户推进行动卡")


def _card_summary(scoring: dict[str, Any], *, primary_candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    if scoring["risk_flags"]:
        parts.append("风险：" + "、".join(item["label"] for item in scoring["risk_flags"][:2]))
    if scoring["opportunity_flags"]:
        parts.append("机会：" + "、".join(item["label"] for item in scoring["opportunity_flags"][:2]))
    primary_reason = _normalized_text(primary_candidate.get("why_now") or primary_candidate.get("reason"))
    if primary_reason:
        parts.append("建议：" + primary_reason)
    return "；".join(part for part in parts if part)


def _stable_ai_payload(value: Any) -> dict[str, Any]:
    payload = _json_loads(value, default={})
    if not isinstance(payload, dict):
        return {}
    stable_payload = dict(payload)
    for key in {"run_id", "request_id", "output_id", "generated_at", "trace"}:
        stable_payload.pop(key, None)
    recommendation = stable_payload.get("recommendation")
    if isinstance(recommendation, dict):
        stable_payload["recommendation"] = {
            "summary": _normalized_text(recommendation.get("summary")),
            "actionType": _normalized_text(recommendation.get("actionType")),
            "actionTitle": _normalized_text(recommendation.get("actionTitle")),
            "whyNow": _normalized_text(recommendation.get("whyNow")),
            "evidenceRefs": recommendation.get("evidenceRefs") or [],
            "draftText": _normalized_text(recommendation.get("draftText")),
            "confidence": round(float(recommendation.get("confidence") or 0), 4),
            "safeFieldUpdates": recommendation.get("safeFieldUpdates") or {},
        }
    return stable_payload


def _snapshot_matches(latest_snapshot: dict[str, Any], *, incoming: dict[str, Any]) -> bool:
    if not latest_snapshot:
        return False
    comparable_pairs = (
        (_normalized_text(latest_snapshot.get("snapshot_status")), _normalized_text(incoming.get("snapshot_status"))),
        (_normalized_text(latest_snapshot.get("summary")), _normalized_text(incoming.get("summary"))),
        (
            _normalized_text(latest_snapshot.get("recommended_action_type")),
            _normalized_text(incoming.get("recommended_action_type")),
        ),
        (_normalized_text(latest_snapshot.get("source_updated_at")), _normalized_text(incoming.get("source_updated_at"))),
    )
    if any(current != expected for current, expected in comparable_pairs):
        return False
    if round(float(latest_snapshot.get("priority_score") or 0), 2) != round(float(incoming.get("priority_score") or 0), 2):
        return False
    def _stable_signal_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stable_items: list[dict[str, Any]] = []
        for item in items:
            stable_items.append(
                {
                    "signal_key": _normalized_text(item.get("signal_key")),
                    "signal_type": _normalized_text(item.get("signal_type")),
                    "signal_source": _normalized_text(item.get("signal_source")),
                    "signal_status": _normalized_text(item.get("signal_status")),
                    "priority": _normalized_text(item.get("priority")),
                    "score": round(float(item.get("score") or 0), 2),
                    "summary": _normalized_text(item.get("summary")),
                    "payload": _json_loads(item.get("payload_json") or item.get("payload"), default={}),
                    "evidence": _json_loads(item.get("evidence_json") or item.get("evidence"), default=[]),
                    "source_ref_type": _normalized_text(item.get("source_ref_type")),
                    "source_ref_id": _normalized_text(item.get("source_ref_id")),
                    "source_updated_at": _normalized_text(item.get("source_updated_at")),
                }
            )
        return stable_items

    for column_name, value in (
        ("evidence_json", incoming.get("evidence")),
        ("risk_flags_json", incoming.get("risk_flags")),
        ("opportunity_flags_json", incoming.get("opportunity_flags")),
        ("suggested_action_candidates_json", incoming.get("suggested_action_candidates")),
        ("score_breakdown_json", incoming.get("score_breakdown")),
    ):
        current = _json_loads(latest_snapshot.get(column_name), default=[])
        if _json_dump(current) != _json_dump(value):
            return False
    current_signals = _json_loads(latest_snapshot.get("signals_json"), default=[])
    if _json_dump(_stable_signal_items(current_signals if isinstance(current_signals, list) else [])) != _json_dump(
        _stable_signal_items(incoming.get("signals") or [])
    ):
        return False
    return _json_dump(_stable_ai_payload(latest_snapshot.get("ai_payload_json"))) == _json_dump(
        _stable_ai_payload(incoming.get("ai_payload"))
    )


def _upsert_primary_card(
    *,
    context: dict[str, Any],
    scoring: dict[str, Any],
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not candidates:
        return None, "skipped"
    summary = context["summary"]
    marketing_state = context["marketing_state"]
    value_segment = context["value_segment"]
    ai_assist = context["ai_assist"]
    tenant_key = _resolved_tenant_key(
        tenant_context=context.get("tenant_context"),
        tenant_key=_normalized_text(context.get("tenant_key")),
    )
    scoped_card_key = customer_pulse_scoped_key(
        tenant_key=tenant_key,
        base_key=f"{_normalized_text(summary.get('external_userid'))}:primary",
    )
    existing = repo.get_customer_pulse_card_by_key(scoped_card_key, tenant_key=tenant_key) or {}
    primary_candidate = candidates[0]
    incoming_source_updated_at = _normalized_text(scoring.get("source_updated_at")) or _iso_now()
    existing_source_updated_at = _normalized_text(existing.get("source_updated_at"))

    next_status = "open"
    next_draft_message = ""
    if _normalized_text(primary_candidate.get("action_type")) == "generate_reply_draft":
        next_draft_message = _normalized_text(primary_candidate.get("payload", {}).get("draft_message")) or _normalized_text(
            ai_assist.get("draft_message")
        )
    next_snooze_until = ""
    next_resolved_at = ""
    next_resolution_note = ""
    if existing:
        existing_status = _normalized_text(existing.get("card_status"))
        if existing_status in _TERMINAL_CARD_STATUSES and incoming_source_updated_at and existing_source_updated_at >= incoming_source_updated_at:
            return repo.get_customer_pulse_card(int(existing.get("id") or 0), tenant_key=tenant_key) or existing, "skipped"
        if existing_status == "draft_ready" and existing_source_updated_at >= incoming_source_updated_at:
            next_status = "draft_ready"
            next_draft_message = _normalized_text(existing.get("draft_message")) or next_draft_message
        elif existing_status == "snoozed" and existing_source_updated_at >= incoming_source_updated_at:
            next_status = "snoozed"
            next_snooze_until = _normalized_text(existing.get("snooze_until"))
        elif existing_status in _TERMINAL_CARD_STATUSES and incoming_source_updated_at and existing_source_updated_at < incoming_source_updated_at:
            next_status = "open"

    card_payload = {
        "card_key": scoped_card_key,
        "tenant_key": tenant_key,
        "external_userid": _normalized_text(summary.get("external_userid")),
        "owner_userid": _normalized_text(summary.get("owner_userid")),
        "customer_name": _normalized_text(summary.get("customer_name")) or _normalized_text(summary.get("external_userid")),
        "mobile": _normalized_text(summary.get("mobile")),
        "owner_display_name": _normalized_text(summary.get("owner_display_name")) or _normalized_text(summary.get("owner_userid")),
        "marketing_main_stage": _normalized_text(marketing_state.get("main_stage")),
        "marketing_sub_stage": _normalized_text(marketing_state.get("sub_stage")),
        "value_segment": _normalized_text(value_segment.get("segment")).lower(),
        "snapshot_id": int(snapshot.get("id") or 0) or None,
        "card_status": next_status,
        "priority": _normalized_text(scoring.get("priority")),
        "priority_score": float(scoring.get("priority_score") or 0),
        "card_type": _normalized_text(primary_candidate.get("action_type")).replace("generate_", "").replace("set_", ""),
        "title": _card_title(primary_candidate),
        "summary": _card_summary(scoring, primary_candidate=primary_candidate),
        "suggested_action_type": _normalized_text(primary_candidate.get("action_type")),
        "suggested_action_payload": dict(primary_candidate.get("payload") or {}),
        "evidence": evidence,
        "risk_flags": scoring["risk_flags"],
        "opportunity_flags": scoring["opportunity_flags"],
        "suggested_action_candidates": candidates,
        "score_breakdown": scoring["score_breakdown"],
        "draft_message": next_draft_message,
        "need_human_confirmation": True,
        "due_at": _normalized_text(primary_candidate.get("payload", {}).get("due_at")) or incoming_source_updated_at,
        "snooze_until": next_snooze_until,
        "resolved_at": next_resolved_at,
        "resolution_note": next_resolution_note,
        "source_updated_at": incoming_source_updated_at,
    }

    unchanged = existing and all(
        [
            _normalized_text(existing.get("card_status")) == _normalized_text(card_payload["card_status"]),
            _normalized_text(existing.get("priority")) == _normalized_text(card_payload["priority"]),
            round(float(existing.get("priority_score") or 0), 2) == round(float(card_payload["priority_score"] or 0), 2),
            _normalized_text(existing.get("title")) == _normalized_text(card_payload["title"]),
            _normalized_text(existing.get("summary")) == _normalized_text(card_payload["summary"]),
            _normalized_text(existing.get("customer_name")) == _normalized_text(card_payload["customer_name"]),
            _normalized_text(existing.get("mobile")) == _normalized_text(card_payload["mobile"]),
            _normalized_text(existing.get("owner_display_name")) == _normalized_text(card_payload["owner_display_name"]),
            _normalized_text(existing.get("marketing_main_stage")) == _normalized_text(card_payload["marketing_main_stage"]),
            _normalized_text(existing.get("marketing_sub_stage")) == _normalized_text(card_payload["marketing_sub_stage"]),
            _normalized_text(existing.get("value_segment")) == _normalized_text(card_payload["value_segment"]),
            _normalized_text(existing.get("suggested_action_type")) == _normalized_text(card_payload["suggested_action_type"]),
            _normalized_text(existing.get("source_updated_at")) == _normalized_text(card_payload["source_updated_at"]),
            _json_dump(_json_loads(existing.get("risk_flags_json"), default=[])) == _json_dump(card_payload["risk_flags"]),
            _json_dump(_json_loads(existing.get("opportunity_flags_json"), default=[])) == _json_dump(card_payload["opportunity_flags"]),
            _json_dump(_json_loads(existing.get("suggested_action_candidates_json"), default=[]))
            == _json_dump(card_payload["suggested_action_candidates"]),
            _json_dump(_json_loads(existing.get("score_breakdown_json"), default=[])) == _json_dump(card_payload["score_breakdown"]),
            _json_dump(_json_loads(existing.get("evidence_json"), default=[])) == _json_dump(card_payload["evidence"]),
            _normalized_text(existing.get("draft_message")) == _normalized_text(card_payload["draft_message"]),
            _normalized_text(existing.get("due_at")) == _normalized_text(card_payload["due_at"]),
            _normalized_text(existing.get("snooze_until")) == _normalized_text(card_payload["snooze_until"]),
        ]
    )
    if unchanged:
        return repo.get_customer_pulse_card(int(existing.get("id") or 0), tenant_key=tenant_key) or existing, "skipped"
    card = repo.upsert_customer_pulse_card(**card_payload)
    return card, "updated" if existing else "created"


def _materialize_customer_pulse(
    external_userid: str,
    *,
    operator: str,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    context = _load_context(external_userid, tenant_context=resolved_context)
    summary = context["summary"]
    normalized_external_userid = _normalized_text(summary.get("external_userid") or external_userid)
    signals, metrics = _build_rule_signals(context)
    persisted_signals = _persist_signals(normalized_external_userid, signals=signals, tenant_key=resolved_tenant_key)
    scoring = _build_scoring(persisted_signals, metrics=metrics)
    candidates = _build_action_candidates(context, scoring=scoring, metrics=metrics)
    evidence = _dedupe_evidence(
        [
            evidence_item
            for signal in persisted_signals
            for evidence_item in _json_loads(signal.get("evidence_json"), default=[])
            if isinstance(evidence_item, dict)
        ],
        limit=6,
    )
    ai_recommendation = generate_customer_pulse_ai_recommendation(
        context=context,
        scoring=scoring,
        candidates=candidates,
        signals=persisted_signals,
    )
    candidates, card_evidence = _merge_ai_recommendation_into_candidates(
        candidates=candidates,
        recommendation_result=ai_recommendation,
        default_evidence=evidence,
    )
    candidates = _suppress_reply_draft_when_ai_is_untrusted(
        candidates=candidates,
        recommendation_result=ai_recommendation,
    )
    candidates = _apply_action_allowlist(candidates)
    primary_ai_recommendation = ai_recommendation.get("recommendation") if isinstance(ai_recommendation.get("recommendation"), dict) else {}
    ai_audit_labels = [_EXECUTION_AUDIT_AI_SUGGESTED] if _normalized_text(ai_recommendation.get("status")) == "accepted" else []
    ai_payload = {
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "assistant_draft_available": bool(context["ai_assist"].get("available")),
        "assistant_confidence": round(float(context["ai_assist"].get("confidence") or 0), 4),
        "assistant_reason": _normalized_text(context["ai_assist"].get("reason")),
        "assistant_output_type": _normalized_text(context["ai_assist"].get("output_type")),
        "assistant_output_id": _normalized_text(context["ai_assist"].get("output_id")),
        "recommendation_status": _normalized_text(ai_recommendation.get("status")) or "skipped",
        "provider": _normalized_text(ai_recommendation.get("provider")),
        "model_name": _normalized_text(ai_recommendation.get("model_name")),
        "run_id": _normalized_text(ai_recommendation.get("run_id")),
        "request_id": _normalized_text(ai_recommendation.get("request_id")),
        "output_id": _normalized_text(ai_recommendation.get("output_id")),
        "fallback_reason": _normalized_text(ai_recommendation.get("fallback_reason")),
        "error_message": _normalized_text(ai_recommendation.get("error_message")),
        "context_window": ai_recommendation.get("context_window") or {},
        "guardrails": ai_recommendation.get("guardrails") or {},
        "guardrail_summary": {
            "blocked": bool((ai_recommendation.get("guardrails") or {}).get("blocked")),
            "input_violations": list(((ai_recommendation.get("guardrails") or {}).get("input_violations") or [])),
            "output_violations": list(((ai_recommendation.get("guardrails") or {}).get("output_violations") or [])),
        },
        "trace": {
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "resource": _resource_summary(resource_type="customer", resource_id=normalized_external_userid),
            "actor": _actor_summary(tenant_context=resolved_context, operator=_normalized_text(operator)),
            "generated_at": _iso_now(),
        },
        "audit_labels": ai_audit_labels,
        "recommendation": primary_ai_recommendation,
        "last_interaction_at": _normalized_text(metrics.get("last_interaction_at")),
        "last_inbound_at": _normalized_text(metrics.get("last_inbound_at")),
        "last_outbound_at": _normalized_text(metrics.get("last_outbound_at")),
        "stage_stalled_days": metrics.get("stage_stalled_days"),
        "interaction_gap_days": metrics.get("interaction_gap_days"),
        "current_followup_segment": _normalized_text(metrics.get("current_followup_segment")),
    }
    repo.insert_customer_pulse_metric_event(
        event_type="ai_recommendation_completed",
        event_source="customer_pulse_snapshot_job",
        external_userid=normalized_external_userid,
        owner_userid=_normalized_text(summary.get("owner_userid")),
        action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
        tenant_key=resolved_tenant_key,
        operator=_normalized_text(operator),
        payload={
            "status": ai_payload["recommendation_status"],
            "fallback_reason": ai_payload["fallback_reason"],
            "provider": ai_payload["provider"],
            "model_name": ai_payload["model_name"],
            "request_id": ai_payload["request_id"],
            "output_id": ai_payload["output_id"],
            "guardrails": ai_payload["guardrail_summary"],
        },
    )
    if ai_payload["recommendation_status"] == "accepted":
        repo.insert_customer_pulse_metric_event(
            event_type="ai_success",
            event_source="customer_pulse_snapshot_job",
            external_userid=normalized_external_userid,
            owner_userid=_normalized_text(summary.get("owner_userid")),
            action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
            tenant_key=resolved_tenant_key,
            operator=_normalized_text(operator),
            payload={
                "provider": ai_payload["provider"],
                "model_name": ai_payload["model_name"],
                "request_id": ai_payload["request_id"],
                "output_id": ai_payload["output_id"],
            },
        )
    if ai_payload["recommendation_status"] == "fallback":
        repo.insert_customer_pulse_metric_event(
            event_type="fallback_count",
            event_source="customer_pulse_snapshot_job",
            external_userid=normalized_external_userid,
            owner_userid=_normalized_text(summary.get("owner_userid")),
            action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
            tenant_key=resolved_tenant_key,
            operator=_normalized_text(operator),
            payload={
                "fallback_reason": ai_payload["fallback_reason"],
                "provider": ai_payload["provider"],
                "model_name": ai_payload["model_name"],
            },
        )
    if ai_payload["recommendation_status"] == "fallback" and (
        _normalized_text(ai_payload["fallback_reason"]) or _normalized_text(ai_payload["error_message"])
    ):
        repo.insert_customer_pulse_metric_event(
            event_type="ai_error",
            event_source="customer_pulse_snapshot_job",
            external_userid=normalized_external_userid,
            owner_userid=_normalized_text(summary.get("owner_userid")),
            action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
            tenant_key=resolved_tenant_key,
            operator=_normalized_text(operator),
            payload={
                "fallback_reason": ai_payload["fallback_reason"],
                "error_message": ai_payload["error_message"],
                "provider": ai_payload["provider"],
            },
        )

    if not persisted_signals or not candidates or float(scoring.get("priority_score") or 0) < 20:
        return {
            "ok": True,
            "external_userid": normalized_external_userid,
            "customer_name": _normalized_text(summary.get("customer_name")) or normalized_external_userid,
            "processed": False,
            "reason": "no_actionable_candidate",
            "priority_score": float(scoring.get("priority_score") or 0),
            "risk_flags": scoring["risk_flags"],
            "opportunity_flags": scoring["opportunity_flags"],
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "generated_at": _iso_now(),
        }

    primary_candidate = candidates[0]
    snapshot_payload = {
        "tenant_key": resolved_tenant_key,
        "external_userid": normalized_external_userid,
        "owner_userid": _normalized_text(summary.get("owner_userid")),
        "snapshot_status": "visible",
        "confidence": scoring["confidence"],
        "priority_score": float(scoring.get("priority_score") or 0),
        "summary": _card_summary(scoring, primary_candidate=primary_candidate),
        "recommended_action_type": _normalized_text(primary_candidate.get("action_type")),
        "recommended_action_label": _action_label(primary_candidate.get("action_type")),
        "evidence": card_evidence,
        "ai_payload": ai_payload,
        "signals": persisted_signals,
        "risk_flags": scoring["risk_flags"],
        "opportunity_flags": scoring["opportunity_flags"],
        "suggested_action_candidates": candidates,
        "score_breakdown": scoring["score_breakdown"],
        "source_updated_at": _normalized_text(scoring.get("source_updated_at")),
        "created_by": _normalized_text(operator) or "system",
    }
    latest_snapshot = context["latest_snapshot"]
    if _snapshot_matches(latest_snapshot, incoming=snapshot_payload):
        snapshot = latest_snapshot
    else:
        snapshot = repo.create_customer_pulse_snapshot(**snapshot_payload)

    card, card_action = _upsert_primary_card(
        context=context,
        scoring=scoring,
        evidence=card_evidence,
        candidates=candidates,
        snapshot=snapshot,
    )
    return {
        "ok": True,
        "external_userid": normalized_external_userid,
        "customer_name": _normalized_text(summary.get("customer_name")) or normalized_external_userid,
        "processed": bool(card),
        "snapshot": snapshot,
        "card": _present_card(card, snapshot_row=snapshot, access_context=context.get("tenant_context")) if card else None,
        "priority_score": float(scoring.get("priority_score") or 0),
        "priority": _normalized_text(scoring.get("priority")),
        "risk_flags": scoring["risk_flags"],
        "opportunity_flags": scoring["opportunity_flags"],
        "suggested_action_candidates": candidates,
        "score_breakdown": scoring["score_breakdown"],
        "metrics": metrics,
        "action": card_action,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "generated_at": _iso_now(),
    }


def refresh_customer_pulse_cards(
    *,
    limit: int = 50,
    operator: str = "system",
    external_userids: list[str] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        return {
            "enabled": False,
            "feature_gate": feature_gate,
            "processed_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "cards": [],
        }
    candidate_external_userids = [
        _normalized_text(item)
        for item in (external_userids or repo.list_customer_pulse_candidate_external_userids(limit=limit))
        if _normalized_text(item)
    ]
    normalized_allowed_owner_userids = {
        _normalized_text(item)
        for item in (allowed_owner_userids or [])
        if _normalized_text(item)
    }
    if normalized_allowed_owner_userids:
        target_external_userids = [
            external_userid
            for external_userid in candidate_external_userids
            if _normalized_text(repo.get_customer_pulse_customer_summary(external_userid).get("owner_userid"))
            in normalized_allowed_owner_userids
        ]
    else:
        target_external_userids = candidate_external_userids
    processed_count = 0
    created_count = 0
    updated_count = 0
    skipped_count = 0
    refreshed_cards: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for external_userid in target_external_userids:
        result = _materialize_customer_pulse(
            external_userid,
            operator=operator,
            tenant_context=resolved_context,
        )
        items.append(result)
        if not result.get("processed"):
            skipped_count += 1
            continue
        processed_count += 1
        if result.get("action") == "created":
            created_count += 1
        elif result.get("action") == "updated":
            updated_count += 1
        else:
            skipped_count += 1
        if result.get("card"):
            refreshed_cards.append(result["card"])
    return {
        "enabled": True,
        "feature_gate": feature_gate,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "processed_count": processed_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "cards": refreshed_cards,
        "items": items,
        "generated_at": _iso_now(),
    }


def enqueue_customer_pulse_recompute(
    *,
    external_userid: str,
    owner_userid: str = "",
    delay_seconds: int = 0,
    operator: str = "",
    trigger_source: str = "",
    trigger_ref_type: str = "",
    trigger_ref_id: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return {"ok": True, "scheduled": False, "reason": "missing_external_userid"}
    if not feature_gate["enabled"]:
        return {"ok": True, "scheduled": False, "reason": "feature_disabled", "enabled": False, "feature_gate": feature_gate}
    now_dt = datetime.now()
    run_after = (now_dt + timedelta(seconds=max(int(delay_seconds or 0), 0))).strftime("%Y-%m-%d %H:%M:%S")
    resolved_owner = _normalized_text(owner_userid) or _normalized_text(
        repo.get_customer_pulse_customer_summary(normalized_external_userid).get("owner_userid")
    )
    payload = {
        "external_userid": normalized_external_userid,
        "owner_userid": resolved_owner,
        "trigger_source": _normalized_text(trigger_source),
        "trigger_ref_type": _normalized_text(trigger_ref_type),
        "trigger_ref_id": _normalized_text(trigger_ref_id),
        "scheduled_by": _normalized_text(operator) or "system",
        "scheduled_at": _iso_now(),
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
    }
    job = repo.upsert_customer_pulse_recompute_job(
        job_type=CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE,
        tenant_key=resolved_tenant_key,
        external_userid=normalized_external_userid,
        owner_userid=resolved_owner,
        run_after=run_after,
        payload=payload,
    )
    return {
        "ok": True,
        "enabled": True,
        "feature_gate": feature_gate,
        "scheduled": bool(job),
        "job": job,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
    }


def run_due_customer_pulse_recompute_jobs(
    *,
    limit: int = 20,
    operator: str = "system",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 20), 200))
    now = _iso_now()
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    due_jobs = repo.list_due_customer_pulse_recompute_jobs(
        job_type=CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE,
        due_at=now,
        tenant_key=resolved_tenant_key,
        owner_userids=allowed_owner_userids,
        limit=normalized_limit,
    )
    summary = {
        "ok": True,
        "limit": normalized_limit,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "scanned_count": len(due_jobs),
        "success_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "items": [],
    }
    for job in due_jobs:
        running_job = repo.mark_customer_pulse_recompute_job_running(int(job["id"]), tenant_key=resolved_tenant_key)
        if not running_job:
            continue
        try:
            result = _materialize_customer_pulse(
                _normalized_text(running_job.get("external_userid")),
                operator=operator,
                tenant_context=resolved_context,
            )
            status = "success" if result.get("processed") else "skipped"
        except Exception as exc:
            status = "failed"
            result = {
                "ok": False,
                "external_userid": _normalized_text(job.get("external_userid")),
                "error": str(exc),
            }
        repo.finish_customer_pulse_recompute_job(
            int(job["id"]),
            status=status,
            result_payload=result,
            tenant_key=resolved_tenant_key,
        )
        if status == "success":
            summary["success_count"] += 1
        elif status == "skipped":
            summary["skipped_count"] += 1
        else:
            summary["failed_count"] += 1
        summary["items"].append({"job_id": int(job["id"]), "status": status, **result})
    return summary


def run_due_customer_pulse_snapshot_job(
    *,
    limit: int = 20,
    rescan_limit: int = 20,
    operator: str = "system",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    queue_result = run_due_customer_pulse_recompute_jobs(
        limit=limit,
        operator=operator,
        tenant_context=resolved_context,
        allowed_owner_userids=allowed_owner_userids,
    )
    refresh_result = refresh_customer_pulse_cards(
        limit=max(1, min(int(rescan_limit or 0), 200)),
        operator=operator,
        tenant_context=resolved_context,
        allowed_owner_userids=allowed_owner_userids,
    )
    return {
        "ok": True,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "queue": queue_result,
        "refresh": refresh_result,
        "generated_at": _iso_now(),
    }


def _customer_pulse_access_permissions(access_context: Mapping[str, Any] | None) -> dict[str, Any]:
    return customer_pulse_permission_summary(access_context)


def _can_view_evidence(access_context: Mapping[str, Any] | None) -> bool:
    return bool(_customer_pulse_access_permissions(access_context).get("evidence_view"))


def _allowed_action_map(access_context: Mapping[str, Any] | None) -> dict[str, bool]:
    action_permissions = _customer_pulse_access_permissions(access_context).get("action_permissions")
    return dict(action_permissions or {}) if isinstance(action_permissions, dict) else {}


def _sanitize_evidence_ref_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceType": _normalized_text(item.get("sourceType")),
        "sourceId": _normalized_text(item.get("sourceId")),
        "title": customer_pulse_mask_pii(item.get("title"), max_length=48),
        "eventTime": _normalized_text(item.get("eventTime")),
    }


def _sanitize_evidence_text(value: Any, *, max_length: int = 120) -> str:
    return customer_pulse_mask_pii(value, max_length=max_length)


def _sanitize_evidence_refs(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = _sanitize_evidence_ref_item(item)
        if not sanitized["sourceType"] or not sanitized["sourceId"]:
            continue
        refs.append(sanitized)
    return refs


def _sanitize_ai_payload(ai_payload: Any, *, access_context: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _json_loads(ai_payload, default={})
    if not isinstance(payload, dict):
        return {}
    recommendation = dict(payload.get("recommendation") or {}) if isinstance(payload.get("recommendation"), dict) else {}
    if recommendation:
        recommendation["evidenceRefs"] = _sanitize_evidence_refs(recommendation.get("evidenceRefs") or [])
        payload["recommendation"] = recommendation
    if not _can_view_evidence(access_context):
        payload["evidence"] = []
    return payload


def _present_snapshot(snapshot_row: dict[str, Any], *, access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    can_view_evidence = _can_view_evidence(access_context)
    signals = _json_loads(snapshot_row.get("signals_json"), default=[])
    if not isinstance(signals, list):
        signals = []
    presented_signals = []
    for item in signals:
        if not isinstance(item, dict):
            continue
        signal_evidence = item.get("evidence") if can_view_evidence else []
        presented_signals.append(
            {
                **dict(item),
                "evidence": signal_evidence if isinstance(signal_evidence, list) else [],
            }
        )
    return {
        "id": int(snapshot_row.get("id") or 0),
        "tenant_key": _normalized_text(snapshot_row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "external_userid": _normalized_text(snapshot_row.get("external_userid")),
        "owner_userid": _normalized_text(snapshot_row.get("owner_userid")),
        "snapshot_status": _normalized_text(snapshot_row.get("snapshot_status")) or "ready",
        "confidence": float(snapshot_row.get("confidence") or 0) if snapshot_row.get("confidence") not in (None, "") else None,
        "priority_score": round(float(snapshot_row.get("priority_score") or 0), 2),
        "summary": _normalized_text(snapshot_row.get("summary")),
        "recommended_action_type": _normalized_text(snapshot_row.get("recommended_action_type")),
        "recommended_action_label": _normalized_text(snapshot_row.get("recommended_action_label"))
        or _action_label(snapshot_row.get("recommended_action_type")),
        "evidence": _json_loads(snapshot_row.get("evidence_json"), default=[]) if can_view_evidence else [],
        "ai_payload": _sanitize_ai_payload(snapshot_row.get("ai_payload_json"), access_context=access_context),
        "signals": presented_signals,
        "risk_flags": _json_loads(snapshot_row.get("risk_flags_json"), default=[]),
        "opportunity_flags": _json_loads(snapshot_row.get("opportunity_flags_json"), default=[]),
        "suggested_action_candidates": _json_loads(snapshot_row.get("suggested_action_candidates_json"), default=[]),
        "score_breakdown": _json_loads(snapshot_row.get("score_breakdown_json"), default=[]),
        "source_updated_at": _normalized_text(snapshot_row.get("source_updated_at")),
        "created_by": _normalized_text(snapshot_row.get("created_by")),
        "created_at": _normalized_text(snapshot_row.get("created_at")),
        "updated_at": _normalized_text(snapshot_row.get("updated_at")),
    }


def _present_signal(row: dict[str, Any], *, access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = _json_loads(row.get("payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "signal_key": _normalized_text(row.get("signal_key")),
        "tenant_key": _normalized_text(row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "signal_type": _normalized_text(row.get("signal_type")),
        "signal_source": _normalized_text(row.get("signal_source")),
        "signal_status": _normalized_text(row.get("signal_status")) or "open",
        "priority": _normalized_text(row.get("priority")) or "normal",
        "score": round(float(row.get("score") or 0), 2),
        "summary": _normalized_text(row.get("summary")),
        "payload": payload,
        "evidence": _json_loads(row.get("evidence_json"), default=[]) if _can_view_evidence(access_context) else [],
        "source_ref_type": _normalized_text(row.get("source_ref_type")),
        "source_ref_id": _normalized_text(row.get("source_ref_id")),
        "source_updated_at": _normalized_text(row.get("source_updated_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _card_evidence_refs(
    *,
    snapshot_payload: dict[str, Any] | None,
    ai_recommendation: dict[str, Any],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    raw_ai_refs = ai_recommendation.get("evidenceRefs") or []
    if isinstance(raw_ai_refs, list):
        for item in raw_ai_refs:
            if not isinstance(item, dict):
                continue
            source_type = _normalized_text(item.get("sourceType"))
            source_id = _normalized_text(item.get("sourceId"))
            if not source_type or not source_id:
                continue
            dedupe_key = (source_type, source_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            refs.append(
                {
                    "sourceType": source_type,
                    "sourceId": source_id,
                    "title": _normalized_text(item.get("title")),
                    "eventTime": _normalized_text(item.get("eventTime")),
                }
            )
    if refs:
        return _sanitize_evidence_refs(refs)

    for signal in (snapshot_payload or {}).get("signals") or []:
        if not isinstance(signal, dict):
            continue
        source_type = _normalized_text(signal.get("source_ref_type") or signal.get("signal_source"))
        source_id = _normalized_text(signal.get("source_ref_id"))
        if not source_type or not source_id:
            continue
        dedupe_key = (source_type, source_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidence = signal.get("evidence") or []
        first_evidence = evidence[0] if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict) else {}
        refs.append(
            {
                "sourceType": source_type,
                "sourceId": source_id,
                "title": _normalized_text(first_evidence.get("title")) or _normalized_text(signal.get("summary")),
                "eventTime": _normalized_text(first_evidence.get("event_time")) or _normalized_text(signal.get("source_updated_at")),
            }
        )
    return _sanitize_evidence_refs(refs)


def _present_card(
    row: dict[str, Any],
    *,
    snapshot_row: dict[str, Any] | None = None,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    suggested_action_payload = _json_loads(row.get("suggested_action_payload_json"), default={})
    if not isinstance(suggested_action_payload, dict):
        suggested_action_payload = {}
    snapshot = dict(snapshot_row or {})
    if not snapshot and row.get("snapshot_id"):
        snapshot = repo.get_customer_pulse_snapshot(
            int(row.get("snapshot_id") or 0),
            tenant_key=_normalized_text(row.get("tenant_key")),
        ) or {}
    snapshot_payload = _present_snapshot(snapshot, access_context=access_context) if snapshot else None
    permissions = _customer_pulse_access_permissions(access_context)
    action_permissions = _allowed_action_map(access_context)
    can_view_evidence = bool(permissions.get("evidence_view"))
    stage_label = _stage_label(row.get("marketing_main_stage"), row.get("marketing_sub_stage"))
    stage_key = "/".join(
        part
        for part in [_normalized_text(row.get("marketing_main_stage")), _normalized_text(row.get("marketing_sub_stage"))]
        if part
    )
    segment_label = _segment_label(row.get("value_segment"))
    status = _normalized_text(row.get("card_status")) or "open"
    evidence = _json_loads(row.get("evidence_json"), default=[]) if can_view_evidence else []
    if not isinstance(evidence, list):
        evidence = []
    suggested_action_candidates = _json_loads(row.get("suggested_action_candidates_json"), default=[])
    if not isinstance(suggested_action_candidates, list):
        suggested_action_candidates = []
    suggested_action_candidates = _apply_action_allowlist(suggested_action_candidates)
    permitted_candidates = [
        item
        for item in suggested_action_candidates
        if isinstance(item, dict) and action_permissions.get(_normalized_text(item.get("action_type")), False)
    ]
    suggested_action_type = _normalized_text(row.get("suggested_action_type"))
    if suggested_action_type and (
        not _action_allowed(suggested_action_type) or not action_permissions.get(suggested_action_type, False)
    ):
        suggested_action_type = _normalized_text((permitted_candidates[0] if permitted_candidates else {}).get("action_type"))
        replacement_payload = dict((permitted_candidates[0] if permitted_candidates else {}).get("payload") or {})
        if replacement_payload:
            suggested_action_payload = replacement_payload
    elif suggested_action_type and not permitted_candidates and not action_permissions.get(suggested_action_type, False):
        suggested_action_type = ""
    ai_recommendation = (
        dict(((snapshot_payload or {}).get("ai_payload") or {}).get("recommendation") or {})
        if isinstance((snapshot_payload or {}).get("ai_payload"), dict)
        else {}
    )
    evidence_refs = _card_evidence_refs(snapshot_payload=snapshot_payload, ai_recommendation=ai_recommendation)
    why_now = _normalized_text(ai_recommendation.get("whyNow"))
    if not why_now and permitted_candidates:
        primary_candidate = permitted_candidates[0] if isinstance(permitted_candidates[0], dict) else {}
        why_now = _normalized_text(primary_candidate.get("why_now") or primary_candidate.get("reason"))
    latest_event = next((item for item in evidence if isinstance(item, dict)), {})
    fallback_ref = evidence_refs[0] if evidence_refs else {}
    due_anchor = _normalized_text(row.get("snooze_until")) or _normalized_text(row.get("due_at"))
    due_moment = _parse_datetime(due_anchor)
    is_overdue = bool(due_moment and due_moment <= datetime.now() and status in _ACTIVE_CARD_STATUSES)
    current_judgement = _normalized_text(ai_recommendation.get("summary")) or _normalized_text(row.get("summary"))
    draft_blocked_by_ai = bool(suggested_action_payload.get("draft_blocked_by_ai"))
    supported_action_buttons = [
        {
            "action_type": _normalized_text(item.get("action_type")),
            "action_label": _normalized_text(item.get("action_label")) or _action_label(item.get("action_type")),
            "title": _normalized_text(item.get("title")),
            "candidate_score": round(float(item.get("candidate_score") or 0), 2),
        }
        for item in permitted_candidates
        if isinstance(item, dict) and _normalized_text(item.get("action_type"))
    ]
    feedback_actions = []
    if bool(permissions.get("submit_feedback")) and status == "snoozed":
        feedback_actions.append({"type": "reopen", "label": "重新打开"})
    elif bool(permissions.get("submit_feedback")) and status in _ACTIVE_CARD_STATUSES:
        feedback_actions.extend(
            [
                {"type": "complete", "label": "标记完成"},
                {"type": "snooze", "label": "明天提醒我"},
                {"type": "dismiss", "label": "暂不处理"},
            ]
        )
    if bool(permissions.get("submit_feedback")):
        feedback_actions.extend(
            [
                {"type": "misjudged", "label": "误判"},
                {"type": "unhelpful", "label": "无帮助"},
            ]
        )
    return {
        "id": int(row.get("id") or 0),
        "card_key": _normalized_text(row.get("card_key")),
        "tenant_key": _normalized_text(row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "external_userid": _normalized_text(row.get("external_userid")),
        "customer_name": _normalized_text(row.get("customer_name")) or _normalized_text(row.get("external_userid")),
        "owner_userid": _normalized_text(row.get("owner_userid")),
        "owner_display_name": _normalized_text(row.get("owner_display_name")) or _normalized_text(row.get("owner_userid")),
        "mobile": _normalized_text(row.get("mobile")),
        "card_status": status,
        "card_status_label": _card_status_label(status),
        "priority": _normalized_text(row.get("priority")) or "normal",
        "priority_label": _priority_label(row.get("priority")),
        "priority_score": round(float(row.get("priority_score") or 0), 2),
        "card_type": _normalized_text(row.get("card_type")) or "followup",
        "title": _normalized_text(row.get("title")) or "客户推进行动卡",
        "summary": _normalized_text(row.get("summary")),
        "current_judgement": current_judgement,
        "why_now": why_now,
        "suggested_action_type": suggested_action_type,
        "suggested_action_label": _action_label(suggested_action_type) if suggested_action_type else "当前无可执行动作",
        "suggested_action_payload": suggested_action_payload if suggested_action_type else {},
        "suggested_action_candidates": permitted_candidates,
        "supported_action_buttons": supported_action_buttons,
        "score_breakdown": _json_loads(row.get("score_breakdown_json"), default=[]),
        "risk_flags": _json_loads(row.get("risk_flags_json"), default=[]),
        "opportunity_flags": _json_loads(row.get("opportunity_flags_json"), default=[]),
        "evidence": evidence,
        "evidence_refs": evidence_refs,
        "evidenceRefs": evidence_refs,
        "latest_event": {
            "title": _normalized_text(latest_event.get("title")) or _normalized_text(fallback_ref.get("title")) or "最近事件",
            "detail": _normalized_text(latest_event.get("detail"))
            or (_normalized_text(fallback_ref.get("title")) if _normalized_text(fallback_ref.get("title")) else "暂无详情"),
            "event_time": _normalized_text(latest_event.get("event_time")) or _normalized_text(fallback_ref.get("eventTime")),
            "source": _normalized_text(latest_event.get("source")) or _normalized_text(fallback_ref.get("sourceType")),
        },
        "draft_message": _normalized_text(row.get("draft_message")),
        "draft_blocked_by_ai": draft_blocked_by_ai,
        "draft_notice": _normalized_text(suggested_action_payload.get("draft_notice")) or "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "draft_editor_available": bool(action_permissions.get("generate_reply_draft"))
        and (
            suggested_action_type == "generate_reply_draft"
            or any(item.get("action_type") == "generate_reply_draft" for item in supported_action_buttons)
        ),
        "need_human_confirmation": bool(row.get("need_human_confirmation")),
        "confidence": float(snapshot.get("confidence") or 0) if snapshot and snapshot.get("confidence") not in (None, "") else None,
        "stage_label": stage_label,
        "stage_key": stage_key,
        "segment_label": segment_label,
        "due_at": _normalized_text(row.get("due_at")),
        "snooze_until": _normalized_text(row.get("snooze_until")),
        "is_overdue": is_overdue,
        "resolved_at": _normalized_text(row.get("resolved_at")),
        "resolution_note": _normalized_text(row.get("resolution_note")),
        "source_updated_at": _normalized_text(row.get("source_updated_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
        "feedback_actions": feedback_actions,
        "review_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "permissions": permissions,
        "action_disabled_by_config": not bool(suggested_action_type),
        "action_disabled_by_permission": not bool(permissions.get("can_execute_any")),
        "evidence_expand_available": bool(can_view_evidence and evidence_refs),
        "snapshot": snapshot_payload,
    }


def _resolve_card_action_candidate(
    card: dict[str, Any],
    *,
    action_type: str = "",
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    resolved_action_type = _normalized_text(action_type) or _normalized_text(card.get("suggested_action_type"))
    if not resolved_action_type:
        raise ValueError("unsupported action_type")
    primary_candidate = {
        "action_type": _normalized_text(card.get("suggested_action_type")),
        "payload": dict(card.get("suggested_action_payload") or {}),
        "title": _normalized_text(card.get("title")),
        "why_now": _normalized_text(card.get("why_now")),
    }
    if resolved_action_type == primary_candidate["action_type"]:
        return resolved_action_type, dict(primary_candidate.get("payload") or {}), primary_candidate
    for item in card.get("suggested_action_candidates") or []:
        if not isinstance(item, dict):
            continue
        if _normalized_text(item.get("action_type")) != resolved_action_type:
            continue
        return resolved_action_type, dict(item.get("payload") or {}), item
    raise ValueError("unsupported action_type")


def _searchable_card_text(card: dict[str, Any]) -> str:
    parts = [
        card.get("customer_name"),
        card.get("external_userid"),
        card.get("owner_display_name"),
        card.get("owner_userid"),
        card.get("mobile"),
        card.get("title"),
        card.get("summary"),
        card.get("current_judgement"),
        card.get("why_now"),
        card.get("stage_label"),
        card.get("segment_label"),
        (card.get("latest_event") or {}).get("detail"),
        (card.get("latest_event") or {}).get("title"),
    ]
    for item in card.get("risk_flags") or []:
        if isinstance(item, dict):
            parts.extend([item.get("key"), item.get("label")])
    for item in card.get("opportunity_flags") or []:
        if isinstance(item, dict):
            parts.extend([item.get("key"), item.get("label")])
    return " ".join(_normalized_text(part).lower() for part in parts if _normalized_text(part))


def _filter_match(card: dict[str, Any], *, filters: dict[str, Any]) -> bool:
    scope = _normalized_text(filters.get("scope")) or "all"
    stage = _normalized_text(filters.get("stage"))
    risk = _normalized_text(filters.get("risk"))
    search = _normalized_text(filters.get("search")).lower()
    resolved_owner_userid = _normalized_text(filters.get("resolved_owner_userid"))
    if scope == "mine" and resolved_owner_userid and _normalized_text(card.get("owner_userid")) != resolved_owner_userid:
        return False
    if stage and _normalized_text(card.get("stage_key")) != stage:
        return False
    if risk and not any(_normalized_text(item.get("key")) == risk for item in (card.get("risk_flags") or []) if isinstance(item, dict)):
        return False
    if filters.get("overdue_only") and not bool(card.get("is_overdue")):
        return False
    if filters.get("draft_only") and not (bool(_normalized_text(card.get("draft_message"))) or _normalized_text(card.get("card_status")) == "draft_ready"):
        return False
    if filters.get("high_priority_only") and _normalized_text(card.get("priority")) != "high":
        return False
    if search and search not in _searchable_card_text(card):
        return False
    return True


def _build_inbox_filter_options(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    stage_options: list[dict[str, str]] = []
    seen_stage_keys: set[str] = set()
    risk_options: list[dict[str, str]] = []
    seen_risk_keys: set[str] = set()
    for card in cards:
        stage_key = _normalized_text(card.get("stage_key"))
        if stage_key and stage_key not in seen_stage_keys:
            seen_stage_keys.add(stage_key)
            stage_options.append({"value": stage_key, "label": _normalized_text(card.get("stage_label")) or stage_key})
        for item in card.get("risk_flags") or []:
            if not isinstance(item, dict):
                continue
            risk_key = _normalized_text(item.get("key"))
            if not risk_key or risk_key in seen_risk_keys:
                continue
            seen_risk_keys.add(risk_key)
            risk_options.append({"value": risk_key, "label": _normalized_text(item.get("label")) or risk_key})
    return {
        "stages": sorted(stage_options, key=lambda item: item["label"]),
        "risks": sorted(risk_options, key=lambda item: item["label"]),
    }


def build_customer_pulse_inbox_payload(
    *,
    limit: int = 50,
    owner_userid: str = "",
    external_userid: str = "",
    operator: str = "",
    scope: str = "all",
    stage: str = "",
    risk: str = "",
    overdue_only: bool = False,
    draft_only: bool = False,
    high_priority_only: bool = False,
    search: str = "",
    track_metrics: bool = False,
    metric_source: str = "",
    include_ops_dashboard: bool = False,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
            "feature_gate": feature_gate,
            "rules_version": CUSTOMER_PULSE_RULES_VERSION,
            "runtime_config": {
                "high_priority_threshold": _high_priority_threshold(),
                "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
                "allowed_action_types": sorted(_allowed_action_types()),
            },
            "permissions": _customer_pulse_access_permissions(resolved_context),
            "cards": [],
            "filter_options": {"stages": [], "risks": []},
            "filters": {
                "scope": _normalized_text(scope) or "all",
                "stage": _normalized_text(stage),
                "risk": _normalized_text(risk),
                "overdue_only": bool(overdue_only),
                "draft_only": bool(draft_only),
                "high_priority_only": bool(high_priority_only),
                "search": _normalized_text(search),
                "requested_owner_userid": _normalized_text(owner_userid),
                "resolved_owner_userid": _normalized_text(owner_userid) or _normalized_text(operator),
                "external_userid": _normalized_text(external_userid),
                "operator": _normalized_text(operator),
                "scope_fallback_notice": "",
            },
            "visible_count": 0,
            "matched_count": 0,
            "total_active_count": 0,
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "metrics_summary": _customer_pulse_metrics_summary(
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                owner_userids=allowed_owner_userids,
            ),
            "ops_dashboard": (
                build_customer_pulse_ops_dashboard_payload(
                    tenant_context=resolved_context,
                    tenant_key=resolved_tenant_key,
                    owner_userids=allowed_owner_userids,
                )
                if include_ops_dashboard
                else None
            ),
            "counts": {"open": 0, "draft_ready": 0, "snoozed": 0, "completed": 0, "dismissed": 0},
            "summary_cards": [],
            "channel_notice": "当前租户或角色未进入 Customer Pulse 灰度范围，不展示收件箱数据。",
            "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
            "generated_at": _iso_now(),
        }
    counts = repo.count_customer_pulse_cards_by_status(
        tenant_key=resolved_tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )
    effective_scope = _normalized_text(scope) or "all"
    requested_owner_userid = _normalized_text(owner_userid)
    resolved_owner_userid = requested_owner_userid or _normalized_text(operator)
    scope_fallback_notice = ""
    if effective_scope == "mine" and not resolved_owner_userid:
        effective_scope = "all"
        scope_fallback_notice = "当前后台未注入登录人，`我的客户` 已回退为 `全部客户`。如需锁定负责人，可通过 operator 或 owner_userid 传入。"
    card_rows = repo.list_customer_pulse_cards(
        limit=max(1, min(int(limit or 0), 200)),
        tenant_key=resolved_tenant_key,
        owner_userid=requested_owner_userid,
        external_userid=external_userid,
        allowed_owner_userids=allowed_owner_userids,
    )
    snapshot_rows_by_id = repo.list_customer_pulse_snapshots_by_ids(
        [int(row.get("snapshot_id") or 0) for row in card_rows],
        tenant_key=resolved_tenant_key,
    )
    base_cards = [
        _present_card(
            row,
            snapshot_row=snapshot_rows_by_id.get(int(row.get("snapshot_id") or 0)),
            access_context=resolved_context,
        )
        for row in card_rows
    ]
    base_cards = [card for card in base_cards if not _card_hidden_by_low_confidence(card)]
    filters = {
        "scope": effective_scope,
        "stage": _normalized_text(stage),
        "risk": _normalized_text(risk),
        "overdue_only": bool(overdue_only),
        "draft_only": bool(draft_only),
        "high_priority_only": bool(high_priority_only),
        "search": _normalized_text(search),
        "requested_owner_userid": requested_owner_userid,
        "resolved_owner_userid": resolved_owner_userid,
        "external_userid": _normalized_text(external_userid),
        "operator": _normalized_text(operator),
        "scope_fallback_notice": scope_fallback_notice,
    }
    filtered_cards = [card for card in base_cards if _filter_match(card, filters=filters)]
    cards = filtered_cards[: max(1, min(int(limit or 0), 200))]
    if track_metrics:
        repo.insert_customer_pulse_metric_events_batch(
            tenant_key=resolved_tenant_key,
            events=[
                {
                    "card_id": int(card.get("id") or 0),
                    "external_userid": _normalized_text(card.get("external_userid")),
                    "owner_userid": _normalized_text(card.get("owner_userid")),
                    "action_type": _normalized_text(card.get("suggested_action_type")),
                    "event_type": "card_exposed",
                    "event_source": _normalized_text(metric_source) or "customer_pulse_inbox",
                    "operator": _normalized_text(operator),
                    "payload": {"surface": "inbox"},
                }
                for card in cards
                if int(card.get("id") or 0) > 0
            ],
        )
    filter_options = _build_inbox_filter_options(base_cards)
    high_priority_count = len([card for card in filtered_cards if _normalized_text(card.get("priority")) == "high"])
    draft_ready_count = len(
        [card for card in filtered_cards if bool(_normalized_text(card.get("draft_message"))) or _normalized_text(card.get("card_status")) == "draft_ready"]
    )
    overdue_count = len([card for card in filtered_cards if bool(card.get("is_overdue"))])
    return {
        "enabled": True,
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "feature_gate": feature_gate,
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "runtime_config": {
            "high_priority_threshold": _high_priority_threshold(),
            "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
            "allowed_action_types": sorted(_allowed_action_types()),
        },
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "cards": cards,
        "filter_options": filter_options,
        "filters": filters,
        "visible_count": len(cards),
        "matched_count": len(filtered_cards),
        "total_active_count": len(base_cards),
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "metrics_summary": _customer_pulse_metrics_summary(
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            owner_userids=allowed_owner_userids,
        ),
        "ops_dashboard": (
            build_customer_pulse_ops_dashboard_payload(
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                owner_userids=allowed_owner_userids,
            )
            if include_ops_dashboard
            else None
        ),
        "counts": {
            "open": int(counts.get("open", 0) or 0),
            "draft_ready": int(counts.get("draft_ready", 0) or 0),
            "snoozed": int(counts.get("snoozed", 0) or 0),
            "completed": int(counts.get("completed", 0) or 0),
            "dismissed": int(counts.get("dismissed", 0) or 0),
        },
        "summary_cards": [
            {
                "key": "visible",
                "label": "当前可见卡片",
                "value": len(cards),
                "description": f"当前筛选命中的行动卡，共 {len(filtered_cards)} 条",
            },
            {
                "key": "high_priority",
                "label": "高优先级",
                "value": high_priority_count,
                "description": "priority_score 或风险命中高优先级阈值",
            },
            {
                "key": "draft_ready",
                "label": "已有草稿",
                "value": draft_ready_count,
                "description": "已生成或已保存草稿，等待人工确认",
            },
            {
                "key": "overdue",
                "label": "超期未跟进",
                "value": overdue_count,
                "description": "下次处理时间已过，仍处于待处理状态",
            },
        ],
        "channel_notice": "若仓库中没有企微新链路，当前只复用已有客户沟通通道；不会临时接入新平台。",
        "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "generated_at": _iso_now(),
    }


def get_customer_pulse_card_payload(
    card_id: int,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        raise ValueError("当前租户或角色未启用 AI推进")
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    snapshot = (
        repo.get_customer_pulse_snapshot(int(card.get("snapshot_id") or 0), tenant_key=resolved_tenant_key)
        if card.get("snapshot_id")
        else {}
    )
    return {
        "enabled": True,
        "feature_gate": feature_gate,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "card": _present_card(card, snapshot_row=snapshot, access_context=resolved_context),
        "snapshot": _present_snapshot(snapshot, access_context=resolved_context) if snapshot else None,
        "latest_execution": _present_execution_log(
            repo.get_latest_customer_pulse_execution_log(int(card.get("id") or 0), tenant_key=resolved_tenant_key)
        ),
        "recent_action_feedback": [
            {
                "id": int(row.get("id") or 0),
                "execution_log_id": int(row.get("execution_log_id") or 0) if row.get("execution_log_id") not in (None, "") else 0,
                "action_type": _normalized_text(row.get("action_type")),
                "feedback_type": _normalized_text(row.get("feedback_type")),
                "feedback_source": _normalized_text(row.get("feedback_source")),
                "operator": _normalized_text(row.get("operator")),
                "note": _normalized_text(row.get("note")),
                "payload": _json_loads(row.get("payload_json"), default={}),
                "created_at": _normalized_text(row.get("created_at")),
            }
            for row in repo.list_customer_pulse_action_feedback(
                card_id=int(card.get("id") or 0),
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
        "metrics_summary": _customer_pulse_metrics_summary(
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        ),
        "recent_activities": [
            {
                "id": int(row.get("id") or 0),
                "activity_type": _normalized_text(row.get("activity_type")),
                "activity_status": _normalized_text(row.get("activity_status")),
                "title": _normalized_text(row.get("title")),
                "summary": _normalized_text(row.get("summary")),
                "due_at": _normalized_text(row.get("due_at")),
                "operator": _normalized_text(row.get("operator")),
                "created_at": _normalized_text(row.get("created_at")),
                "undone_at": _normalized_text(row.get("undone_at")),
                "payload": _json_loads(row.get("payload_json"), default={}),
            }
            for row in repo.list_customer_pulse_activity_logs(
                _normalized_text(card.get("external_userid")),
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
    }


def _customer_pulse_evidence_source_allowed(
    *,
    source_type: str,
    source_id: str,
    external_userid: str,
    owner_userid: str,
) -> bool:
    normalized_source_type = _normalized_text(source_type)
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    normalized_owner_userid = _normalized_text(owner_userid)
    if not normalized_source_type or not normalized_source_id or not normalized_external_userid:
        return False
    if normalized_source_type == "archived_messages":
        row = repo.get_archived_message_ref_row(normalized_source_id, external_userid=normalized_external_userid) or {}
        return bool(row) and (
            not _normalized_text(row.get("owner_userid")) or _normalized_text(row.get("owner_userid")) == normalized_owner_userid
        )
    if normalized_source_type == "automation_reply_monitor_queue":
        row = repo.get_reply_monitor_row_by_id(normalized_source_id, external_userid=normalized_external_userid) or {}
        return bool(row) and (
            not _normalized_text(row.get("owner_userid")) or _normalized_text(row.get("owner_userid")) == normalized_owner_userid
        )
    if normalized_source_type in {"questionnaire_submissions", "questionnaire_scrm_apply_logs"}:
        return bool(repo.get_questionnaire_submission_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    if normalized_source_type == "conversion_dispatch_log":
        return bool(repo.get_conversion_dispatch_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    if normalized_source_type == "customer_marketing_state_current":
        return bool(repo.get_customer_marketing_state_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    if normalized_source_type == "external_contact_bindings":
        return bool(repo.get_external_contact_binding_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    return False


def get_customer_pulse_card_evidence_payload(
    card_id: int,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        raise ValueError("当前租户或角色未启用 AI推进")
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    assert_customer_pulse_evidence_view(resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    snapshot = (
        repo.get_customer_pulse_snapshot(int(card.get("snapshot_id") or 0), tenant_key=resolved_tenant_key)
        if card.get("snapshot_id")
        else {}
    )
    presented_card = _present_card(card, snapshot_row=snapshot, access_context=resolved_context)
    evidence_refs = list(presented_card.get("evidence_refs") or [])
    ref_keys = {
        (_normalized_text(item.get("sourceType")), _normalized_text(item.get("sourceId")))
        for item in evidence_refs
        if _normalized_text(item.get("sourceType")) and _normalized_text(item.get("sourceId"))
    }
    evidence_items: list[dict[str, Any]] = []
    inaccessible_refs: list[dict[str, Any]] = []
    seen_item_keys: set[tuple[str, str, str, str]] = set()
    signals = repo.list_customer_pulse_signal_events(
        _normalized_text(card.get("external_userid")),
        tenant_key=resolved_tenant_key,
        statuses=("open", "resolved"),
        limit=50,
    )
    for signal_row in signals:
        presented_signal = _present_signal(signal_row, access_context=resolved_context)
        source_type = _normalized_text(presented_signal.get("source_ref_type") or presented_signal.get("signal_source"))
        source_id = _normalized_text(presented_signal.get("source_ref_id"))
        ref_key = (source_type, source_id)
        if ref_key not in ref_keys:
            continue
        if not _customer_pulse_evidence_source_allowed(
            source_type=source_type,
            source_id=source_id,
            external_userid=_normalized_text(card.get("external_userid")),
            owner_userid=_normalized_text(card.get("owner_userid")),
        ):
            inaccessible_refs.append({"sourceType": source_type, "sourceId": source_id})
            continue
        signal_evidence = presented_signal.get("evidence") if isinstance(presented_signal.get("evidence"), list) else []
        candidate_items = signal_evidence or [
            {
                "title": _normalized_text(presented_signal.get("summary")) or "证据",
                "detail": _normalized_text(presented_signal.get("summary")) or "暂无详情",
                "event_time": _normalized_text(presented_signal.get("source_updated_at")),
                "source": source_type,
            }
        ]
        for item in candidate_items:
            if not isinstance(item, dict):
                continue
            dedupe_key = (
                source_type,
                source_id,
                _normalized_text(item.get("title")),
                _normalized_text(item.get("event_time") or item.get("detail")),
            )
            if dedupe_key in seen_item_keys:
                continue
            seen_item_keys.add(dedupe_key)
            evidence_items.append(
                {
                    "sourceType": source_type,
                    "sourceId": source_id,
                    "title": _sanitize_evidence_text(item.get("title"), max_length=48) or "证据",
                    "detail": _sanitize_evidence_text(
                        item.get("detail") or presented_signal.get("summary"),
                        max_length=160,
                    )
                    or "暂无详情",
                    "event_time": _normalized_text(item.get("event_time")) or _normalized_text(presented_signal.get("source_updated_at")),
                    "source": _normalized_text(item.get("source")) or source_type,
                }
            )
    return {
        "enabled": True,
        "feature_gate": feature_gate,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "card_id": int(card_id),
        "external_userid": _normalized_text(card.get("external_userid")),
        "evidence_refs": evidence_refs,
        "evidence": evidence_items[: max(1, min(int(limit or 0), 100))],
        "inaccessible_refs": inaccessible_refs,
    }


def build_customer_pulse_customer_detail_payload(
    external_userid: str,
    *,
    track_metrics: bool = False,
    metric_source: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not feature_gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
            "feature_gate": feature_gate,
            "rules_version": CUSTOMER_PULSE_RULES_VERSION,
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "runtime_config": {
                "high_priority_threshold": _high_priority_threshold(),
                "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
                "allowed_action_types": sorted(_allowed_action_types()),
            },
            "permissions": _customer_pulse_access_permissions(resolved_context),
            "customer": {
                "external_userid": normalized_external_userid,
                "customer_name": normalized_external_userid,
                "owner_userid": "",
                "mobile": "",
            },
            "card": None,
            "has_card": False,
            "latest_snapshot": None,
            "signals": [],
            "recent_messages": [],
            "metrics_summary": _customer_pulse_metrics_summary(
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                owner_userids=allowed_owner_userids,
            ),
        }
    latest_snapshot = repo.get_latest_customer_pulse_snapshot_for_external_userid(
        normalized_external_userid,
        tenant_key=resolved_tenant_key,
    ) or {}
    card = repo.get_latest_customer_pulse_card_for_external_userid(
        normalized_external_userid,
        tenant_key=resolved_tenant_key,
    ) or {}
    owner_anchor_userid = _normalized_text(card.get("owner_userid") or latest_snapshot.get("owner_userid"))
    if allowed_owner_userids:
        normalized_allowed_owner_userids = {
            _normalized_text(item) for item in allowed_owner_userids if _normalized_text(item)
        }
        if owner_anchor_userid and owner_anchor_userid not in normalized_allowed_owner_userids:
            raise LookupError("customer not found")
    signals = repo.list_customer_pulse_signal_events(
        normalized_external_userid,
        tenant_key=resolved_tenant_key,
        statuses=("open", "resolved"),
        limit=20,
    )
    presented_card = (
        _present_card(
            repo.get_customer_pulse_card(int(card.get("id") or 0), tenant_key=resolved_tenant_key) or card,
            snapshot_row=latest_snapshot,
            access_context=resolved_context,
        )
        if card
        else None
    )
    if presented_card and _card_hidden_by_low_confidence(presented_card):
        presented_card = None
    if presented_card and track_metrics:
        _record_metric_event(
            event_type="card_exposed",
            event_source=_normalized_text(metric_source) or "customer_pulse_customer_detail",
            card=presented_card,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"surface": "customer_detail"},
        )
    summary = (
        repo.get_customer_pulse_customer_summary(normalized_external_userid)
        if bool(resolved_context.get("legacy_mode")) and not presented_card
        else {}
    )
    recent_messages = (
        repo.list_recent_archived_message_rows(normalized_external_userid, limit=5)
        if bool(resolved_context.get("legacy_mode"))
        else []
    )
    return {
        "enabled": True,
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "feature_gate": feature_gate,
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "runtime_config": {
            "high_priority_threshold": _high_priority_threshold(),
            "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
            "allowed_action_types": sorted(_allowed_action_types()),
        },
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "customer": {
            "external_userid": normalized_external_userid,
            "customer_name": _normalized_text((presented_card or {}).get("customer_name")) or _normalized_text(summary.get("customer_name")) or normalized_external_userid,
            "owner_userid": _normalized_text((presented_card or {}).get("owner_userid")) or owner_anchor_userid,
            "mobile": _normalized_text((presented_card or {}).get("mobile")) or _normalized_text(summary.get("mobile")),
        },
        "card": presented_card,
        "has_card": bool(presented_card),
        "latest_snapshot": _present_snapshot(latest_snapshot, access_context=resolved_context) if latest_snapshot else None,
        "signals": [_present_signal(row, access_context=resolved_context) for row in signals],
        "recent_messages": [
            {
                "id": int(row.get("id") or 0),
                "sender": _normalized_text(row.get("sender")),
                "content": _normalized_text(row.get("content")),
                "send_time": _normalized_text(row.get("send_time")),
                "direction": _message_direction(row, external_userid=normalized_external_userid),
            }
            for row in recent_messages
        ],
        "recent_activities": [
            {
                "id": int(row.get("id") or 0),
                "activity_type": _normalized_text(row.get("activity_type")),
                "activity_status": _normalized_text(row.get("activity_status")),
                "title": _normalized_text(row.get("title")),
                "summary": _normalized_text(row.get("summary")),
                "due_at": _normalized_text(row.get("due_at")),
                "operator": _normalized_text(row.get("operator")),
                "created_at": _normalized_text(row.get("created_at")),
                "undone_at": _normalized_text(row.get("undone_at")),
                "payload": _json_loads(row.get("payload_json"), default={}),
            }
            for row in repo.list_customer_pulse_activity_logs(
                normalized_external_userid,
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
        "latest_execution": _present_execution_log(
            repo.get_latest_customer_pulse_execution_log(int(card.get("id") or 0), tenant_key=resolved_tenant_key)
        )
        if card
        else None,
        "recent_action_feedback": [
            {
                "id": int(row.get("id") or 0),
                "execution_log_id": int(row.get("execution_log_id") or 0) if row.get("execution_log_id") not in (None, "") else 0,
                "action_type": _normalized_text(row.get("action_type")),
                "feedback_type": _normalized_text(row.get("feedback_type")),
                "feedback_source": _normalized_text(row.get("feedback_source")),
                "operator": _normalized_text(row.get("operator")),
                "note": _normalized_text(row.get("note")),
                "payload": _json_loads(row.get("payload_json"), default={}),
                "created_at": _normalized_text(row.get("created_at")),
            }
            for row in repo.list_customer_pulse_action_feedback(
                external_userid=normalized_external_userid,
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
        "generated_at": _iso_now(),
    }


def _reply_draft_task_payload(card: dict[str, Any], draft_message: str, execution_key: str) -> dict[str, Any]:
    return {
        "chat_type": "single",
        "external_userid": [_normalized_text(card.get("external_userid"))],
        "sender": [_normalized_text(card.get("owner_userid"))],
        "text": {"content": draft_message},
        "draft_only": True,
        "need_human_confirmation": True,
        "source": CUSTOMER_PULSE_FLAG_KEY,
        "source_card_id": int(card.get("id") or 0),
        "source_execution_key": execution_key,
    }


def _build_execution_response(
    *,
    card_id: int,
    action_type: str,
    result_payload: dict[str, Any],
    execution_log: dict[str, Any] | None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    latest_card = repo.get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key)
    return {
        "ok": True,
        "action_type": _normalized_text(action_type),
        "action_label": _action_label(action_type),
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "card": _present_card(latest_card or {}, access_context=resolved_context),
        "result": result_payload,
        "execution": _present_execution_log(execution_log),
    }


def _existing_execution_response(
    existing_log: dict[str, Any],
    *,
    card_id: int,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    result_payload = _json_loads(existing_log.get("result_payload_json"), default={})
    if not isinstance(result_payload, dict):
        result_payload = {}
    result_payload["deduplicated"] = True
    return _build_execution_response(
        card_id=card_id,
        action_type=_normalized_text(existing_log.get("action_type")),
        result_payload=result_payload,
        execution_log=existing_log,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def preview_customer_pulse_card_action(
    card_id: int,
    *,
    action_type: str = "",
    track_click: bool = False,
    metric_source: str = "",
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    requested_action_type = _normalized_text(action_type)
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    presented = _present_card(card, access_context=resolved_context)
    if requested_action_type and not _action_allowed(requested_action_type):
        raise ValueError("当前动作已被系统配置禁用")
    if requested_action_type and customer_pulse_action_permission(requested_action_type):
        assert_customer_pulse_action_permission(requested_action_type, access_context=resolved_context)
    resolved_action_type, action_payload, candidate = _resolve_card_action_candidate(presented, action_type=requested_action_type)
    assert_customer_pulse_action_permission(resolved_action_type, access_context=resolved_context)
    if track_click:
        _record_metric_event(
            event_type="card_clicked",
            event_source=_normalized_text(metric_source) or "customer_pulse_preview",
            card=presented,
            action_type=resolved_action_type,
            operator=_normalized_text(operator),
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"surface": "action_preview"},
        )
    if resolved_action_type == "generate_reply_draft":
        _record_metric_event(
            event_type="draft_preview_started",
            event_source=_normalized_text(metric_source) or "customer_pulse_preview",
            card=presented,
            action_type=resolved_action_type,
            operator=_normalized_text(operator),
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"surface": "action_preview"},
        )
    preview_result = {
        "card_id": presented["id"],
        "external_userid": presented["external_userid"],
        "customer_name": presented["customer_name"],
        "action_type": resolved_action_type,
        "action_label": _action_label(resolved_action_type),
        "action_title": _normalized_text(candidate.get("title")) or _action_label(resolved_action_type),
        "why_now": _normalized_text(candidate.get("why_now") or candidate.get("reason")) or _normalized_text(presented.get("why_now")),
        "need_human_confirmation": True,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "undo_supported": _action_requires_undo_window(resolved_action_type),
        "undo_window_minutes": CUSTOMER_PULSE_UNDO_WINDOW_MINUTES if _action_requires_undo_window(resolved_action_type) else 0,
        "undo_notice": f"执行后 {CUSTOMER_PULSE_UNDO_WINDOW_MINUTES} 分钟内可撤销。"
        if _action_requires_undo_window(resolved_action_type)
        else "",
        "evidence": presented["evidence"],
        "effect_scope": "local_only",
        "preview": {},
    }
    if resolved_action_type == "generate_reply_draft":
        draft_blocked_by_ai = bool(action_payload.get("draft_blocked_by_ai"))
        preview_result["effect_scope"] = "draft_only"
        preview_result["preview"] = {
            "draft_message": ""
            if draft_blocked_by_ai
            else (
                presented["draft_message"]
                or _build_rule_based_draft_message(
                    customer_name=presented["customer_name"],
                    summary=presented["summary"],
                    evidence=presented["evidence"],
                )
            ),
            "channel_type": "existing_customer_channel",
            "auto_send": False,
            "draft_blocked_by_ai": draft_blocked_by_ai,
            "draft_notice": _normalized_text(action_payload.get("draft_notice"))
            or "所有外发消息默认只生成草稿，需人工确认后再发送。",
        }
    elif resolved_action_type == "update_followup_segment":
        followup_segment = _normalized_text(action_payload.get("followup_segment")) or "focus"
        preview_result["effect_scope"] = "marketing_state"
        preview_result["preview"] = {
            "followup_segment": followup_segment,
            "followup_segment_label": _segment_label(followup_segment),
        }
    elif resolved_action_type == "create_followup_task":
        preview_result["preview"] = {
            "task_title": _normalized_text(action_payload.get("task_title")) or _normalized_text(candidate.get("title")) or presented["title"],
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    elif resolved_action_type == "set_followup_reminder":
        preview_result["preview"] = {
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    elif resolved_action_type == "update_tags":
        preview_result["effect_scope"] = "contact_tags"
        preview_result["preview"] = {
            "add_tag_ids": action_payload.get("add_tag_ids") or [],
            "remove_tag_ids": action_payload.get("remove_tag_ids") or [],
        }
    else:
        raise ValueError("unsupported action_type")
    return preview_result


def execute_customer_pulse_card_action(
    card_id: int,
    *,
    action_type: str = "",
    operator: str = "",
    extra_payload: dict[str, Any] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    if not is_customer_pulse_inbox_enabled(access_context=resolved_context):
        raise ValueError("AI推进功能未启用")
    requested_action_type = _normalized_text(action_type)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    presented = _present_card(card, access_context=resolved_context)
    if requested_action_type and not _action_allowed(requested_action_type):
        raise ValueError("当前动作已被系统配置禁用")
    if requested_action_type and customer_pulse_action_permission(requested_action_type):
        assert_customer_pulse_action_permission(requested_action_type, access_context=resolved_context)
    resolved_action_type, candidate_payload, candidate = _resolve_card_action_candidate(presented, action_type=requested_action_type)
    assert_customer_pulse_action_permission(resolved_action_type, access_context=resolved_context)
    if not _action_allowed(resolved_action_type):
        raise ValueError("当前动作已被系统配置禁用")
    extra_payload = dict(extra_payload or {})
    action_payload = {**candidate_payload, **extra_payload}
    normalized_operator = _normalized_text(operator) or "crm_console"
    reference_preview = preview_customer_pulse_card_action(
        card_id,
        action_type=resolved_action_type,
        track_click=False,
        tenant_context=resolved_context,
        tenant_key=resolved_tenant_key,
    )
    _assert_action_scope(presented, action_payload)
    normalized_execution_payload = _normalize_action_execution_payload(
        card=presented,
        action_type=resolved_action_type,
        candidate=candidate,
        action_payload=action_payload,
    )
    reference_execution_payload = _normalize_action_execution_payload(
        card=presented,
        action_type=resolved_action_type,
        candidate=candidate,
        action_payload=dict(reference_preview.get("preview") or {}),
    )
    edited_fields = _edited_fields(reference_execution_payload, normalized_execution_payload)
    learning_feedback_type = "edited_then_sent" if edited_fields else "adopted"
    base_execution_labels = _ai_audit_labels_from_candidate(candidate, candidate_payload)
    execution_audit_labels = _execution_audit_labels(base_labels=base_execution_labels, edited_fields=edited_fields)
    unsafe_input_fields = _unsafe_execution_input_fields(resolved_action_type, extra_payload)
    text_guardrail_hits = _draft_execution_guardrail_hits(resolved_action_type, normalized_execution_payload)
    request_payload_with_audit = {
        **normalized_execution_payload,
        "audit": _request_payload_audit_summary(
            action_type=resolved_action_type,
            request_payload=normalized_execution_payload,
            tenant_context=resolved_context,
            operator=normalized_operator,
            card=presented,
            execution_labels=base_execution_labels,
            unsafe_input_fields=unsafe_input_fields,
            text_guardrail_hits=text_guardrail_hits,
        ),
    }
    idempotency_key = _build_action_idempotency_key(card_id, resolved_action_type, normalized_execution_payload)
    existing_log = repo.get_latest_customer_pulse_execution_log_by_idempotency(
        card_id=card_id,
        action_type=resolved_action_type,
        idempotency_key=idempotency_key,
        tenant_key=resolved_tenant_key,
    )
    if existing_log and _normalized_text(existing_log.get("execution_status")) == "confirmed" and not _normalized_text(existing_log.get("undone_at")):
        return _existing_execution_response(
            existing_log,
            card_id=card_id,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )

    execution_key = _execution_key()
    pre_card_snapshot = _card_state_snapshot(presented)
    rollback_payload = _execution_rollback_payload(
        action_type=resolved_action_type,
        pre_card_snapshot=pre_card_snapshot,
        status="pending",
    )
    rollback_payload["resource_id"] = str(card_id)
    execution_log = repo.insert_customer_pulse_execution_log(
        card_id=card_id,
        external_userid=presented["external_userid"],
        action_type=resolved_action_type,
        execution_status="processing",
        channel_type="",
        operator=normalized_operator,
        actor_userid=_normalized_text(resolved_context.get("actor_userid") or resolved_context.get("user_id")),
        actor_role=_normalized_text(resolved_context.get("actor_role") or resolved_context.get("role")),
        resource_type=CUSTOMER_PULSE_RESOURCE_CARD,
        resource_id=str(card_id),
        tenant_key=resolved_tenant_key,
        execution_key=execution_key,
        idempotency_key=idempotency_key,
        request_payload=request_payload_with_audit,
        result_payload={},
        error_message="",
        tenant_context=customer_pulse_tenant_context_summary(resolved_context),
        audit_labels=base_execution_labels,
        rollback_payload=rollback_payload,
    )

    channel_type = ""
    try:
        if unsafe_input_fields:
            raise ValueError(f"检测到未授权字段更新：{', '.join(unsafe_input_fields)}")
        if text_guardrail_hits:
            raise ValueError(f"草稿命中安全风控：{', '.join(text_guardrail_hits)}")
        activity_log_id = 0
        outbound_task_id = 0
        undo_until = _undo_until() if _action_requires_undo_window(resolved_action_type) else ""
        updated_row: dict[str, Any]
        result_payload: dict[str, Any]

        if resolved_action_type == "generate_reply_draft":
            draft_blocked_by_ai = bool(action_payload.get("draft_blocked_by_ai"))
            explicit_draft_message = _normalized_text(normalized_execution_payload.get("draft_message"))
            if draft_blocked_by_ai and not explicit_draft_message:
                raise ValueError("当前 AI 置信度不足或命中风控，请人工编辑草稿后再保存。")
            draft_message = explicit_draft_message or presented["draft_message"] or _build_rule_based_draft_message(
                customer_name=presented["customer_name"],
                summary=presented["summary"],
                evidence=presented["evidence"],
            )
            draft_task = save_local_private_message_draft(
                _reply_draft_task_payload(presented, draft_message, execution_key),
                source=CUSTOMER_PULSE_FLAG_KEY,
            )
            outbound_task_id = int(draft_task.get("task_id") or 0)
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="draft_ready",
                draft_message=draft_message,
                need_human_confirmation=True,
                snooze_until="",
                resolved_at="",
                resolution_note="",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="reply_draft",
                activity_status="draft_ready",
                title="已保存 AI 回复草稿",
                summary=f"已为 {presented['customer_name']} 生成并保存可编辑草稿",
                operator=normalized_operator,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "draft_message": draft_message,
                    "outbound_task_id": outbound_task_id,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "existing_customer_channel"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "draft_message": draft_message,
                "auto_send": False,
                "need_human_confirmation": True,
                "stored_locally": True,
                "copy_text": draft_message,
                "outbound_task_id": outbound_task_id,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "create_followup_task":
            due_at = _normalized_text(normalized_execution_payload.get("due_at")) or _next_followup_time()
            task_title = _normalized_text(normalized_execution_payload.get("task_title")) or _normalized_text(candidate.get("title")) or presented["title"]
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="completed",
                due_at=due_at,
                resolved_at=_iso_now(),
                resolution_note="local_followup_task_created",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="followup_task",
                activity_status="open",
                title=task_title,
                summary=f"AI 建议已落地为跟进任务：{task_title}",
                operator=normalized_operator,
                due_at=due_at,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "task_title": task_title,
                    "due_at": due_at,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "local_task"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "task_title": task_title,
                "due_at": due_at,
                "stored_locally": True,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "update_followup_segment":
            followup_segment = _normalized_text(normalized_execution_payload.get("followup_segment")) or "focus"
            current_marketing_state = repo.get_customer_marketing_state_current(presented["external_userid"]) or {}
            before_followup_segment = _followup_segment_from_marketing_state(current_marketing_state) or "normal"
            marketing_result = set_manual_followup_segment(
                external_userid=presented["external_userid"],
                followup_segment=followup_segment,
                owner_userid=presented["owner_userid"],
                operator=normalized_operator,
                source="customer_pulse_inbox",
            )
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="completed",
                resolved_at=_iso_now(),
                resolution_note=f"followup_segment:{followup_segment}",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="followup_segment_update",
                activity_status="applied",
                title="已更新跟进阶段",
                summary=f"{_segment_label(before_followup_segment)} -> {_segment_label(followup_segment)}",
                operator=normalized_operator,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "before_followup_segment": before_followup_segment,
                    "after_followup_segment": followup_segment,
                    "marketing_result": marketing_result,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "crm_console_mutation"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "marketing_result": marketing_result,
                "before_followup_segment": before_followup_segment,
                "after_followup_segment": followup_segment,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "update_tags":
            current_tag_rows = repo.list_contact_tag_rows(presented["external_userid"], limit=100)
            current_tag_ids = {
                _normalized_text(item.get("tag_id"))
                for item in current_tag_rows
                if _normalized_text(item.get("userid")) == presented["owner_userid"] and _normalized_text(item.get("tag_id"))
            }
            add_tag_ids = sorted(
                {
                    _normalized_text(item)
                    for item in (normalized_execution_payload.get("add_tag_ids") or [])
                    if _normalized_text(item)
                }
            )
            remove_tag_ids = sorted(
                {
                    _normalized_text(item)
                    for item in (normalized_execution_payload.get("remove_tag_ids") or [])
                    if _normalized_text(item)
                }
            )
            applied_add_tag_ids = [item for item in add_tag_ids if item not in current_tag_ids]
            applied_remove_tag_ids = [item for item in remove_tag_ids if item in current_tag_ids]
            if not applied_add_tag_ids and not applied_remove_tag_ids:
                raise ValueError("当前标签变更已存在，无需重复执行")
            if applied_add_tag_ids:
                mark_customer_tags(
                    {
                        "userid": presented["owner_userid"],
                        "external_userid": presented["external_userid"],
                        "add_tag": applied_add_tag_ids,
                    }
                )
            if applied_remove_tag_ids:
                unmark_customer_tags(
                    {
                        "userid": presented["owner_userid"],
                        "external_userid": presented["external_userid"],
                        "remove_tag": applied_remove_tag_ids,
                    }
                )
            after_tag_ids = sorted((current_tag_ids | set(applied_add_tag_ids)) - set(applied_remove_tag_ids))
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="completed",
                resolved_at=_iso_now(),
                resolution_note="customer_tags_updated",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="tag_update",
                activity_status="applied",
                title="已更新客户标签",
                summary=f"新增 {len(applied_add_tag_ids)} 个标签，移除 {len(applied_remove_tag_ids)} 个标签",
                operator=normalized_operator,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "before_tag_ids": sorted(current_tag_ids),
                    "applied_add_tag_ids": applied_add_tag_ids,
                    "applied_remove_tag_ids": applied_remove_tag_ids,
                    "after_tag_ids": after_tag_ids,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "contact_tags"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "applied_add_tag_ids": applied_add_tag_ids,
                "applied_remove_tag_ids": applied_remove_tag_ids,
                "after_tag_ids": after_tag_ids,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "set_followup_reminder":
            due_at = _normalized_text(normalized_execution_payload.get("due_at")) or _next_followup_time()
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="snoozed",
                due_at=due_at,
                snooze_until=due_at,
                resolution_note="next_followup_reminder_set",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="followup_reminder",
                activity_status="scheduled",
                title="已设置下次跟进提醒",
                summary=f"提醒时间：{due_at}",
                operator=normalized_operator,
                due_at=due_at,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "due_at": due_at,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "local_reminder"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "due_at": due_at,
                "stored_locally": True,
                "activity_log_id": activity_log_id,
            }
        else:
            raise ValueError("unsupported action_type")

        rollback_payload = _execution_rollback_payload(
            action_type=resolved_action_type,
            pre_card_snapshot=pre_card_snapshot,
            undo_until=undo_until,
            status="available" if undo_until else "completed",
            activity_log_id=activity_log_id,
        )
        rollback_payload["resource_id"] = str(card_id)
        result_payload["audit"] = _result_payload_audit_summary(
            action_type=resolved_action_type,
            card_before=pre_card_snapshot,
            card_after=_card_state_snapshot(updated_card),
            execution_labels=execution_audit_labels,
            edited_fields=edited_fields,
            status="confirmed",
            rollback_payload=rollback_payload,
        )
        result_payload["audit_labels"] = execution_audit_labels
        if resolved_action_type == "generate_reply_draft":
            result_payload["draft_review_status"] = (
                _EXECUTION_AUDIT_HUMAN_EDITED if edited_fields else _EXECUTION_AUDIT_HUMAN_CONFIRMED
            )
        if resolved_action_type in {"update_followup_segment", "update_tags", "set_followup_reminder"}:
            result_payload["safe_field_update_review_status"] = (
                _EXECUTION_AUDIT_HUMAN_EDITED if edited_fields else _EXECUTION_AUDIT_HUMAN_CONFIRMED
            )
        execution_log = repo.update_customer_pulse_execution_log(
            int(execution_log.get("id") or 0),
            tenant_key=resolved_tenant_key,
            execution_status="confirmed",
            channel_type=channel_type,
            activity_log_id=activity_log_id,
            outbound_task_id=outbound_task_id,
            undo_status="available" if undo_until else "",
            undo_until=undo_until,
            result_payload_json=result_payload,
            error_message="",
            audit_labels_json=execution_audit_labels,
            rollback_payload_json=rollback_payload,
        )
        _record_action_feedback(
            card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
            feedback_type=learning_feedback_type,
            feedback_source="action_execution",
            operator=normalized_operator,
            action_type=resolved_action_type,
            execution_log_id=int(execution_log.get("id") or 0),
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={
                "audit_labels": execution_audit_labels,
                "edited_fields": edited_fields,
                "reference_payload": reference_execution_payload,
                "executed_payload": normalized_execution_payload,
            },
        )
        _record_metric_event(
            event_type="action_executed",
            event_source="customer_pulse_execute",
            card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
            execution_log_id=int(execution_log.get("id") or 0),
            action_type=resolved_action_type,
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"edited_fields": edited_fields, "audit_labels": execution_audit_labels},
        )
        metric_type_map = {
            "generate_reply_draft": "draft_confirmed",
            "create_followup_task": "followup_task_created",
            "update_followup_segment": "followup_segment_updated",
        }
        metric_event_type = metric_type_map.get(resolved_action_type)
        if metric_event_type:
            _record_metric_event(
                event_type=metric_event_type,
                event_source="customer_pulse_execute",
                card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
                execution_log_id=int(execution_log.get("id") or 0),
                action_type=resolved_action_type,
                operator=normalized_operator,
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                payload={"edited_fields": edited_fields, "audit_labels": execution_audit_labels},
            )
        _record_metric_event(
            event_type="writeback_success",
            event_source="customer_pulse_execute",
            card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
            execution_log_id=int(execution_log.get("id") or 0),
            action_type=resolved_action_type,
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )
        return _build_execution_response(
            card_id=card_id,
            action_type=resolved_action_type,
            result_payload=result_payload,
            execution_log=execution_log,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )
    except Exception as exc:
        failure_result_payload = {
            "retryable": True,
            "error_message": str(exc),
            "audit": _result_payload_audit_summary(
                action_type=resolved_action_type,
                card_before=pre_card_snapshot,
                card_after={},
                execution_labels=execution_audit_labels,
                edited_fields=edited_fields,
                status="failed",
                error_message=str(exc),
                rollback_payload=rollback_payload,
            ),
            "audit_labels": execution_audit_labels,
            "guardrails": _guardrail_summary(
                execution_labels=execution_audit_labels,
                unsafe_input_fields=unsafe_input_fields,
                text_guardrail_hits=text_guardrail_hits,
                ai_guardrails=((presented.get("snapshot") or {}).get("ai_payload") or {}).get("guardrails")
                if isinstance(((presented.get("snapshot") or {}).get("ai_payload") or {}), dict)
                else {},
            ),
        }
        repo.update_customer_pulse_execution_log(
            int(execution_log.get("id") or 0),
            tenant_key=resolved_tenant_key,
            execution_status="failed",
            channel_type=channel_type,
            result_payload_json=failure_result_payload,
            error_message=str(exc),
            audit_labels_json=execution_audit_labels,
            rollback_payload_json=rollback_payload,
        )
        if unsafe_input_fields or text_guardrail_hits:
            _record_metric_event(
                event_type="guardrail_blocked",
                event_source="customer_pulse_execute",
                card=presented,
                execution_log_id=int(execution_log.get("id") or 0),
                action_type=resolved_action_type,
                operator=normalized_operator,
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                payload={
                    "unsafe_input_fields": unsafe_input_fields,
                    "text_guardrail_hits": text_guardrail_hits,
                    "error_message": str(exc),
                },
            )
        _record_metric_event(
            event_type="writeback_failed",
            event_source="customer_pulse_execute",
            card=presented,
            execution_log_id=int(execution_log.get("id") or 0),
            action_type=resolved_action_type,
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"error_message": str(exc)},
        )
        raise


def undo_customer_pulse_card_action_execution(
    execution_id: int,
    *,
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        return {
            "key": "customer_pulse",
            "title": "AI推进收件箱",
            "count": 0,
            "description": "当前租户或角色未进入 Customer Pulse 灰度范围。",
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "tone": "ok",
            "items": [],
            "empty_title": "当前未开放 AI 推进灰度",
            "href": "/admin/customer-pulse",
        }
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    execution_log = repo.get_customer_pulse_execution_log(int(execution_id), tenant_key=resolved_tenant_key)
    if not execution_log:
        raise LookupError("execution not found")
    presented_execution = _present_execution_log(execution_log) or {}
    if presented_execution.get("execution_status") != "confirmed":
        raise ValueError("当前执行记录尚未成功，不能撤销")
    if not bool(presented_execution.get("undo_supported")):
        raise ValueError("当前动作不支持撤销")
    if _normalized_text(presented_execution.get("undone_at")):
        raise ValueError("该执行记录已撤销")
    if not bool(presented_execution.get("undo_available")):
        raise ValueError("撤销窗口已过期")
    latest_execution = repo.get_latest_customer_pulse_execution_log(
        int(presented_execution.get("card_id") or 0),
        tenant_key=resolved_tenant_key,
    )
    if latest_execution and int(latest_execution.get("id") or 0) != int(execution_id) and not _normalized_text(latest_execution.get("undone_at")):
        raise ValueError("当前卡片已有更新后的执行记录，不能撤销旧动作")

    normalized_operator = _normalized_text(operator) or "crm_console"
    result_payload = dict(presented_execution.get("result_payload") or {})
    pre_card_snapshot = dict(result_payload.get("card_before") or {})
    if not pre_card_snapshot:
        raise ValueError("缺少撤销所需的原始卡片状态")

    action_type = _normalized_text(presented_execution.get("action_type"))
    assert_customer_pulse_action_permission(action_type, access_context=resolved_context)
    external_userid = _normalized_text(presented_execution.get("external_userid"))
    card_id = int(presented_execution.get("card_id") or 0)
    current_card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not current_card:
        raise LookupError("card not found")
    presented_card = _present_card(current_card, access_context=resolved_context)
    now = _iso_now()

    if action_type == "generate_reply_draft":
        outbound_task_id = int(presented_execution.get("outbound_task_id") or result_payload.get("outbound_task_id") or 0)
        if outbound_task_id:
            existing_task = get_outbound_task(outbound_task_id) or {}
            response_payload = _json_loads(existing_task.get("response_payload"), default={})
            if not isinstance(response_payload, dict):
                response_payload = {}
            response_payload.update(
                {
                    "draft_only": True,
                    "cancelled_at": now,
                    "cancelled_by": normalized_operator,
                    "cancel_source": "customer_pulse_undo",
                }
            )
            update_outbound_task_status(outbound_task_id, status="cancelled", response_payload=response_payload)
    elif action_type == "create_followup_task":
        pass
    elif action_type == "update_followup_segment":
        before_followup_segment = _normalized_text(result_payload.get("before_followup_segment"))
        if before_followup_segment not in {"normal", "focus"}:
            raise ValueError("原始跟进阶段不支持撤销")
        set_manual_followup_segment(
            external_userid=external_userid,
            followup_segment=before_followup_segment,
            owner_userid=presented_card["owner_userid"],
            operator=normalized_operator,
            source="customer_pulse_undo",
        )
    elif action_type == "update_tags":
        applied_add_tag_ids = [
            _normalized_text(item)
            for item in (result_payload.get("applied_add_tag_ids") or [])
            if _normalized_text(item)
        ]
        applied_remove_tag_ids = [
            _normalized_text(item)
            for item in (result_payload.get("applied_remove_tag_ids") or [])
            if _normalized_text(item)
        ]
        if applied_add_tag_ids:
            unmark_customer_tags(
                {
                    "userid": presented_card["owner_userid"],
                    "external_userid": external_userid,
                    "remove_tag": applied_add_tag_ids,
                }
            )
        if applied_remove_tag_ids:
            mark_customer_tags(
                {
                    "userid": presented_card["owner_userid"],
                    "external_userid": external_userid,
                    "add_tag": applied_remove_tag_ids,
                }
            )
    elif action_type == "set_followup_reminder":
        pass
    else:
        raise ValueError("unsupported action_type")

    restored_row = _restore_card_state(
        card_id,
        pre_card_snapshot,
        tenant_context=resolved_context,
        tenant_key=resolved_tenant_key,
    )
    activity_log_id = int(presented_execution.get("activity_log_id") or result_payload.get("activity_log_id") or 0)
    if activity_log_id:
        repo.update_customer_pulse_activity_log(
            activity_log_id,
            tenant_key=resolved_tenant_key,
            activity_status="undone",
            undone_at=now,
        )
    undo_activity = repo.insert_customer_pulse_activity_log(
        card_id=card_id,
        external_userid=external_userid,
        owner_userid=presented_card["owner_userid"],
        activity_type="action_undo",
        activity_status="completed",
        title=f"已撤销{_action_label(action_type)}",
        summary=f"已撤销 AI 建议执行：{_action_label(action_type)}",
        operator=normalized_operator,
        activity_source=CUSTOMER_PULSE_FLAG_KEY,
        tenant_key=resolved_tenant_key,
        execution_key=_execution_key(),
        idempotency_key=f"undo-{presented_execution.get('execution_key')}",
        payload={
            "reverted_execution_id": int(execution_id),
            "reverted_action_type": action_type,
            "reverted_activity_log_id": activity_log_id,
        },
    )
    result_payload["undo_activity_log_id"] = int(undo_activity.get("id") or 0)
    result_payload["undone_at"] = now
    result_payload["undone_by"] = normalized_operator
    rollback_payload = dict(presented_execution.get("rollback_payload") or {})
    rollback_payload.update(
        {
            "resource_id": str(card_id),
            "status": "undone",
            "undone_at": now,
            "undo_activity_log_id": int(undo_activity.get("id") or 0),
        }
    )
    result_payload["audit"] = _result_payload_audit_summary(
        action_type=action_type,
        card_before=pre_card_snapshot,
        card_after=_card_state_snapshot(_present_card(restored_row, access_context=resolved_context)),
        execution_labels=[_normalized_text(item) for item in presented_execution.get("audit_labels") or [] if _normalized_text(item)],
        edited_fields=[],
        status="undone",
        rollback_payload=rollback_payload,
    )
    execution_log = repo.update_customer_pulse_execution_log(
        int(execution_id),
        tenant_key=resolved_tenant_key,
        undo_status="undone",
        undone_at=now,
        result_payload_json=result_payload,
        rollback_payload_json=rollback_payload,
    )
    return {
        "ok": True,
        "action_type": action_type,
        "action_label": _action_label(action_type),
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "card": _present_card(restored_row, access_context=resolved_context),
        "execution": _present_execution_log(execution_log),
        "undo_activity": {
            "id": int(undo_activity.get("id") or 0),
            "title": _normalized_text(undo_activity.get("title")),
            "summary": _normalized_text(undo_activity.get("summary")),
            "created_at": _normalized_text(undo_activity.get("created_at")),
        },
    }


def submit_customer_pulse_feedback(
    card_id: int,
    *,
    feedback_type: str,
    note: str = "",
    operator: str = "",
    payload: dict[str, Any] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    assert_customer_pulse_feedback_permission(resolved_context)
    presented = _present_card(card, access_context=resolved_context)
    normalized_feedback_type = _normalized_text(feedback_type).lower()
    normalized_operator = _normalized_text(operator) or "crm_console"
    payload = dict(payload or {})
    if normalized_feedback_type in {"adopted", "edited_then_sent", "misjudged", "unhelpful", "ignored"}:
        feedback_row = _record_action_feedback(
            card=presented,
            feedback_type=normalized_feedback_type,
            feedback_source=_normalized_text(payload.get("feedback_source")) or "manual_feedback",
            operator=normalized_operator,
            action_type=_normalized_text(payload.get("action_type")) or _normalized_text(presented.get("suggested_action_type")),
            execution_log_id=int(payload.get("execution_id") or 0) or None,
            note=note,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload=payload,
        )
        if normalized_feedback_type == "ignored":
            _record_metric_event(
                event_type="card_ignored",
                event_source=_normalized_text(payload.get("feedback_source")) or "manual_feedback",
                card=presented,
                operator=normalized_operator,
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
            )
        return {
            "ok": True,
            "card": presented,
            "feedback": feedback_row,
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        }
    update_fields: dict[str, Any]
    feedback_value = ""
    action_feedback_type = ""
    if normalized_feedback_type == "complete":
        update_fields = {
            "card_status": "completed",
            "resolved_at": _iso_now(),
            "resolution_note": _normalized_text(note) or "marked_complete",
            "snooze_until": "",
        }
    elif normalized_feedback_type == "dismiss":
        update_fields = {
            "card_status": "dismissed",
            "resolved_at": _iso_now(),
            "resolution_note": _normalized_text(note) or "dismissed",
            "snooze_until": "",
        }
        action_feedback_type = "ignored"
    elif normalized_feedback_type == "reopen":
        update_fields = {
            "card_status": "open",
            "resolved_at": "",
            "resolution_note": _normalized_text(note),
            "snooze_until": "",
        }
    elif normalized_feedback_type == "snooze":
        snooze_until = _normalized_text(payload.get("snooze_until")) or _next_followup_time()
        feedback_value = snooze_until
        update_fields = {
            "card_status": "snoozed",
            "due_at": snooze_until,
            "snooze_until": snooze_until,
            "resolution_note": _normalized_text(note) or "snoozed",
        }
    else:
        raise ValueError("unsupported feedback_type")
    updated_row = repo.update_customer_pulse_card(card_id, tenant_key=resolved_tenant_key, **update_fields)
    feedback_row = repo.insert_customer_pulse_feedback(
        card_id=card_id,
        tenant_key=resolved_tenant_key,
        external_userid=presented["external_userid"],
        feedback_type=normalized_feedback_type,
        feedback_value=feedback_value,
        note=note,
        operator=normalized_operator,
        payload=payload,
    )
    action_feedback_row = {}
    if action_feedback_type:
        action_feedback_row = _record_action_feedback(
            card=_present_card(updated_row, access_context=resolved_context),
            feedback_type=action_feedback_type,
            feedback_source=_normalized_text(payload.get("feedback_source")) or "card_feedback",
            operator=normalized_operator,
            action_type=_normalized_text(payload.get("action_type")) or _normalized_text(presented.get("suggested_action_type")),
            execution_log_id=int(payload.get("execution_id") or 0) or None,
            note=note,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload=payload,
        )
        _record_metric_event(
            event_type="card_ignored",
            event_source=_normalized_text(payload.get("feedback_source")) or "card_feedback",
            card=_present_card(updated_row, access_context=resolved_context),
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )
    return {
        "ok": True,
        "card": _present_card(updated_row, access_context=resolved_context),
        "feedback": feedback_row,
        "action_feedback": action_feedback_row,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
    }


def build_customer_pulse_dashboard_group(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    rows = repo.list_recent_customer_pulse_cards_for_dashboard(limit=5, tenant_key=resolved_tenant_key)
    items = [
        {
            "title": _normalized_text(row.get("customer_name")) or _normalized_text(row.get("external_userid")),
            "meta": _action_label(row.get("suggested_action_type")),
            "detail": _normalized_text(row.get("summary")) or _normalized_text(row.get("title")) or "待处理客户推进卡",
        }
        for row in rows
    ]
    counts = repo.count_customer_pulse_cards_by_status(tenant_key=resolved_tenant_key)
    count = int(counts.get("open", 0) or 0) + int(counts.get("draft_ready", 0) or 0)
    return {
        "key": "customer_pulse",
        "title": "AI推进收件箱",
        "count": count,
        "description": "今天该处理的客户推进动作卡。",
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "tone": "warn" if count else "ok",
        "items": items,
        "empty_title": "当前没有待处理推进卡",
        "href": "/admin/customer-pulse",
    }
