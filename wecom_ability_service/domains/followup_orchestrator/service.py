from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Mapping

from flask import current_app, has_app_context, has_request_context

from ...infra.settings import get_setting
from ..customer_pulse import (
    build_customer_pulse_inbox_payload,
    customer_pulse_feature_gate_summary,
    execute_customer_pulse_card_action,
    get_customer_pulse_card_payload,
    preview_customer_pulse_card_action,
    undo_customer_pulse_card_action_execution,
)
from ..customer_pulse import repo as customer_pulse_repo
from ..customer_pulse.access import (
    CustomerPulseAccessDenied,
    current_customer_pulse_request_access_context,
    customer_pulse_template_access_payload,
    customer_pulse_tenant_context_summary,
    resolve_customer_pulse_read_scope,
)
from . import repo

FOLLOWUP_ORCHESTRATOR_FLAG_KEY = "ai_followup_orchestrator"
FOLLOWUP_ORCHESTRATOR_FLAG_POLICY_KEY = "FOLLOWUP_ORCHESTRATOR_FLAG_POLICY_JSON"
FOLLOWUP_ORCHESTRATOR_POLICY_KEY = "FOLLOWUP_ORCHESTRATOR_POLICY_JSON"
FOLLOWUP_ORCHESTRATOR_SOURCE_TYPE = "customer_pulse_rule_engine"
FOLLOWUP_ORCHESTRATOR_MISSION_STATES = (
    "unassigned",
    "suggested",
    "accepted",
    "approved",
    "executing",
    "completed",
    "skipped",
    "escalated",
)
FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS = (
    "accept",
    "claim",
    "complete",
    "reject",
    "suggest_assignment",
    "request_manager_approval",
    "prebuild_batch_draft",
    "escalate",
    "mark_blocked",
    "skip",
)
FOLLOWUP_ORCHESTRATOR_DECISION_TYPES = (
    "claim",
    "reassign",
    "escalate",
    "batch",
)
FOLLOWUP_ORCHESTRATOR_DECISION_STATUSES = (
    "suggested",
    "accepted",
    "rejected",
    "approved",
    "executing",
    "completed",
)
FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD = 5
FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD = 3
FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS = 24
FOLLOWUP_ORCHESTRATOR_BATCH_MIN_SIZE = 2
FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD = 2
FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS = 200
FOLLOWUP_ORCHESTRATOR_RULES_VERSION = "followup_orchestrator_rules_v1"
FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS = {
    "base_priority_multiplier": 1.0,
    "overdue_bonus": 22,
    "due_soon_bonus": 8,
    "missing_owner_bonus": 18,
    "owner_overload_bonus": 14,
    "high_risk_bonus": 20,
    "repeat_unhandled_bonus": 10,
    "batchable_bonus": 6,
}
FOLLOWUP_ORCHESTRATOR_REJECTABLE_ACTIONS = {"reject", "skip", "mark_blocked"}
FOLLOWUP_ORCHESTRATOR_ACTIVE_ITEM_STATES = {"unassigned", "suggested", "accepted", "approved", "executing"}
FOLLOWUP_ORCHESTRATOR_STABLE_ITEM_STATES = {"accepted", "approved", "executing", "completed", "skipped", "escalated"}
FOLLOWUP_ORCHESTRATOR_STABLE_MISSION_STATES = {"accepted", "approved", "executing", "completed", "skipped", "escalated"}
FOLLOWUP_ORCHESTRATOR_HIGH_RISK_KEYS = {"unanswered_question", "negative_sentiment", "service_exception"}
FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES = {
    "generate_reply_draft",
    "create_followup_task",
    "update_followup_segment",
    "update_tags",
    "set_followup_reminder",
}
FOLLOWUP_ORCHESTRATOR_EXECUTION_STATES = (
    "not_started",
    "draft_ready",
    "pending_approval",
    "executed",
    "completed",
    "skipped",
    "escalated",
)
FOLLOWUP_ORCHESTRATOR_DEFAULT_POLICY = {
    "mission_enabled": True,
    "batch_draft_enabled": True,
    "reassign_enabled": True,
    "allow_cross_team_reassign": False,
    "manager_approval_actions": ["reassign", "cross_team_reassign", "batch_draft"],
    "owner_overload_threshold": FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD,
    "owner_high_priority_threshold": FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD,
    "sla_due_soon_hours": FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS,
    "team_map": {},
}
FOLLOWUP_ORCHESTRATOR_DEFAULT_STATS_WINDOW_DAYS = 14
FOLLOWUP_ORCHESTRATOR_SECURITY_UNAUTHORIZED_CODES = {
    "owner_scope_forbidden",
    "operator_role_forbidden",
    "approval_required",
    "feature_disabled",
}
FOLLOWUP_ORCHESTRATOR_SECURITY_CROSS_TENANT_CODES = {"cross_tenant_owner_scope"}
_FOLLOWUP_ORCHESTRATOR_FEATURE_POLICY_RESERVED_KEYS = {"default_enabled", "roles", "userids", "legacy_internal", "tenants"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any) -> bool:
    return _normalized_text(value).lower() in {"1", "true", "yes", "on"}


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


def _config_value(key: str, default: Any = "") -> Any:
    stored = get_setting(key)
    if stored not in (None, ""):
        return stored
    if has_app_context():
        return current_app.config.get(key, default)
    return default


def _config_bool(key: str, *, default: bool) -> bool:
    raw_value = _config_value(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value in (None, ""):
        return default
    return _normalized_bool(raw_value)


def _feature_gate_context(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if access_context is not None:
        return dict(access_context)
    if has_request_context():
        return dict(current_customer_pulse_request_access_context())
    return {}


def _feature_policy_map() -> dict[str, Any]:
    payload = _json_loads(_config_value(FOLLOWUP_ORCHESTRATOR_FLAG_POLICY_KEY, "{}"), default={})
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
            if _normalized_text(key) and key not in _FOLLOWUP_ORCHESTRATOR_FEATURE_POLICY_RESERVED_KEYS and isinstance(value, dict)
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


def _normalized_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, min(parsed, maximum))


def _normalized_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({_normalized_text(item) for item in value if _normalized_text(item)})
    return sorted({_normalized_text(item) for item in _normalized_text(value).replace("|", ",").split(",") if _normalized_text(item)})


def _normalized_team_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        _normalized_text(owner_userid): _normalized_text(team_key)
        for owner_userid, team_key in value.items()
        if _normalized_text(owner_userid) and _normalized_text(team_key)
    }


def _normalized_policy_payload(raw: Any, *, base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = dict(base or FOLLOWUP_ORCHESTRATOR_DEFAULT_POLICY)
    if not isinstance(raw, dict):
        return source
    source["mission_enabled"] = _normalized_bool(raw.get("mission_enabled", source.get("mission_enabled", True)))
    source["batch_draft_enabled"] = _normalized_bool(raw.get("batch_draft_enabled", source.get("batch_draft_enabled", True)))
    source["reassign_enabled"] = _normalized_bool(raw.get("reassign_enabled", source.get("reassign_enabled", True)))
    source["allow_cross_team_reassign"] = _normalized_bool(
        raw.get("allow_cross_team_reassign", source.get("allow_cross_team_reassign", False))
    )
    source["manager_approval_actions"] = _normalized_string_list(
        raw.get("manager_approval_actions", source.get("manager_approval_actions", []))
    )
    source["owner_overload_threshold"] = _normalized_int(
        raw.get("owner_overload_threshold", source.get("owner_overload_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD)),
        default=int(source.get("owner_overload_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD)),
        minimum=1,
        maximum=500,
    )
    source["owner_high_priority_threshold"] = _normalized_int(
        raw.get(
            "owner_high_priority_threshold",
            source.get("owner_high_priority_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD),
        ),
        default=int(source.get("owner_high_priority_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD)),
        minimum=1,
        maximum=200,
    )
    source["sla_due_soon_hours"] = _normalized_int(
        raw.get("sla_due_soon_hours", source.get("sla_due_soon_hours", FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS)),
        default=int(source.get("sla_due_soon_hours", FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS)),
        minimum=1,
        maximum=24 * 30,
    )
    source["team_map"] = _normalized_team_map(raw.get("team_map", source.get("team_map", {})))
    return source


def _policy_map() -> dict[str, Any]:
    payload = _json_loads(_config_value(FOLLOWUP_ORCHESTRATOR_POLICY_KEY, "{}"), default={})
    if not isinstance(payload, dict):
        return {"default": dict(FOLLOWUP_ORCHESTRATOR_DEFAULT_POLICY), "legacy_internal": {}, "tenants": {}}
    return {
        "default": _normalized_policy_payload(payload.get("default", payload)),
        "legacy_internal": payload.get("legacy_internal") if isinstance(payload.get("legacy_internal"), dict) else {},
        "tenants": payload.get("tenants") if isinstance(payload.get("tenants"), dict) else {},
    }


def resolve_followup_orchestrator_policy(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    tenant_key = _normalized_text(context.get("tenant_key")) or "aicrm"
    actor_role = _normalized_text(context.get("actor_role") or context.get("role")).lower()
    policy_map = _policy_map()
    default_policy = _normalized_policy_payload(policy_map.get("default"))
    legacy_mode = bool(context.get("legacy_mode"))
    tenant_section = policy_map.get("legacy_internal") if legacy_mode else (policy_map.get("tenants") or {}).get(tenant_key)
    resolved = _normalized_policy_payload(tenant_section, base=default_policy)
    source = "default"
    if isinstance(tenant_section, dict):
        source = "legacy_internal" if legacy_mode else f"tenant:{tenant_key}"
        role_overrides: dict[str, Any] = {}
        roles_value = tenant_section.get("roles")
        if isinstance(roles_value, dict):
            role_overrides = roles_value
        role_override = role_overrides.get(actor_role)
        if isinstance(role_override, dict):
            resolved = _normalized_policy_payload(role_override, base=resolved)
            source = f"{source}:role:{actor_role}"
    return {
        **resolved,
        "tenant_key": tenant_key,
        "actor_role": actor_role,
        "legacy_mode": legacy_mode,
        "policy_key": FOLLOWUP_ORCHESTRATOR_POLICY_KEY,
        "source": source,
    }


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _mission_status_label(status: Any) -> str:
    mapping = {
        "unassigned": "待分配",
        "suggested": "待接受",
        "accepted": "已接受",
        "approved": "已批准",
        "executing": "执行中",
        "completed": "已完成",
        "skipped": "已跳过",
        "escalated": "已升级",
    }
    normalized = _normalized_text(status)
    return mapping.get(normalized, normalized or "待处理")


def _decision_status_label(status: Any) -> str:
    mapping = {
        "suggested": "待确认",
        "accepted": "已接受",
        "rejected": "已拒绝",
        "approved": "已批准",
        "executing": "执行中",
        "completed": "已完成",
    }
    normalized = _normalized_text(status)
    return mapping.get(normalized, normalized or "待确认")


def _execution_state_label(state: Any) -> str:
    mapping = {
        "not_started": "未开始",
        "draft_ready": "已生成草稿",
        "pending_approval": "待审批",
        "executed": "已执行",
        "completed": "已完成",
        "skipped": "已跳过",
        "escalated": "已升级",
    }
    normalized = _normalized_text(state)
    return mapping.get(normalized, normalized or "未开始")


def _sha_token(*parts: str, length: int = 12) -> str:
    payload = "|".join(_normalized_text(part) for part in parts if _normalized_text(part))
    if not payload:
        return ""
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length]


def _feature_gate_reason(global_enabled: bool, pulse_enabled: bool) -> str:
    if not global_enabled:
        return "global_disabled"
    if not pulse_enabled:
        return "customer_pulse_disabled"
    return "enabled"


def followup_orchestrator_feature_gate_summary(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    pulse_gate = customer_pulse_feature_gate_summary(context)
    global_enabled = _config_bool(FOLLOWUP_ORCHESTRATOR_FLAG_KEY, default=False)
    enabled = bool(global_enabled and pulse_gate.get("enabled"))
    return {
        "enabled": enabled,
        "reason": _feature_gate_reason(global_enabled, bool(pulse_gate.get("enabled"))),
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "tenant_key": _normalized_text(context.get("tenant_key")) or _normalized_text(pulse_gate.get("tenant_key")) or "aicrm",
        "actor_userid": _normalized_text(context.get("actor_userid") or context.get("user_id")),
        "actor_role": _normalized_text(context.get("actor_role") or context.get("role")),
        "mode": _normalized_text(context.get("mode") or pulse_gate.get("mode")),
        "auth_mode": _normalized_text(context.get("auth_mode") or pulse_gate.get("auth_mode")),
        "global_enabled": bool(global_enabled),
        "pulse_feature_gate": pulse_gate,
    }


def is_followup_orchestrator_enabled(*, access_context: Mapping[str, Any] | None = None) -> bool:
    return bool(followup_orchestrator_feature_gate_summary(access_context).get("enabled"))


def _collect_evidence_refs(cards: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for card in cards:
        for item in card.get("evidence_refs") or []:
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
            if len(refs) >= limit:
                return refs
    return refs


def _build_owner_workload(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for card in cards:
        owner_userid = _normalized_text(card.get("owner_userid")) or "unassigned"
        entry = grouped.setdefault(
            owner_userid,
            {
                "owner_userid": owner_userid,
                "owner_display_name": _normalized_text(card.get("owner_display_name")) or owner_userid,
                "open_card_count": 0,
                "high_priority_count": 0,
                "overdue_count": 0,
                "draft_candidate_count": 0,
            },
        )
        entry["open_card_count"] += 1
        if _normalized_text(card.get("priority")) == "high":
            entry["high_priority_count"] += 1
        if bool(card.get("is_overdue")):
            entry["overdue_count"] += 1
        if _normalized_text(card.get("suggested_action_type")) == "generate_reply_draft":
            entry["draft_candidate_count"] += 1
    result = []
    for item in grouped.values():
        result.append(
            {
                **item,
                "is_overloaded": (
                    int(item.get("open_card_count") or 0) >= FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD
                    or int(item.get("high_priority_count") or 0) >= FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            -int(item.get("open_card_count") or 0),
            -int(item.get("high_priority_count") or 0),
            _normalized_text(item.get("owner_display_name")),
        ),
    )


def _team_candidate_owners(read_scope: Mapping[str, Any], owner_workload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_owner_userids = {
        _normalized_text(item)
        for item in (read_scope.get("allowed_owner_userids") or [])
        if _normalized_text(item)
    }
    if not allowed_owner_userids:
        allowed_owner_userids = {
            _normalized_text(item.get("owner_userid"))
            for item in owner_workload
            if _normalized_text(item.get("owner_userid")) and _normalized_text(item.get("owner_userid")) != "unassigned"
        }
    items = [
        item
        for item in owner_workload
        if _normalized_text(item.get("owner_userid")) in allowed_owner_userids and _normalized_text(item.get("owner_userid")) != "unassigned"
    ]
    return sorted(
        items,
        key=lambda item: (
            int(item.get("open_card_count") or 0),
            int(item.get("high_priority_count") or 0),
            _normalized_text(item.get("owner_userid")),
        ),
    )


def _first_signal_key(items: list[dict[str, Any]], *, field: str) -> str:
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalized_text(item.get(field))
        if normalized:
            return normalized
    return ""


def _card_intent_key(card: Mapping[str, Any]) -> str:
    risk_key = _first_signal_key(card.get("risk_flags") or [], field="key")
    if risk_key:
        return f"risk:{risk_key}"
    opportunity_key = _first_signal_key(card.get("opportunity_flags") or [], field="key")
    if opportunity_key:
        return f"opportunity:{opportunity_key}"
    return _normalized_text(card.get("suggested_action_type")) or "general_followup"


def _batch_template_key(card: Mapping[str, Any]) -> str:
    payload = dict(card.get("suggested_action_payload") or {})
    draft_message = _normalized_text(payload.get("draft_message"))
    if draft_message:
        return _sha_token(draft_message[:80], length=10)
    return _sha_token(_normalized_text(card.get("suggested_action_label")), length=10) or "generic"


def _is_high_risk_card(card: Mapping[str, Any]) -> bool:
    return any(
        isinstance(item, dict) and _normalized_text(item.get("key")) in FOLLOWUP_ORCHESTRATOR_HIGH_RISK_KEYS
        for item in (card.get("risk_flags") or [])
    )


def _is_batchable_card(card: Mapping[str, Any]) -> bool:
    if _is_high_risk_card(card):
        return False
    if _normalized_text(card.get("suggested_action_type")) != "generate_reply_draft":
        return False
    return not bool(card.get("draft_blocked_by_ai"))


def _due_urgency(card: Mapping[str, Any]) -> dict[str, Any]:
    due_at = _parse_datetime(card.get("due_at") or card.get("snooze_until"))
    if not due_at:
        return {
            "due_at": "",
            "is_overdue": False,
            "is_due_soon": False,
            "sla_urgency_points": 0,
            "sla_urgency_label": "none",
        }
    now = datetime.now()
    if due_at <= now:
        return {
            "due_at": _normalized_text(card.get("due_at") or card.get("snooze_until")),
            "is_overdue": True,
            "is_due_soon": False,
            "sla_urgency_points": FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["overdue_bonus"],
            "sla_urgency_label": "overdue",
        }
    if due_at <= now + timedelta(hours=FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS):
        return {
            "due_at": _normalized_text(card.get("due_at") or card.get("snooze_until")),
            "is_overdue": False,
            "is_due_soon": True,
            "sla_urgency_points": FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["due_soon_bonus"],
            "sla_urgency_label": "due_soon",
        }
    return {
        "due_at": _normalized_text(card.get("due_at") or card.get("snooze_until")),
        "is_overdue": False,
        "is_due_soon": False,
        "sla_urgency_points": 0,
        "sla_urgency_label": "scheduled",
    }


def _stable_item_status(existing_item: Mapping[str, Any] | None) -> str:
    existing_status = _normalized_text((existing_item or {}).get("item_status"))
    if existing_status in FOLLOWUP_ORCHESTRATOR_STABLE_ITEM_STATES:
        return existing_status
    return ""


def _stable_mission_status(existing_mission: Mapping[str, Any] | None) -> str:
    existing_status = _normalized_text((existing_mission or {}).get("mission_status"))
    if existing_status in FOLLOWUP_ORCHESTRATOR_STABLE_MISSION_STATES:
        return existing_status
    return ""


def _card_signals(
    card: Mapping[str, Any],
    *,
    owner_workload_map: Mapping[str, Mapping[str, Any]],
    team_candidates: list[dict[str, Any]],
    untreated_counts: Mapping[str, int],
) -> dict[str, Any]:
    owner_userid = _normalized_text(card.get("owner_userid"))
    due_signal = _due_urgency(card)
    current_owner_workload = dict(owner_workload_map.get(owner_userid) or {})
    high_risk = _is_high_risk_card(card)
    repeated_unhandled_count = int(untreated_counts.get(_normalized_text(card.get("external_userid"))) or 0)
    batchable = _is_batchable_card(card)
    schedule_score = float(card.get("priority_score") or 0) * FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["base_priority_multiplier"]
    reason_parts = [f"action_card_priority={round(float(card.get('priority_score') or 0), 2)}"]
    if due_signal["sla_urgency_points"]:
        schedule_score += due_signal["sla_urgency_points"]
        reason_parts.append(f"sla={due_signal['sla_urgency_label']}")
    if not owner_userid:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["missing_owner_bonus"]
        reason_parts.append("missing_owner")
    if bool(current_owner_workload.get("is_overloaded")):
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["owner_overload_bonus"]
        reason_parts.append("owner_overloaded")
    if high_risk:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["high_risk_bonus"]
        reason_parts.append("high_risk")
    if repeated_unhandled_count >= FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["repeat_unhandled_bonus"]
        reason_parts.append(f"repeat_unhandled={repeated_unhandled_count}")
    if batchable:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["batchable_bonus"]
        reason_parts.append("batchable")
    available_handoff_candidates = [
        item
        for item in team_candidates
        if _normalized_text(item.get("owner_userid")) != owner_userid and not bool(item.get("is_overloaded"))
    ]
    return {
        "priority_score": round(float(card.get("priority_score") or 0), 2),
        "schedule_score": round(schedule_score, 2),
        "due": due_signal,
        "has_owner": bool(owner_userid),
        "owner_userid": owner_userid,
        "owner_workload": current_owner_workload,
        "team_available_handoff_count": len(available_handoff_candidates),
        "team_available_handoffs": available_handoff_candidates[:5],
        "high_risk": high_risk,
        "batchable": batchable,
        "repeat_unhandled_count": repeated_unhandled_count,
        "rule_reasons": reason_parts,
        "intent_key": _card_intent_key(card),
        "template_key": _batch_template_key(card),
    }


def _batch_group_key(card: Mapping[str, Any], signals: Mapping[str, Any]) -> str:
    return "|".join(
        [
            _normalized_text(card.get("stage_key")) or "unknown_stage",
            _normalized_text(card.get("suggested_action_type")) or "unknown_action",
            _normalized_text(signals.get("intent_key")) or "general",
            _normalized_text(signals.get("template_key")) or "generic",
        ]
    )


def _determine_assignment(card: Mapping[str, Any], signals: Mapping[str, Any], *, can_view_all: bool) -> dict[str, Any]:
    owner_userid = _normalized_text(card.get("owner_userid"))
    available_handoffs = [dict(item) for item in (signals.get("team_available_handoffs") or []) if isinstance(item, dict)]
    target_owner = dict(available_handoffs[0] if available_handoffs else {})
    target_owner_userid = _normalized_text(target_owner.get("owner_userid"))
    target_owner_display_name = _normalized_text(target_owner.get("owner_display_name")) or target_owner_userid
    if not owner_userid:
        return {
            "decision_type": "claim",
            "assignment_status": "suggested",
            "needs_manager_approval": False,
            "suggested_assignee_userid": target_owner_userid,
            "suggested_assignee_display_name": target_owner_display_name,
            "reason": "当前客户没有 owner，建议由团队内负载较低的负责人认领。",
            "confidence": 0.72 if target_owner_userid else 0.48,
        }
    if bool((signals.get("owner_workload") or {}).get("is_overloaded")) and can_view_all and target_owner_userid:
        return {
            "decision_type": "reassign",
            "assignment_status": "suggested",
            "needs_manager_approval": True,
            "suggested_assignee_userid": target_owner_userid,
            "suggested_assignee_display_name": target_owner_display_name,
            "reason": "当前 owner 待办负载偏高，建议由同团队内负载更低的负责人接力。",
            "confidence": 0.63,
        }
    return {
        "decision_type": "",
        "assignment_status": "kept",
        "needs_manager_approval": False,
        "suggested_assignee_userid": owner_userid,
        "suggested_assignee_display_name": _normalized_text(card.get("owner_display_name")) or owner_userid,
        "reason": "当前 owner 仍可继续处理，不建议转派。",
        "confidence": 0.55,
    }


def _escalation_reason(card: Mapping[str, Any], signals: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    high_risk = bool(signals.get("high_risk"))
    repeated_unhandled = int(signals.get("repeat_unhandled_count") or 0) >= FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD
    overdue = bool((signals.get("due") or {}).get("is_overdue"))
    if high_risk:
        reasons.append("命中高风险客户信号")
    if high_risk and overdue:
        reasons.append("已超 SLA")
    if repeated_unhandled:
        reasons.append("连续多次未处理")
    if not (high_risk or repeated_unhandled):
        return {"needs_escalation": False, "reason": "", "confidence": 0.0}
    return {
        "needs_escalation": True,
        "reason": "；".join(reasons),
        "confidence": 0.68 if high_risk else 0.52,
    }


def _mission_type_for_card(
    card: Mapping[str, Any],
    signals: Mapping[str, Any],
    *,
    batch_group_sizes: Mapping[str, int],
    can_view_all: bool,
) -> str:
    batch_group_key = _batch_group_key(card, signals)
    if bool(_escalation_reason(card, signals).get("needs_escalation")):
        return "risk_escalation_wave"
    if not bool(signals.get("has_owner")):
        return "claim_queue"
    assignment = _determine_assignment(card, signals, can_view_all=can_view_all)
    if _normalized_text(assignment.get("decision_type")) == "reassign":
        return "handoff_wave"
    if bool(signals.get("batchable")) and int(batch_group_sizes.get(batch_group_key) or 0) >= FOLLOWUP_ORCHESTRATOR_BATCH_MIN_SIZE:
        return "batch_draft_wave"
    return "priority_wave"


def _mission_key_for_card(
    card: Mapping[str, Any],
    signals: Mapping[str, Any],
    *,
    mission_type: str,
    scope_key: str,
    assignment: Mapping[str, Any],
) -> str:
    if mission_type == "claim_queue":
        return f"mission:claim:{scope_key}"
    if mission_type == "handoff_wave":
        from_owner = _normalized_text(card.get("owner_userid")) or "unassigned"
        to_owner = _normalized_text(assignment.get("suggested_assignee_userid")) or "unassigned"
        return f"mission:handoff:{scope_key}:{from_owner}:{to_owner}"
    if mission_type == "risk_escalation_wave":
        return f"mission:escalation:{scope_key}"
    if mission_type == "batch_draft_wave":
        return f"mission:batch:{scope_key}:{_sha_token(_batch_group_key(card, signals), length=14)}"
    return f"mission:priority:{scope_key}"


def _mission_title(mission_type: str) -> str:
    mapping = {
        "claim_queue": "待认领客户队列",
        "handoff_wave": "团队接力转派波次",
        "risk_escalation_wave": "风险升级波次",
        "batch_draft_wave": "批量草稿波次",
        "priority_wave": "今日优先推进任务包",
    }
    return mapping.get(_normalized_text(mission_type), "团队任务包")


def _mission_summary(mission_type: str, *, item_count: int, scope_label: str) -> str:
    mapping = {
        "claim_queue": f"{scope_label}内共有 {item_count} 位无 owner 客户待认领。",
        "handoff_wave": f"{scope_label}内共有 {item_count} 位客户建议转派接力。",
        "risk_escalation_wave": f"{scope_label}内共有 {item_count} 位客户需要升级处理。",
        "batch_draft_wave": f"{scope_label}内共有 {item_count} 位客户适合成批预生成草稿。",
        "priority_wave": f"{scope_label}内共有 {item_count} 位客户进入高优先级推进序列。",
    }
    return mapping.get(_normalized_text(mission_type), f"{scope_label}内共有 {item_count} 位客户进入团队任务包。")


def _mission_payload(
    mission_type: str,
    *,
    cards: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    assignment_suggestions: list[dict[str, Any]],
    escalation_suggestions: list[dict[str, Any]],
    batch_group_key: str = "",
    scope_key: str,
) -> dict[str, Any]:
    return {
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "mission_type": mission_type,
        "scope_key": scope_key,
        "card_ids": [int(card.get("id") or 0) for card in cards],
        "pulse_snapshot_ids": [int((card.get("snapshot") or {}).get("id") or 0) for card in cards],
        "batch_group_key": _normalized_text(batch_group_key),
        "assignment_suggestions": assignment_suggestions,
        "escalation_suggestions": escalation_suggestions,
        "signals": signals,
        "evidence_refs": _collect_evidence_refs(cards, limit=8),
    }


def _summarize_mission_items(items: list[dict[str, Any]]) -> tuple[str, int]:
    if not items:
        return "suggested", 0
    statuses = {_normalized_text(item.get("item_status")) for item in items if _normalized_text(item.get("item_status"))}
    if statuses <= {"completed"}:
        return "completed", len(items)
    if "executing" in statuses:
        return "executing", len(items)
    if "approved" in statuses and statuses <= {"approved", "completed"}:
        return "approved", len(items)
    if "accepted" in statuses and statuses <= {"accepted", "completed"}:
        return "accepted", len(items)
    if "escalated" in statuses and statuses <= {"escalated", "completed", "skipped"}:
        return "escalated", len(items)
    if statuses <= {"skipped", "completed"}:
        return "skipped", len(items)
    if "unassigned" in statuses:
        return "unassigned", len(items)
    return "suggested", len(items)


def _resolved_followup_read_scope(
    *,
    access_context: Mapping[str, Any] | None,
    requested_owner_userid: str = "",
) -> dict[str, Any]:
    return resolve_customer_pulse_read_scope(
        requested_owner_userid=_normalized_text(requested_owner_userid),
        access_context=_feature_gate_context(access_context),
    )


def _assert_mission_items_accessible(
    items: list[dict[str, Any]],
    *,
    read_scope: Mapping[str, Any],
    action_type: str = "",
) -> None:
    if not items:
        return
    if bool(read_scope.get("can_view_all")):
        allowed_owner_userids = {
            _normalized_text(item)
            for item in (read_scope.get("allowed_owner_userids") or [])
            if _normalized_text(item)
        }
        if not allowed_owner_userids:
            return
        for item in items:
            owner_userid = _normalized_text(item.get("owner_userid"))
            suggested_assignee_userid = _normalized_text(item.get("suggested_assignee_userid"))
            if owner_userid and owner_userid not in allowed_owner_userids:
                raise CustomerPulseAccessDenied(
                    "当前任务包包含超出 owner scope 的客户。",
                    code="owner_scope_forbidden",
                    http_status=403,
                )
            if suggested_assignee_userid and suggested_assignee_userid not in allowed_owner_userids:
                raise CustomerPulseAccessDenied(
                    "当前任务包包含超出 owner scope 的转派建议。",
                    code="owner_scope_forbidden",
                    http_status=403,
                )
        return

    actor_userid = _normalized_text(read_scope.get("actor_userid"))
    normalized_action_type = _normalized_text(action_type)
    for item in items:
        owner_userid = _normalized_text(item.get("owner_userid"))
        suggested_assignee_userid = _normalized_text(item.get("suggested_assignee_userid"))
        accessible = actor_userid and actor_userid in {owner_userid, suggested_assignee_userid}
        if not accessible and not owner_userid and normalized_action_type in {"claim", "accept"}:
            accessible = True
        if not accessible:
            raise CustomerPulseAccessDenied(
                "当前角色不能访问或操作该任务包。",
                code="owner_scope_forbidden",
                http_status=403,
            )
    if normalized_action_type in {"suggest_assignment", "request_manager_approval"} and not bool(read_scope.get("can_view_all")):
        raise CustomerPulseAccessDenied(
            "当前角色没有调整团队分配的权限。",
            code="operator_role_forbidden",
            http_status=403,
        )


def _current_item_execution_state(
    item: Mapping[str, Any],
    *,
    decision: Mapping[str, Any] | None,
) -> str:
    payload = dict(item.get("payload") or {})
    normalized_payload_state = _normalized_text(payload.get("execution_state"))
    if normalized_payload_state in FOLLOWUP_ORCHESTRATOR_EXECUTION_STATES:
        return normalized_payload_state
    item_status = _normalized_text(item.get("item_status"))
    decision_payload = dict((decision or {}).get("payload") or {})
    decision_status = _normalized_text((decision or {}).get("decision_status"))
    if item_status == "completed":
        return "completed"
    if item_status == "skipped":
        return "skipped"
    if item_status == "escalated":
        return "escalated"
    if bool(decision_payload.get("needs_manager_approval")) and decision_status in {"", "suggested", "accepted"}:
        return "pending_approval"
    latest_pulse_execution = dict(payload.get("latest_pulse_execution") or {})
    if latest_pulse_execution and _normalized_text(latest_pulse_execution.get("execution_status")) == "confirmed":
        if _normalized_text(latest_pulse_execution.get("action_type")) == "generate_reply_draft":
            return "draft_ready"
        return "executed"
    return "not_started"


def _artifact_status_from_card_payload(card_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    latest_execution = dict((card_payload or {}).get("latest_execution") or {})
    recent_activities = [dict(item) for item in ((card_payload or {}).get("recent_activities") or []) if isinstance(item, dict)]
    has_open_activity = lambda activity_type: any(
        _normalized_text(item.get("activity_type")) == activity_type and not _normalized_text(item.get("undone_at"))
        for item in recent_activities
    )
    latest_action_type = _normalized_text(latest_execution.get("action_type"))
    latest_action_status = _normalized_text(latest_execution.get("execution_status"))
    return {
        "draft_ready": bool(
            latest_action_type == "generate_reply_draft"
            and latest_action_status == "confirmed"
            and not _normalized_text(latest_execution.get("undone_at"))
        ),
        "followup_task_open": has_open_activity("followup_task"),
        "reminder_scheduled": has_open_activity("followup_reminder"),
        "stage_updated": has_open_activity("followup_segment_update"),
        "tags_updated": has_open_activity("tag_update"),
        "latest_action_type": latest_action_type,
        "latest_action_status": latest_action_status,
    }


def _build_handoff_packet(
    *,
    mission: Mapping[str, Any],
    item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    tenant_context: Mapping[str, Any],
    tenant_key: str,
) -> dict[str, Any]:
    card_payload: dict[str, Any] = {}
    pulse_card_id = int(item.get("pulse_card_id") or 0)
    if pulse_card_id > 0:
        try:
            card_payload = get_customer_pulse_card_payload(
                pulse_card_id,
                tenant_context=dict(tenant_context or {}),
                tenant_key=tenant_key,
            )
        except Exception:
            card_payload = {}
    recent_activities = [dict(activity) for activity in (card_payload.get("recent_activities") or []) if isinstance(activity, dict)]
    recent_key_events = [
        {
            "title": _normalized_text(activity.get("title")),
            "summary": _normalized_text(activity.get("summary")),
            "created_at": _normalized_text(activity.get("created_at")),
            "activity_type": _normalized_text(activity.get("activity_type")),
        }
        for activity in recent_activities[:3]
    ]
    recent_event_summary = "；".join(
        filter(
            None,
            [
                " / ".join(filter(None, [_normalized_text(event.get("title")), _normalized_text(event.get("created_at"))]))
                for event in recent_key_events
            ],
        )
    )
    mission_recommendation = dict((mission.get("ai_enhancement") or {}).get("recommendation") or {})
    packet = {
        "mission_key": _normalized_text(mission.get("mission_key")),
        "mission_title": _normalized_text(mission_recommendation.get("missionTitle")) or _normalized_text(mission.get("title")),
        "handoff_summary": _normalized_text(mission.get("handoff_summary")) or _normalized_text(mission_recommendation.get("handoffSummary")),
        "current_judgement": _normalized_text(item.get("current_judgement")),
        "next_action_suggestion": _normalized_text(item.get("suggested_action_label")),
        "next_action_type": _normalized_text(item.get("suggested_action_type")),
        "why_now": _normalized_text(item.get("why_now")),
        "recent_event_summary": recent_event_summary,
        "recent_key_events": recent_key_events,
        "evidence_refs": list(item.get("evidence_refs") or []),
        "artifact_status": _artifact_status_from_card_payload(card_payload),
        "latest_execution": dict(card_payload.get("latest_execution") or {}),
        "decision": {
            "decision_type": _normalized_text((decision or {}).get("decision_type")),
            "decision_status": _normalized_text((decision or {}).get("decision_status")),
            "current_owner_userid": _normalized_text((decision or {}).get("current_owner_userid")),
            "suggested_owner_userid": _normalized_text((decision or {}).get("suggested_owner_userid")),
            "reason": _normalized_text(((decision or {}).get("payload") or {}).get("reason")),
        },
        "generated_at": datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
    }
    return packet


def _record_orchestrator_activity(
    *,
    item: Mapping[str, Any],
    tenant_key: str,
    operator: str,
    activity_type: str,
    activity_status: str,
    title: str,
    summary: str,
    payload: Mapping[str, Any] | None = None,
    due_at: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    pulse_card_id = int(item.get("pulse_card_id") or 0)
    if pulse_card_id <= 0:
        return {}
    try:
        return customer_pulse_repo.insert_customer_pulse_activity_log(
            card_id=pulse_card_id,
            external_userid=_normalized_text(item.get("external_userid")),
            owner_userid=_normalized_text(item.get("owner_userid")),
            activity_type=activity_type,
            activity_status=activity_status,
            title=title,
            summary=summary,
            operator=_normalized_text(operator) or "crm_console",
            due_at=_normalized_text(due_at),
            activity_source=FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
            tenant_key=tenant_key,
            execution_key=_sha_token(activity_type, _normalized_text(item.get("mission_item_key")), length=16),
            idempotency_key=idempotency_key or _sha_token(
                _normalized_text(item.get("mission_item_key")),
                activity_type,
                _normalized_text(summary),
                length=20,
            ),
            payload=dict(payload or {}),
        )
    except Exception:
        return {}


def _with_item_runtime_payload(
    item_payload: Mapping[str, Any],
    *,
    execution_state: str | None = None,
    latest_pulse_execution: Mapping[str, Any] | None = None,
    latest_pulse_result: Mapping[str, Any] | None = None,
    latest_pulse_action_type: str = "",
    latest_pulse_execution_id: int = 0,
    latest_pulse_activity_log_id: int = 0,
    handoff_packet: Mapping[str, Any] | None = None,
    active_assignee_userid: str = "",
    latest_orchestrator_activity_id: int = 0,
) -> dict[str, Any]:
    payload = dict(item_payload or {})
    if execution_state is not None:
        payload["execution_state"] = _normalized_text(execution_state)
        payload["execution_state_label"] = _execution_state_label(execution_state)
    if latest_pulse_execution is not None:
        payload["latest_pulse_execution"] = dict(latest_pulse_execution or {})
    if latest_pulse_result is not None:
        payload["latest_pulse_result"] = dict(latest_pulse_result or {})
    if latest_pulse_action_type:
        payload["latest_pulse_action_type"] = _normalized_text(latest_pulse_action_type)
    if latest_pulse_execution_id:
        payload["latest_pulse_execution_id"] = int(latest_pulse_execution_id)
    if latest_pulse_activity_log_id:
        payload["latest_pulse_activity_log_id"] = int(latest_pulse_activity_log_id)
    if handoff_packet is not None:
        payload["handoff_packet"] = dict(handoff_packet or {})
    if active_assignee_userid:
        payload["active_assignee_userid"] = _normalized_text(active_assignee_userid)
    if latest_orchestrator_activity_id:
        payload["latest_orchestrator_activity_id"] = int(latest_orchestrator_activity_id)
    return payload


def _apply_mission_ai_if_enabled(
    mission: dict[str, Any],
    *,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(mission, dict):
        return {}
    try:
        from .ai_enhancement import apply_followup_orchestrator_ai_enhancement
    except Exception:
        return dict(mission)
    return apply_followup_orchestrator_ai_enhancement(mission=dict(mission))


def _decorate_mission(mission: Mapping[str, Any], *, items: list[dict[str, Any]], decisions: list[dict[str, Any]], logs: list[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(mission.get("payload") or {})
    return {
        **dict(mission),
        "title": _mission_title(_normalized_text(mission.get("mission_type"))),
        "mission_status_label": _mission_status_label(mission.get("mission_status")),
        "items": items,
        "decisions": decisions,
        "execution_logs": logs,
        "evidence_refs": list(payload.get("evidence_refs") or []),
        "rules_version": _normalized_text(payload.get("rules_version")) or FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "ai_enhancement": dict(payload.get("ai_enhancement") or {}) if isinstance(payload.get("ai_enhancement"), dict) else {},
    }


def _decorate_item(item: Mapping[str, Any], *, decision: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(item.get("payload") or {})
    execution_state = _current_item_execution_state(item, decision=decision)
    result = {
        **dict(item),
        "item_status_label": _mission_status_label(item.get("item_status")),
        "assignment_status_label": _decision_status_label(item.get("assignment_status")),
        "signals": payload.get("signals") or {},
        "why_now": _normalized_text(payload.get("why_now")),
        "title": _normalized_text(payload.get("title")),
        "current_judgement": _normalized_text(payload.get("current_judgement")),
        "suggested_action_type": _normalized_text(payload.get("suggested_action_type")),
        "suggested_action_label": _normalized_text(payload.get("suggested_action_label")),
        "stage_key": _normalized_text(payload.get("stage_key")),
        "stage_label": _normalized_text(payload.get("stage_label")),
        "owner_display_name": _normalized_text(payload.get("owner_display_name")),
        "batchable": bool(payload.get("batchable")),
        "batch_group_key": _normalized_text(payload.get("batch_group_key")),
        "escalation_reason": _normalized_text(payload.get("escalation_reason")),
        "rule_reasons": list(payload.get("rule_reasons") or []),
        "risk_flags": list(payload.get("risk_flags") or []),
        "opportunity_flags": list(payload.get("opportunity_flags") or []),
        "draft_blocked_by_ai": bool(payload.get("draft_blocked_by_ai")),
        "ai_draft_suggestion": dict(payload.get("ai_draft_suggestion") or {}) if isinstance(payload.get("ai_draft_suggestion"), dict) else {},
        "execution_state": execution_state,
        "execution_state_label": _execution_state_label(execution_state),
        "handoff_packet": dict(payload.get("handoff_packet") or {}) if isinstance(payload.get("handoff_packet"), dict) else {},
        "latest_pulse_execution": dict(payload.get("latest_pulse_execution") or {}) if isinstance(payload.get("latest_pulse_execution"), dict) else {},
        "latest_pulse_result": dict(payload.get("latest_pulse_result") or {}) if isinstance(payload.get("latest_pulse_result"), dict) else {},
        "active_assignee_userid": _normalized_text(payload.get("active_assignee_userid")) or _normalized_text(item.get("suggested_assignee_userid")),
        "decision": dict(decision or {}),
    }
    return result


def _sync_scope_label(read_scope: Mapping[str, Any], requested_scope: str) -> str:
    if _normalized_text(requested_scope) == "mine":
        actor_userid = _normalized_text(read_scope.get("actor_userid"))
        return actor_userid or "我的任务包"
    allowed_owner_userids = [_normalized_text(item) for item in (read_scope.get("allowed_owner_userids") or []) if _normalized_text(item)]
    if allowed_owner_userids:
        return f"团队({len(allowed_owner_userids)}人)"
    return "团队"


def sync_followup_orchestrator_missions(
    *,
    scope: str = "team",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 50,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    gate = followup_orchestrator_feature_gate_summary(context)
    if not gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
            "feature_gate": gate,
            "missions": [],
            "mission_items": [],
        }
    requested_scope = _normalized_text(scope) or "team"
    requested_owner_userid = _normalized_text(owner_userid)
    if requested_scope == "mine":
        requested_owner_userid = _normalized_text(context.get("actor_userid") or context.get("user_id")) or requested_owner_userid
    read_scope = resolve_customer_pulse_read_scope(
        requested_owner_userid=requested_owner_userid,
        access_context=context,
    )
    tenant_key = _normalized_text(read_scope.get("tenant_key"))
    scope_key = _normalized_text(read_scope.get("owner_userid_filter")) if requested_scope == "mine" else _sync_scope_label(read_scope, requested_scope)
    pulse_payload = build_customer_pulse_inbox_payload(
        limit=max(1, min(int(limit or 50), FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS)),
        owner_userid=_normalized_text(read_scope.get("owner_userid_filter")),
        external_userid=_normalized_text(external_userid),
        operator=_normalized_text(read_scope.get("operator")),
        scope="all",
        track_metrics=False,
        metric_source="followup_orchestrator_sync",
        tenant_context=read_scope.get("tenant_context"),
        tenant_key=tenant_key,
        allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
    )
    cards = [dict(item) for item in (pulse_payload.get("cards") or []) if isinstance(item, dict)]
    owner_workload = _build_owner_workload(cards)
    owner_workload_map = {
        _normalized_text(item.get("owner_userid")): item
        for item in owner_workload
        if _normalized_text(item.get("owner_userid"))
    }
    team_candidates = _team_candidate_owners(read_scope, owner_workload)
    untreated_counts = repo.list_followup_orchestrator_unresolved_counts(
        tenant_key=tenant_key,
        external_userids=[_normalized_text(card.get("external_userid")) for card in cards],
    )
    signals_by_card_id: dict[int, dict[str, Any]] = {}
    batch_group_sizes: dict[str, int] = {}
    for card in cards:
        card_id = int(card.get("id") or 0)
        signals = _card_signals(
            card,
            owner_workload_map=owner_workload_map,
            team_candidates=team_candidates,
            untreated_counts=untreated_counts,
        )
        signals_by_card_id[card_id] = signals
        if bool(signals.get("batchable")):
            group_key = _batch_group_key(card, signals)
            batch_group_sizes[group_key] = int(batch_group_sizes.get(group_key) or 0) + 1

    mission_specs: dict[str, dict[str, Any]] = {}
    persisted_items: list[dict[str, Any]] = []
    persisted_decisions: list[dict[str, Any]] = []
    can_view_all = bool(read_scope.get("can_view_all"))
    for card in sorted(cards, key=lambda item: -float((signals_by_card_id.get(int(item.get("id") or 0)) or {}).get("schedule_score") or 0)):
        card_id = int(card.get("id") or 0)
        signals = dict(signals_by_card_id.get(card_id) or {})
        assignment = _determine_assignment(card, signals, can_view_all=can_view_all)
        escalation = _escalation_reason(card, signals)
        mission_type = _mission_type_for_card(
            card,
            signals,
            batch_group_sizes=batch_group_sizes,
            can_view_all=can_view_all,
        )
        mission_key = _mission_key_for_card(
            card,
            signals,
            mission_type=mission_type,
            scope_key=_sha_token(scope_key or "team", length=10) or "team",
            assignment=assignment,
        )
        existing_mission = repo.get_followup_orchestrator_mission_by_key(mission_key, tenant_key=tenant_key) or {}
        stable_mission_status = _stable_mission_status(existing_mission)
        batch_group_key = _batch_group_key(card, signals)
        mission_entry = mission_specs.setdefault(
            mission_key,
            {
                "mission_key": mission_key,
                "mission_type": mission_type,
                "mission_status": stable_mission_status or ("unassigned" if mission_type == "claim_queue" else "suggested"),
                "owner_userid": _normalized_text(assignment.get("suggested_assignee_userid")) if mission_type in {"claim_queue", "handoff_wave"} else _normalized_text(card.get("owner_userid")),
                "team_scope_key": scope_key,
                "source_type": FOLLOWUP_ORCHESTRATOR_SOURCE_TYPE,
                "summary": "",
                "priority_score": 0.0,
                "item_count": 0,
                "requires_manager_approval": False,
                "payload_cards": [],
                "payload_signals": [],
                "payload_assignments": [],
                "payload_escalations": [],
                "batch_group_key": batch_group_key if mission_type == "batch_draft_wave" else "",
                "created_by": _normalized_text(read_scope.get("operator")) or "system",
                "items": [],
            },
        )
        mission_entry["payload_cards"].append(card)
        mission_entry["payload_signals"].append(signals)
        if _normalized_text(assignment.get("decision_type")):
            mission_entry["payload_assignments"].append(
                {
                    "card_id": card_id,
                    "external_userid": _normalized_text(card.get("external_userid")),
                    "decision_type": _normalized_text(assignment.get("decision_type")),
                    "current_owner_userid": _normalized_text(card.get("owner_userid")),
                    "suggested_owner_userid": _normalized_text(assignment.get("suggested_assignee_userid")),
                    "reason": _normalized_text(assignment.get("reason")),
                    "needs_manager_approval": bool(assignment.get("needs_manager_approval")),
                    "confidence": float(assignment.get("confidence") or 0),
                }
            )
        if bool(escalation.get("needs_escalation")):
            mission_entry["payload_escalations"].append(
                {
                    "card_id": card_id,
                    "external_userid": _normalized_text(card.get("external_userid")),
                    "reason": _normalized_text(escalation.get("reason")),
                    "confidence": float(escalation.get("confidence") or 0),
                }
            )
        mission_entry["priority_score"] = max(float(mission_entry["priority_score"] or 0), float(signals.get("schedule_score") or 0))
        mission_entry["item_count"] = int(mission_entry["item_count"] or 0) + 1
        mission_entry["requires_manager_approval"] = bool(mission_entry["requires_manager_approval"]) or bool(assignment.get("needs_manager_approval"))
        existing_item = repo.get_followup_orchestrator_mission_item_by_key(f"mission-item:card:{card_id}", tenant_key=tenant_key) or {}
        stable_item_status = _stable_item_status(existing_item)
        item_status = stable_item_status or ("unassigned" if mission_type == "claim_queue" else "suggested")
        assignment_status = _normalized_text(existing_item.get("assignment_status"))
        if not assignment_status:
            if _normalized_text(assignment.get("decision_type")):
                assignment_status = "suggested"
            else:
                assignment_status = "kept"
        existing_payload = dict(existing_item.get("payload") or {})
        payload = {
            **existing_payload,
            "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
            "title": _normalized_text(card.get("title")),
            "why_now": _normalized_text(card.get("why_now")),
            "current_judgement": _normalized_text(card.get("current_judgement") or card.get("summary")),
            "suggested_action_type": _normalized_text(card.get("suggested_action_type")),
            "suggested_action_label": _normalized_text(card.get("suggested_action_label")),
            "priority_score": round(float(card.get("priority_score") or 0), 2),
            "schedule_score": round(float(signals.get("schedule_score") or 0), 2),
            "signals": signals,
            "rule_reasons": list(signals.get("rule_reasons") or []),
            "stage_key": _normalized_text(card.get("stage_key")),
            "stage_label": _normalized_text(card.get("stage_label")),
            "owner_display_name": _normalized_text(card.get("owner_display_name")),
            "risk_flags": list(card.get("risk_flags") or []),
            "opportunity_flags": list(card.get("opportunity_flags") or []),
            "draft_blocked_by_ai": bool(card.get("draft_blocked_by_ai")),
            "batchable": bool(signals.get("batchable")),
            "batch_group_key": batch_group_key if mission_type == "batch_draft_wave" else "",
            "escalation_reason": _normalized_text(escalation.get("reason")),
            "mission_type": mission_type,
        }
        mission_entry["items"].append(
            {
                "mission_item_key": f"mission-item:card:{card_id}",
                "item_status": item_status,
                "assignment_status": assignment_status,
                "external_userid": _normalized_text(card.get("external_userid")),
                "customer_name": _normalized_text(card.get("customer_name")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
                "suggested_assignee_userid": _normalized_text(assignment.get("suggested_assignee_userid")),
                "pulse_card_id": card_id,
                "pulse_snapshot_id": int((card.get("snapshot") or {}).get("id") or 0),
                "payload": payload,
                "evidence_refs": list(card.get("evidence_refs") or []),
                "decision_type": _normalized_text(assignment.get("decision_type")),
                "decision_status": _normalized_text(existing_item.get("assignment_status")) if _normalized_text(existing_item.get("assignment_status")) in {"accepted", "approved", "rejected"} else ("suggested" if _normalized_text(assignment.get("decision_type")) else ""),
                "decision_reason": _normalized_text(assignment.get("reason")),
                "needs_manager_approval": bool(assignment.get("needs_manager_approval")),
            }
        )

    persisted_missions: list[dict[str, Any]] = []
    for mission_spec in mission_specs.values():
        mission_spec["summary"] = _mission_summary(
            _normalized_text(mission_spec.get("mission_type")),
            item_count=int(mission_spec.get("item_count") or 0),
            scope_label=scope_key,
        )
        mission_spec["payload"] = _mission_payload(
            _normalized_text(mission_spec.get("mission_type")),
            cards=list(mission_spec.get("payload_cards") or []),
            signals=list(mission_spec.get("payload_signals") or []),
            assignment_suggestions=list(mission_spec.get("payload_assignments") or []),
            escalation_suggestions=list(mission_spec.get("payload_escalations") or []),
            batch_group_key=_normalized_text(mission_spec.get("batch_group_key")),
            scope_key=scope_key,
        )
        persisted_mission = repo.upsert_followup_orchestrator_mission(
            tenant_key=tenant_key,
            mission_key=_normalized_text(mission_spec.get("mission_key")),
            mission_type=_normalized_text(mission_spec.get("mission_type")),
            mission_status=_normalized_text(mission_spec.get("mission_status")),
            owner_userid=_normalized_text(mission_spec.get("owner_userid")),
            team_scope_key=_normalized_text(mission_spec.get("team_scope_key")),
            source_type=FOLLOWUP_ORCHESTRATOR_SOURCE_TYPE,
            summary=_normalized_text(mission_spec.get("summary")),
            priority_score=float(mission_spec.get("priority_score") or 0),
            item_count=int(mission_spec.get("item_count") or 0),
            requires_manager_approval=bool(mission_spec.get("requires_manager_approval")),
            payload=mission_spec.get("payload") or {},
            created_by=_normalized_text(mission_spec.get("created_by")),
        )
        active_item_keys: list[str] = []
        mission_items_for_summary: list[dict[str, Any]] = []
        decisions_for_summary: list[dict[str, Any]] = []
        for item_spec in mission_spec.get("items") or []:
            if not isinstance(item_spec, dict):
                continue
            active_item_keys.append(_normalized_text(item_spec.get("mission_item_key")))
            persisted_item = repo.upsert_followup_orchestrator_mission_item(
                tenant_key=tenant_key,
                mission_id=int(persisted_mission.get("id") or 0),
                mission_item_key=_normalized_text(item_spec.get("mission_item_key")),
                item_status=_normalized_text(item_spec.get("item_status")),
                assignment_status=_normalized_text(item_spec.get("assignment_status")),
                external_userid=_normalized_text(item_spec.get("external_userid")),
                customer_name=_normalized_text(item_spec.get("customer_name")),
                owner_userid=_normalized_text(item_spec.get("owner_userid")),
                suggested_assignee_userid=_normalized_text(item_spec.get("suggested_assignee_userid")),
                pulse_card_id=int(item_spec.get("pulse_card_id") or 0) or None,
                pulse_snapshot_id=int(item_spec.get("pulse_snapshot_id") or 0) or None,
                payload=item_spec.get("payload") or {},
                evidence_refs=item_spec.get("evidence_refs") or [],
            )
            persisted_items.append(persisted_item)
            mission_items_for_summary.append(persisted_item)
            decision_type = _normalized_text(item_spec.get("decision_type"))
            if decision_type:
                persisted_decision = repo.upsert_followup_orchestrator_assignment_decision(
                    tenant_key=tenant_key,
                    mission_id=int(persisted_mission.get("id") or 0),
                    mission_item_id=int(persisted_item.get("id") or 0),
                    decision_type=decision_type,
                    decision_status=_normalized_text(item_spec.get("decision_status")) or "suggested",
                    current_owner_userid=_normalized_text(item_spec.get("owner_userid")),
                    suggested_owner_userid=_normalized_text(item_spec.get("suggested_assignee_userid")),
                    payload={
                        "reason": _normalized_text(item_spec.get("decision_reason")),
                        "needs_manager_approval": bool(item_spec.get("needs_manager_approval")),
                    },
                )
                persisted_decisions.append(persisted_decision)
                decisions_for_summary.append(persisted_decision)
        repo.mark_followup_orchestrator_missing_items_stale(
            mission_id=int(persisted_mission.get("id") or 0),
            tenant_key=tenant_key,
            active_item_keys=active_item_keys,
        )
        refreshed_items = repo.list_followup_orchestrator_mission_items(
            tenant_key=tenant_key,
            mission_id=int(persisted_mission.get("id") or 0),
            limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
        )
        refreshed_status, refreshed_count = _summarize_mission_items(refreshed_items)
        if _stable_mission_status(persisted_mission):
            refreshed_status = _normalized_text(persisted_mission.get("mission_status"))
        persisted_mission = repo.update_followup_orchestrator_mission(
            int(persisted_mission.get("id") or 0),
            tenant_key=tenant_key,
            mission_status=refreshed_status,
            item_count=refreshed_count,
        )
        persisted_missions.append(persisted_mission)

    mission_detail_map: dict[str, dict[str, Any]] = {}
    for mission in persisted_missions:
        mission_id = int(mission.get("id") or 0)
        items = repo.list_followup_orchestrator_mission_items(
            tenant_key=tenant_key,
            mission_id=mission_id,
            limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
        )
        decisions = repo.list_followup_orchestrator_assignment_decisions(
            tenant_key=tenant_key,
            mission_id=mission_id,
            limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
        )
        decision_map = {
            int(item.get("mission_item_id") or 0): item
            for item in decisions
            if int(item.get("mission_item_id") or 0) > 0
        }
        decorated_items = [_decorate_item(item, decision=decision_map.get(int(item.get("id") or 0))) for item in items]
        mission_logs = repo.list_followup_orchestrator_execution_logs(
            tenant_key=tenant_key,
            mission_id=mission_id,
            limit=50,
        )
        mission_detail_map[_normalized_text(mission.get("mission_key"))] = _decorate_mission(
            mission,
            items=decorated_items,
            decisions=decisions,
            logs=mission_logs,
        )

    return {
        "enabled": True,
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "feature_gate": gate,
        "tenant_context": customer_pulse_tenant_context_summary(context),
        "access": customer_pulse_template_access_payload(context),
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "rules": dict(FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS),
        "filters": {
            "scope": requested_scope,
            "owner_userid": _normalized_text(read_scope.get("owner_userid_filter")) if requested_scope == "mine" else requested_owner_userid,
            "external_userid": _normalized_text(external_userid),
        },
        "owner_workload": owner_workload,
        "team_candidate_count": len(team_candidates),
        "cards": cards,
        "missions": [mission_detail_map[_normalized_text(mission.get("mission_key"))] for mission in persisted_missions if _normalized_text(mission.get("mission_key")) in mission_detail_map],
        "mission_items": persisted_items,
        "decisions": persisted_decisions,
    }


def build_followup_orchestrator_overview_payload(
    *,
    scope: str = "team",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    gate = followup_orchestrator_feature_gate_summary(context)
    if not gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
            "feature_gate": gate,
            "missions": [],
            "mission_items": [],
        }
    synced = sync_followup_orchestrator_missions(
        scope=scope,
        owner_userid=owner_userid,
        external_userid=external_userid,
        limit=limit,
        access_context=context,
    ) if auto_sync else {
        "enabled": True,
        "feature_gate": gate,
        "tenant_context": customer_pulse_tenant_context_summary(context),
        "access": customer_pulse_template_access_payload(context),
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "rules": dict(FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS),
        "cards": [],
        "missions": [],
        "mission_items": [],
        "owner_workload": [],
        "team_candidate_count": 0,
        "filters": {"scope": _normalized_text(scope) or "team", "owner_userid": _normalized_text(owner_userid), "external_userid": _normalized_text(external_userid)},
    }
    synced_missions = synced.get("missions")
    synced_items = synced.get("mission_items")
    synced_cards = synced.get("cards")
    missions = [dict(item) for item in synced_missions if isinstance(item, dict)] if isinstance(synced_missions, list) else []
    missions = [_apply_mission_ai_if_enabled(item, access_context=context) for item in missions]
    mission_items = [dict(item) for item in synced_items if isinstance(item, dict)] if isinstance(synced_items, list) else []
    card_count = len(synced_cards) if isinstance(synced_cards, list) else 0
    assignment_suggestions: list[dict[str, Any]] = []
    escalation_suggestions: list[dict[str, Any]] = []
    batch_draft_suggestions: list[dict[str, Any]] = []
    mission_candidates: list[dict[str, Any]] = []
    for mission in missions:
        payload = dict(mission.get("payload") or {})
        ai_enhancement = dict(mission.get("ai_enhancement") or {}) if isinstance(mission.get("ai_enhancement"), dict) else {}
        ai_recommendation = dict(ai_enhancement.get("recommendation") or {}) if isinstance(ai_enhancement.get("recommendation"), dict) else {}
        mission_candidates.append(
            {
                "mission_key": _normalized_text(mission.get("mission_key")),
                "mission_type": _normalized_text(mission.get("mission_type")),
                "mission_status": _normalized_text(mission.get("mission_status")),
                "mission_status_label": _mission_status_label(mission.get("mission_status")),
                "title": _normalized_text(mission.get("title")) or _mission_title(_normalized_text(mission.get("mission_type"))),
                "summary": _normalized_text(mission.get("summary")),
                "item_count": int(mission.get("item_count") or 0),
                "priority_score": round(float(mission.get("priority_score") or 0), 2),
                "reason": _normalized_text(ai_recommendation.get("missionSummary")) or _normalized_text(mission.get("summary")),
                "confidence": round(float(ai_recommendation.get("confidence") or 0), 4),
                "evidence_refs": list(ai_recommendation.get("evidenceRefs") or payload.get("evidence_refs") or []),
                "assignment_why": _normalized_text(mission.get("assignment_why")),
                "escalation_why": _normalized_text(mission.get("escalation_why")),
                "handoff_summary": _normalized_text(mission.get("handoff_summary")),
                "ai_enhancement": ai_enhancement,
                "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
                "customer_items": [
                    {
                        "card_id": int((item.get("payload") or {}).get("pulse_card_id") or item.get("pulse_card_id") or 0),
                        "external_userid": _normalized_text(item.get("external_userid")),
                        "customer_name": _normalized_text(item.get("customer_name")),
                        "owner_userid": _normalized_text(item.get("owner_userid")),
                        "owner_display_name": _normalized_text((item.get("payload") or {}).get("owner_display_name")),
                        "why_now": _normalized_text((item.get("payload") or {}).get("why_now")),
                        "suggested_action_type": _normalized_text((item.get("payload") or {}).get("suggested_action_type")),
                        "suggested_action_label": _normalized_text((item.get("payload") or {}).get("suggested_action_label")),
                        "ai_draft_suggestion": dict(item.get("ai_draft_suggestion") or {}) if isinstance(item.get("ai_draft_suggestion"), dict) else {},
                    }
                    for item in (mission.get("items") or [])[:5]
                    if isinstance(item, dict)
                ],
            }
        )
        for assignment in payload.get("assignment_suggestions") or []:
            if isinstance(assignment, dict):
                assignment_suggestions.append(dict(assignment))
        for escalation in payload.get("escalation_suggestions") or []:
            if isinstance(escalation, dict):
                escalation_suggestions.append(dict(escalation))
        if _normalized_text(mission.get("mission_type")) == "batch_draft_wave":
            batch_draft_suggestions.append(
                {
                    "batch_key": _normalized_text(mission.get("mission_key")),
                    "title": _normalized_text(mission.get("title")) or _mission_title("batch_draft_wave"),
                    "item_count": int(mission.get("item_count") or 0),
                    "reason": _normalized_text(mission.get("summary")),
                    "confidence": round(float(ai_recommendation.get("confidence") or 0), 4),
                    "evidence_refs": list(ai_recommendation.get("evidenceRefs") or payload.get("evidence_refs") or []),
                    "ai_enhancement": ai_enhancement,
                    "cards": [
                        {
                            "card_id": int(item.get("pulse_card_id") or 0),
                            "external_userid": _normalized_text(item.get("external_userid")),
                            "customer_name": _normalized_text(item.get("customer_name")),
                            "owner_userid": _normalized_text(item.get("owner_userid")),
                            "why_now": _normalized_text(item.get("why_now")),
                            "ai_draft_suggestion": dict(item.get("ai_draft_suggestion") or {}) if isinstance(item.get("ai_draft_suggestion"), dict) else {},
                        }
                        for item in (mission.get("items") or [])
                        if isinstance(item, dict)
                    ],
                }
            )
    return {
        "enabled": True,
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "feature_gate": synced.get("feature_gate") or gate,
        "tenant_context": synced.get("tenant_context"),
        "access": synced.get("access"),
        "filters": synced.get("filters") or {},
        "states": list(FOLLOWUP_ORCHESTRATOR_MISSION_STATES),
        "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "rules": dict(FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS),
        "summary_cards": [
            {"key": "open_action_cards", "label": "可编排卡片", "value": card_count, "description": "来自 customer_pulse action cards"},
            {"key": "mission_candidates", "label": "任务包", "value": len(missions), "description": "按优先级、认领、转派、升级和成批规则生成"},
            {"key": "assignment_suggestions", "label": "转派建议", "value": len(assignment_suggestions), "description": "owner 过载时优先建议接力"},
            {"key": "batch_draft_suggestions", "label": "批量草稿建议", "value": len(batch_draft_suggestions), "description": "仅对低风险且同模板的回复类卡片生效"},
        ],
        "owner_workload": synced.get("owner_workload") or [],
        "mission_candidates": mission_candidates,
        "missions": missions,
        "mission_items": mission_items,
        "stored_mission_items": mission_items,
        "assignment_suggestions": assignment_suggestions,
        "escalation_suggestions": escalation_suggestions,
        "batch_draft_suggestions": batch_draft_suggestions,
        "team_candidate_count": _safe_int(synced.get("team_candidate_count"), default=0),
        "reused_capabilities": [
            "customer_pulse_cards",
            "pulse_snapshots",
            "tenant_scoped_access",
            "customer_pulse_rbac",
            "customer_pulse_audit",
            "customer_pulse_execution_log",
            "customer_pulse_activity_writeback",
        ],
    }


def build_followup_orchestrator_customer_payload(
    *,
    external_userid: str,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    overview = build_followup_orchestrator_overview_payload(
        scope="team",
        external_userid=external_userid,
        limit=50,
        access_context=access_context,
    )
    if not overview.get("enabled"):
        return overview
    mission_items = [
        item
        for item in (overview.get("mission_items") or [])
        if _normalized_text((item or {}).get("external_userid")) == _normalized_text(external_userid)
    ]
    assignment_suggestions = [
        item
        for item in (overview.get("assignment_suggestions") or [])
        if _normalized_text((item or {}).get("external_userid")) == _normalized_text(external_userid)
    ]
    escalation_suggestions = [
        item
        for item in (overview.get("escalation_suggestions") or [])
        if _normalized_text((item or {}).get("external_userid")) == _normalized_text(external_userid)
    ]
    batch_draft_suggestions = []
    for suggestion in overview.get("batch_draft_suggestions") or []:
        if not isinstance(suggestion, dict):
            continue
        if any(_normalized_text((card or {}).get("external_userid")) == _normalized_text(external_userid) for card in (suggestion.get("cards") or [])):
            batch_draft_suggestions.append(dict(suggestion))
    return {
        "enabled": True,
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "feature_gate": overview.get("feature_gate"),
        "tenant_context": overview.get("tenant_context"),
        "access": overview.get("access"),
        "external_userid": _normalized_text(external_userid),
        "mission_items": mission_items,
        "assignment_suggestions": assignment_suggestions,
        "escalation_suggestions": escalation_suggestions,
        "batch_draft_suggestions": batch_draft_suggestions,
        "states": list(FOLLOWUP_ORCHESTRATOR_MISSION_STATES),
        "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
    }


def build_followup_orchestrator_my_missions_payload(
    *,
    actor_userid: str,
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    overview = build_followup_orchestrator_overview_payload(
        scope="team",
        limit=limit,
        auto_sync=auto_sync,
        access_context=context,
    )
    if not overview.get("enabled"):
        return overview
    tenant_key = _normalized_text((overview.get("tenant_context") or {}).get("tenant_key"))
    actor_value = _normalized_text(actor_userid) or _normalized_text(context.get("actor_userid") or context.get("user_id"))
    missions = repo.list_followup_orchestrator_missions_for_actor(
        tenant_key=tenant_key,
        actor_userid=actor_value,
        limit=limit,
    )
    mission_details = [get_followup_orchestrator_mission_detail_payload(mission_key=_normalized_text(item.get("mission_key")), access_context=context, tenant_key=tenant_key) for item in missions]
    return {
        **overview,
        "missions": [item for item in mission_details if item],
        "actor_userid": actor_value,
        "filters": {
            **dict(overview.get("filters") or {}),
            "scope": "mine",
            "owner_userid": actor_value,
        },
    }


def build_followup_orchestrator_team_board_payload(
    *,
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return build_followup_orchestrator_overview_payload(
        scope="team",
        limit=limit,
        auto_sync=auto_sync,
        access_context=access_context,
    )


def get_followup_orchestrator_mission_detail_payload(
    *,
    mission_key: str,
    access_context: Mapping[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    read_scope = _resolved_followup_read_scope(access_context=access_context)
    context = _feature_gate_context(access_context)
    resolved_tenant_key = _normalized_text(tenant_key) or _normalized_text(read_scope.get("tenant_key")) or _normalized_text(context.get("tenant_key")) or "aicrm"
    mission = repo.get_followup_orchestrator_mission_by_key(_normalized_text(mission_key), tenant_key=resolved_tenant_key)
    if not mission:
        raise LookupError("mission not found")
    items = repo.list_followup_orchestrator_mission_items(
        tenant_key=resolved_tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    _assert_mission_items_accessible(items, read_scope=read_scope)
    decisions = repo.list_followup_orchestrator_assignment_decisions(
        tenant_key=resolved_tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    decision_map = {
        int(item.get("mission_item_id") or 0): item
        for item in decisions
        if int(item.get("mission_item_id") or 0) > 0
    }
    decorated_items = [_decorate_item(item, decision=decision_map.get(int(item.get("id") or 0))) for item in items]
    logs = repo.list_followup_orchestrator_execution_logs(
        tenant_key=resolved_tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=50,
    )
    return _apply_mission_ai_if_enabled(
        _decorate_mission(mission, items=decorated_items, decisions=decisions, logs=logs),
        access_context=context,
    )


def _resolved_mission_item_context(
    *,
    mission_key: str,
    mission_item_key: str,
    access_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    read_scope = _resolved_followup_read_scope(access_context=access_context)
    context = _feature_gate_context(access_context)
    tenant_key = _normalized_text(read_scope.get("tenant_key")) or _normalized_text(context.get("tenant_key")) or "aicrm"
    mission = repo.get_followup_orchestrator_mission_by_key(_normalized_text(mission_key), tenant_key=tenant_key)
    if not mission:
        raise LookupError("mission not found")
    item = repo.get_followup_orchestrator_mission_item_by_key(_normalized_text(mission_item_key), tenant_key=tenant_key)
    if not item or int(item.get("mission_id") or 0) != int(mission.get("id") or 0):
        raise LookupError("mission item not found")
    _assert_mission_items_accessible([item], read_scope=read_scope)
    decision = repo.get_followup_orchestrator_assignment_decision_for_item(
        mission_item_id=int(item.get("id") or 0),
        tenant_key=tenant_key,
    ) or {}
    return context, tenant_key, mission, item, decision, read_scope


def _executor_execution_state(action_type: str) -> str:
    if _normalized_text(action_type) == "generate_reply_draft":
        return "draft_ready"
    return "executed"


def _undo_restored_item_status(item: Mapping[str, Any], decision: Mapping[str, Any] | None) -> str:
    current_status = _normalized_text(item.get("item_status"))
    if current_status in {"accepted", "approved", "suggested", "unassigned"}:
        return current_status
    decision_status = _normalized_text((decision or {}).get("decision_status"))
    if decision_status == "approved":
        return "approved"
    if decision_status in {"accepted", "completed"}:
        return "accepted"
    if _normalized_text(item.get("owner_userid")) or _normalized_text(item.get("suggested_assignee_userid")):
        return "accepted"
    return "suggested"


def preview_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    action_type: str = "",
    actor_userid: str = "",
    operator: str = "",
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context, tenant_key, mission, item, decision, _read_scope = _resolved_mission_item_context(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )
    resolved_action_type = _normalized_text(action_type) or _normalized_text((item.get("payload") or {}).get("suggested_action_type"))
    if resolved_action_type not in FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES:
        raise ValueError("unsupported executor action_type")
    if int(item.get("pulse_card_id") or 0) <= 0:
        raise ValueError("mission item is not linked to customer_pulse card")
    preview = preview_customer_pulse_card_action(
        int(item.get("pulse_card_id") or 0),
        action_type=resolved_action_type,
        track_click=False,
        operator=_normalized_text(operator),
        tenant_context=dict(context or {}),
        tenant_key=tenant_key,
    )
    return {
        "mission_key": _normalized_text(mission.get("mission_key")),
        "mission_item_key": _normalized_text(item.get("mission_item_key")),
        "tenant_context": customer_pulse_tenant_context_summary(context),
        "actor_userid": _normalized_text(actor_userid) or _normalized_text(context.get("actor_userid") or context.get("user_id")),
        "preview": preview,
        "item": _decorate_item(item, decision=decision),
    }


def _execute_followup_orchestrator_item_action(
    *,
    mission: Mapping[str, Any],
    item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    action_type: str,
    actor_userid: str,
    actor_role: str,
    operator: str,
    note: str,
    extra_payload: Mapping[str, Any] | None,
    tenant_context: Mapping[str, Any] | None,
    tenant_key: str,
) -> dict[str, Any]:
    if int(item.get("pulse_card_id") or 0) <= 0:
        raise ValueError("mission item is not linked to customer_pulse card")
    execution_response = execute_customer_pulse_card_action(
        int(item.get("pulse_card_id") or 0),
        action_type=_normalized_text(action_type),
        operator=_normalized_text(operator),
        extra_payload=dict(extra_payload or {}),
        tenant_context=dict(tenant_context or {}),
        tenant_key=tenant_key,
    )
    pulse_execution = dict(execution_response.get("execution") or {})
    pulse_result = dict(execution_response.get("result") or {})
    payload = _with_item_runtime_payload(
        dict(item.get("payload") or {}),
        execution_state=_executor_execution_state(action_type),
        latest_pulse_execution=pulse_execution,
        latest_pulse_result=pulse_result,
        latest_pulse_action_type=_normalized_text(action_type),
        latest_pulse_execution_id=int(pulse_execution.get("id") or 0),
        latest_pulse_activity_log_id=int(
            pulse_execution.get("activity_log_id")
            or pulse_result.get("activity_log_id")
            or 0
        ),
        active_assignee_userid=_normalized_text(actor_userid) or _normalized_text(item.get("suggested_assignee_userid")) or _normalized_text(item.get("owner_userid")),
    )
    updated_item = repo.update_followup_orchestrator_mission_item(
        int(item.get("id") or 0),
        tenant_key=tenant_key,
        item_status="executing",
        assignment_status=_normalized_text(item.get("assignment_status")) or "accepted",
        payload_json=payload,
    )
    updated_decision = {}
    if decision:
        next_decision_status = _normalized_text(decision.get("decision_status"))
        if next_decision_status in {"", "suggested", "approved"}:
            next_decision_status = "accepted"
        updated_decision = repo.update_followup_orchestrator_assignment_decision(
            int(decision.get("id") or 0),
            tenant_key=tenant_key,
            decision_status=next_decision_status or "accepted",
            decided_by_userid=_normalized_text(actor_userid),
            payload_json={
                **dict(decision.get("payload") or {}),
                "last_executor_action_type": _normalized_text(action_type),
                "last_executor_execution_id": int(pulse_execution.get("id") or 0),
            },
        )
    orchestrator_log = repo.insert_followup_orchestrator_execution_log(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        mission_item_id=int(updated_item.get("id") or 0),
        action_type=f"execute_{_normalized_text(action_type)}",
        execution_status=_normalized_text(pulse_execution.get("execution_status")) or "confirmed",
        operator=_normalized_text(operator),
        actor_userid=_normalized_text(actor_userid),
        actor_role=_normalized_text(actor_role),
        resource_type="followup_orchestrator_mission_item",
        resource_id=_normalized_text(item.get("mission_item_key")),
        tenant_context=tenant_context,
        request_payload={
            "action_type": _normalized_text(action_type),
            "note": _normalized_text(note),
            "extra_payload": dict(extra_payload or {}),
        },
        result_payload={
            "execution_state": _executor_execution_state(action_type),
            "pulse_execution": pulse_execution,
            "pulse_result": pulse_result,
        },
        error_message="",
    )
    return {
        "item": updated_item,
        "decision": updated_decision,
        "pulse_execution": pulse_execution,
        "pulse_result": pulse_result,
        "orchestrator_log": orchestrator_log,
    }


def execute_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    action_type: str = "",
    actor_userid: str,
    actor_role: str,
    operator: str,
    note: str = "",
    extra_payload: Mapping[str, Any] | None = None,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context, tenant_key, mission, item, decision, _read_scope = _resolved_mission_item_context(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )
    resolved_action_type = _normalized_text(action_type) or _normalized_text((item.get("payload") or {}).get("suggested_action_type"))
    if resolved_action_type not in FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES:
        raise ValueError("unsupported executor action_type")
    execution_result = _execute_followup_orchestrator_item_action(
        mission=mission,
        item=item,
        decision=decision,
        action_type=resolved_action_type,
        actor_userid=actor_userid,
        actor_role=actor_role,
        operator=operator,
        note=note,
        extra_payload=extra_payload,
        tenant_context=context,
        tenant_key=tenant_key,
    )
    return {
        "mission": get_followup_orchestrator_mission_detail_payload(
            mission_key=_normalized_text(mission.get("mission_key")),
            access_context=context,
            tenant_key=tenant_key,
        ),
        "mission_item_key": _normalized_text(mission_item_key),
        "action_type": resolved_action_type,
        **execution_result,
    }


def undo_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    execution_id: int = 0,
    actor_userid: str,
    actor_role: str,
    operator: str,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context, tenant_key, mission, item, decision, _read_scope = _resolved_mission_item_context(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )
    payload = dict(item.get("payload") or {})
    resolved_execution_id = int(execution_id or payload.get("latest_pulse_execution_id") or ((payload.get("latest_pulse_execution") or {}).get("id") or 0))
    if resolved_execution_id <= 0:
        raise ValueError("missing execution_id")
    undo_result = undo_customer_pulse_card_action_execution(
        resolved_execution_id,
        operator=_normalized_text(operator),
        tenant_context=dict(context or {}),
        tenant_key=tenant_key,
    )
    next_execution_state = "pending_approval" if bool(((decision or {}).get("payload") or {}).get("needs_manager_approval")) and _normalized_text((decision or {}).get("decision_status")) in {"", "suggested"} else "not_started"
    updated_item = repo.update_followup_orchestrator_mission_item(
        int(item.get("id") or 0),
        tenant_key=tenant_key,
        item_status=_undo_restored_item_status(item, decision=decision),
        payload_json=_with_item_runtime_payload(
            payload,
            execution_state=next_execution_state,
            latest_pulse_execution=dict(undo_result.get("execution") or {}),
            latest_pulse_result=dict(undo_result or {}),
            latest_pulse_execution_id=int((undo_result.get("execution") or {}).get("id") or 0),
            latest_pulse_activity_log_id=int((undo_result.get("undo_activity") or {}).get("id") or 0),
            latest_pulse_action_type=_normalized_text((undo_result.get("execution") or {}).get("action_type")),
        ),
    )
    orchestrator_log = repo.insert_followup_orchestrator_execution_log(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        mission_item_id=int(updated_item.get("id") or 0),
        action_type="undo_customer_pulse_execution",
        execution_status="undone",
        operator=_normalized_text(operator),
        actor_userid=_normalized_text(actor_userid),
        actor_role=_normalized_text(actor_role),
        resource_type="followup_orchestrator_mission_item",
        resource_id=_normalized_text(item.get("mission_item_key")),
        tenant_context=context,
        request_payload={"execution_id": resolved_execution_id},
        result_payload=undo_result,
        error_message="",
    )
    return {
        "mission": get_followup_orchestrator_mission_detail_payload(
            mission_key=_normalized_text(mission.get("mission_key")),
            access_context=context,
            tenant_key=tenant_key,
        ),
        "mission_item_key": _normalized_text(mission_item_key),
        "execution": dict(undo_result.get("execution") or {}),
        "undo_result": undo_result,
        "orchestrator_log": orchestrator_log,
    }


def apply_followup_orchestrator_mission_action(
    *,
    mission_key: str,
    action_type: str,
    actor_userid: str,
    actor_role: str,
    operator: str,
    tenant_context: Mapping[str, Any] | None = None,
    mission_item_key: str = "",
    note: str = "",
) -> dict[str, Any]:
    context = dict(tenant_context or {})
    read_scope = _resolved_followup_read_scope(access_context=context)
    tenant_key = _normalized_text(read_scope.get("tenant_key")) or _normalized_text(context.get("tenant_key")) or "aicrm"
    mission = repo.get_followup_orchestrator_mission_by_key(_normalized_text(mission_key), tenant_key=tenant_key)
    if not mission:
        raise LookupError("mission not found")
    items = repo.list_followup_orchestrator_mission_items(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    target_items = items
    normalized_item_key = _normalized_text(mission_item_key)
    if normalized_item_key:
        target_items = [item for item in items if _normalized_text(item.get("mission_item_key")) == normalized_item_key]
        if not target_items:
            raise LookupError("mission item not found")
    normalized_action = _normalized_text(action_type)
    if normalized_action not in FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS:
        raise ValueError("unsupported action_type")
    _assert_mission_items_accessible(target_items, read_scope=read_scope, action_type=normalized_action)
    updated_items: list[dict[str, Any]] = []
    updated_decisions: list[dict[str, Any]] = []
    batch_execution_results: list[dict[str, Any]] = []
    for item in target_items:
        next_item_status = _normalized_text(item.get("item_status"))
        next_assignment_status = _normalized_text(item.get("assignment_status"))
        decision = repo.get_followup_orchestrator_assignment_decision_for_item(
            mission_item_id=int(item.get("id") or 0),
            tenant_key=tenant_key,
        )
        decision_update: dict[str, Any] = {}
        payload = dict(item.get("payload") or {})
        if normalized_action in {"accept", "claim"}:
            next_item_status = "accepted"
            next_assignment_status = "accepted" if decision else next_assignment_status or "accepted"
            payload = _with_item_runtime_payload(
                payload,
                execution_state="not_started",
                active_assignee_userid=_normalized_text(actor_userid) or _normalized_text(item.get("suggested_assignee_userid")) or _normalized_text(item.get("owner_userid")),
            )
            decision_update = {"decision_status": "accepted", "decided_by_userid": _normalized_text(actor_userid)}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type=f"orchestrator_{normalized_action}",
                activity_status="accepted",
                title="已接受团队任务包" if normalized_action == "accept" else "已认领客户项",
                summary=_normalized_text(note) or ("当前客户项已由负责人接手处理。" if normalized_action == "accept" else "当前客户项已由团队成员认领。"),
                payload={"mission_key": _normalized_text(mission.get("mission_key")), "mission_item_key": _normalized_text(item.get("mission_item_key"))},
            )
        elif normalized_action == "request_manager_approval":
            next_item_status = "approved"
            next_assignment_status = "approved" if decision else next_assignment_status or "approved"
            handoff_packet = _build_handoff_packet(
                mission=mission,
                item=_decorate_item({**dict(item), "payload": payload}, decision=decision),
                decision={
                    **dict(decision or {}),
                    "decision_status": "approved",
                    "payload": {**dict((decision or {}).get("payload") or {}), "needs_manager_approval": bool(((decision or {}).get("payload") or {}).get("needs_manager_approval"))},
                },
                tenant_context=context,
                tenant_key=tenant_key,
            )
            payload = _with_item_runtime_payload(
                payload,
                execution_state="executed",
                handoff_packet=handoff_packet,
                active_assignee_userid=_normalized_text(item.get("suggested_assignee_userid")) or _normalized_text(item.get("owner_userid")),
            )
            decision_update = {
                "decision_status": "approved",
                "approved_by_userid": _normalized_text(actor_userid),
                "payload_json": {
                    **dict((decision or {}).get("payload") or {}),
                    "handoff_packet": handoff_packet,
                },
            }
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_handoff_approved",
                activity_status="completed",
                title="已批准转派接力",
                summary=_normalized_text(note) or "经理已批准当前客户项的接力建议，已生成 handoff packet。",
                payload={"handoff_packet": handoff_packet, "mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "escalate":
            next_item_status = "escalated"
            next_assignment_status = "approved" if decision else next_assignment_status or "approved"
            payload["manual_escalation_note"] = _normalized_text(note) or "用户手动触发升级"
            payload = _with_item_runtime_payload(payload, execution_state="escalated")
            decision_update = {"decision_status": "approved", "approved_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_escalation",
                activity_status="completed",
                title="已升级处理",
                summary=_normalized_text(note) or "当前客户项已升级处理。",
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "complete":
            next_item_status = "completed"
            next_assignment_status = "completed" if decision else next_assignment_status or "completed"
            payload["completed_note"] = _normalized_text(note) or "用户标记为已完成"
            payload = _with_item_runtime_payload(payload, execution_state="completed")
            decision_update = {"decision_status": "completed", "decided_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_completed",
                activity_status="completed",
                title="已完成团队任务项",
                summary=_normalized_text(note) or "当前客户项已完成。",
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "prebuild_batch_draft":
            try:
                execution_result = _execute_followup_orchestrator_item_action(
                    mission=mission,
                    item=item,
                    decision=decision,
                    action_type="generate_reply_draft",
                    actor_userid=actor_userid,
                    actor_role=actor_role,
                    operator=operator,
                    note=note,
                    extra_payload={},
                    tenant_context=context,
                    tenant_key=tenant_key,
                )
                updated_items.append(execution_result["item"])
                if execution_result.get("decision"):
                    updated_decisions.append(execution_result["decision"])
                batch_execution_results.append(
                    {
                        "mission_item_key": _normalized_text(item.get("mission_item_key")),
                        "external_userid": _normalized_text(item.get("external_userid")),
                        "status": "success",
                        "pulse_execution_id": int((execution_result.get("pulse_execution") or {}).get("id") or 0),
                        "activity_log_id": int(((execution_result.get("pulse_result") or {}).get("activity_log_id") or 0)),
                    }
                )
            except Exception as exc:
                failed_payload = {
                    **payload,
                    "batch_draft_prebuild_requested": True,
                    "last_batch_error": str(exc),
                }
                failed_item = repo.update_followup_orchestrator_mission_item(
                    int(item.get("id") or 0),
                    tenant_key=tenant_key,
                    item_status=_normalized_text(item.get("item_status")) or "accepted",
                    assignment_status=_normalized_text(item.get("assignment_status")) or "accepted",
                    payload_json=failed_payload,
                )
                updated_items.append(failed_item)
                batch_execution_results.append(
                    {
                        "mission_item_key": _normalized_text(item.get("mission_item_key")),
                        "external_userid": _normalized_text(item.get("external_userid")),
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                repo.insert_followup_orchestrator_execution_log(
                    tenant_key=tenant_key,
                    mission_id=int(mission.get("id") or 0),
                    mission_item_id=int(item.get("id") or 0),
                    action_type="execute_generate_reply_draft",
                    execution_status="failed",
                    operator=_normalized_text(operator),
                    actor_userid=_normalized_text(actor_userid),
                    actor_role=_normalized_text(actor_role),
                    resource_type="followup_orchestrator_mission_item",
                    resource_id=_normalized_text(item.get("mission_item_key")),
                    tenant_context=context,
                    request_payload={"action_type": "generate_reply_draft", "note": _normalized_text(note)},
                    result_payload={"error": str(exc)},
                    error_message=str(exc),
                )
            continue
        elif normalized_action in FOLLOWUP_ORCHESTRATOR_REJECTABLE_ACTIONS:
            next_item_status = "skipped"
            next_assignment_status = "rejected" if decision else next_assignment_status or "rejected"
            payload["skip_reason"] = _normalized_text(note) or normalized_action
            payload = _with_item_runtime_payload(payload, execution_state="skipped")
            decision_update = {"decision_status": "rejected", "decided_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type=f"orchestrator_{normalized_action}",
                activity_status="completed",
                title="已标记阻塞" if normalized_action == "mark_blocked" else "已跳过客户项",
                summary=_normalized_text(note) or ("当前客户项已标记阻塞。" if normalized_action == "mark_blocked" else "当前客户项已跳过。"),
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "suggest_assignment":
            payload = _with_item_runtime_payload(payload, execution_state="pending_approval")
            decision_update = {"decision_status": "suggested", "decided_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_assignment_suggested",
                activity_status="pending",
                title="已建议转派接力",
                summary=_normalized_text(note) or "当前客户项已提出转派接力建议，等待审批。",
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        updated_item = repo.update_followup_orchestrator_mission_item(
            int(item.get("id") or 0),
            tenant_key=tenant_key,
            item_status=next_item_status,
            assignment_status=next_assignment_status,
            payload_json=payload,
        )
        updated_items.append(updated_item)
        if decision:
            updated_decision = repo.update_followup_orchestrator_assignment_decision(
                int(decision.get("id") or 0),
                tenant_key=tenant_key,
                **decision_update,
            )
            updated_decisions.append(updated_decision)
        repo.insert_followup_orchestrator_execution_log(
            tenant_key=tenant_key,
            mission_id=int(mission.get("id") or 0),
            mission_item_id=int(item.get("id") or 0),
            action_type=normalized_action,
            execution_status="accepted" if normalized_action in {"accept", "claim", "request_manager_approval"} else next_item_status,
            operator=_normalized_text(operator),
            actor_userid=_normalized_text(actor_userid),
            actor_role=_normalized_text(actor_role),
            resource_type="followup_orchestrator_mission_item",
            resource_id=_normalized_text(item.get("mission_item_key")),
            tenant_context=context,
            request_payload={"note": _normalized_text(note), "action_type": normalized_action},
            result_payload={"item_status": next_item_status, "assignment_status": next_assignment_status},
        )
    refreshed_items = repo.list_followup_orchestrator_mission_items(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    refreshed_status, refreshed_count = _summarize_mission_items(refreshed_items)
    if _stable_mission_status(mission) and normalized_action not in {"accept", "claim", "request_manager_approval", "prebuild_batch_draft"}:
        refreshed_status = _normalized_text(mission.get("mission_status"))
    refreshed_mission = repo.update_followup_orchestrator_mission(
        int(mission.get("id") or 0),
        tenant_key=tenant_key,
        mission_status=refreshed_status,
        item_count=refreshed_count,
        payload_json={
            **dict(mission.get("payload") or {}),
            "last_action_note": _normalized_text(note),
            "last_action_type": normalized_action,
            "last_action_results": batch_execution_results if batch_execution_results else [],
        },
    )
    return {
        "mission": get_followup_orchestrator_mission_detail_payload(
            mission_key=_normalized_text(refreshed_mission.get("mission_key")),
            tenant_key=tenant_key,
            access_context=context,
        ),
        "updated_items": updated_items,
        "updated_decisions": updated_decisions,
    }
