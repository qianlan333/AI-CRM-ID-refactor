from __future__ import annotations

import json
from typing import Any

from ...db import get_db
from ..user_ops import page_service as user_ops_page_service
from . import workflow_repo
from .agents.registry import CHILD_AGENT_CONFIG_DEFINITIONS
from .workflow_definitions import (
    AGENT_POOL_BINDING_SCOPE_BEHAVIOR_TIER,
    AGENT_POOL_BINDING_SCOPE_DEFAULT,
    AGENT_POOL_BINDING_SCOPE_PERSONALIZED,
    AGENT_POOL_BINDING_SCOPE_PROFILE_CATEGORY,
    AGENT_POOL_TYPE_PERSONALIZED,
    AGENT_POOL_TYPE_REPLY,
    AGENT_POOL_TYPE_REWRITE,
    AGENT_POOL_TYPE_SHARED,
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    GENERATION_MODE_AUTO_LAYERED_REWRITE,
    GENERATION_MODE_MANUAL_LAYERED,
    GENERATION_MODE_PERSONALIZED_SINGLE,
    NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
    NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER,
    NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY,
    NODE_TRIGGER_MODE_SCHEDULED,
    SEGMENTATION_BASIS_BEHAVIOR,
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    WORKFLOW_STATUS_ACTIVE,
    WORKFLOW_STATUS_DRAFT,
    WORKFLOW_STATUS_PAUSED,
    list_supported_agent_pool_binding_scopes,
    list_supported_agent_pool_types,
    list_supported_behavior_tiers,
    list_supported_conversion_audiences,
    list_supported_generation_modes,
    list_supported_node_content_variant_scopes,
    list_supported_node_trigger_modes,
    list_supported_segmentation_bases,
    list_supported_workflow_statuses,
)

_ALLOWED_AUDIENCES = {
    AUDIENCE_PENDING_QUESTIONNAIRE,
    AUDIENCE_OPERATING,
    AUDIENCE_CONVERTED,
}
_ALLOWED_SEGMENTATION_BASES = {
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    SEGMENTATION_BASIS_BEHAVIOR,
}
_ALLOWED_GENERATION_MODES = {
    GENERATION_MODE_MANUAL_LAYERED,
    GENERATION_MODE_AUTO_LAYERED_REWRITE,
    GENERATION_MODE_PERSONALIZED_SINGLE,
}
_ALLOWED_WORKFLOW_STATUSES = {
    WORKFLOW_STATUS_DRAFT,
    WORKFLOW_STATUS_ACTIVE,
    WORKFLOW_STATUS_PAUSED,
}
_ALLOWED_NODE_TRIGGER_MODES = {
    NODE_TRIGGER_MODE_SCHEDULED,
    NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
}
_ALLOWED_POOL_TYPES = {
    AGENT_POOL_TYPE_SHARED,
    AGENT_POOL_TYPE_REPLY,
    AGENT_POOL_TYPE_REWRITE,
    AGENT_POOL_TYPE_PERSONALIZED,
}

_LEGACY_REPLY_POOL_LABELS = {
    "new_user": "新用户应答池",
    "inactive_normal": "未激活普通应答池",
    "inactive_focus": "未激活重点应答池",
    "active_normal": "活跃普通应答池",
    "active_focus": "活跃重点应答池",
    "silent": "沉默用户应答池",
    "won": "已成交应答池",
    "no_reply": "无需回复池",
    "human_reply": "人工接管池",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _normalized_text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(result, minimum)
    return result


def _truncate_text(value: Any, *, limit: int = 120) -> str:
    text = _normalized_text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _slugify_code(value: Any, *, prefix: str) -> str:
    raw = _normalized_text(value).lower().replace(" ", "_").replace("-", "_")
    safe = "".join(char if (char.isalnum() or char == "_") else "_" for char in raw)
    compact = "_".join(part for part in safe.split("_") if part)
    return compact or prefix


def _json_fingerprint(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _behavior_tier_codes() -> list[str]:
    return [str(item["tier_code"]) for item in list_supported_behavior_tiers()]


def _behavior_tier_map() -> dict[str, dict[str, Any]]:
    return {str(item["tier_code"]): dict(item) for item in list_supported_behavior_tiers()}


def _workflow_status_to_enabled(status: str) -> bool:
    return _normalized_text(status) == WORKFLOW_STATUS_ACTIVE


def _validate_send_time(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) != 5 or text[2] != ":":
        raise ValueError("send_time must be HH:MM")
    hour_text, minute_text = text.split(":", 1)
    if not hour_text.isdigit() or not minute_text.isdigit():
        raise ValueError("send_time must be HH:MM")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("send_time must be HH:MM")
    return f"{hour:02d}:{minute:02d}"


def _validate_node_trigger_mode(value: Any) -> str:
    normalized = _normalized_text(value) or NODE_TRIGGER_MODE_SCHEDULED
    if normalized not in _ALLOWED_NODE_TRIGGER_MODES:
        raise ValueError("trigger_mode must be one of scheduled, audience_entered")
    return normalized


def _normalize_agent_members_payload(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_agent_codes: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError("agents item must be an object")
        agent_code = _normalized_text(item.get("agent_code"))
        if not agent_code:
            raise ValueError("agent_code is required")
        if agent_code in seen_agent_codes:
            raise ValueError(f"duplicate agent_code: {agent_code}")
        seen_agent_codes.add(agent_code)
        role_code = _normalized_text(item.get("role_code")) or "primary"
        if role_code not in {"primary", "fallback", "supporting"}:
            raise ValueError("role_code must be one of primary, fallback, supporting")
        normalized.append(
            {
                "agent_code": agent_code,
                "role_code": role_code,
                "position_index": _normalize_int(item.get("position_index"), default=index - 1, minimum=0),
            }
        )
    return normalized


def _normalize_template_categories_payload(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_category_keys: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError("category must be an object")
        category_key = _slugify_code(item.get("category_key") or item.get("key") or item.get("category_name"), prefix=f"category_{index}")
        if category_key in seen_category_keys:
            raise ValueError(f"duplicate category_key: {category_key}")
        seen_category_keys.add(category_key)
        category_name = _normalized_text(item.get("category_name") or item.get("name"))
        if not category_name:
            raise ValueError("category_name is required")
        raw_option_ids = item.get("option_ids")
        if raw_option_ids is None:
            raw_option_ids = [mapping.get("option_id") for mapping in item.get("option_mappings") or [] if isinstance(mapping, dict)]
        if not isinstance(raw_option_ids or [], list):
            raise ValueError("option_ids must be an array")
        option_ids: list[int] = []
        seen_option_ids: set[int] = set()
        for option_id in raw_option_ids or []:
            normalized_option_id = _normalize_int(option_id, default=0, minimum=1)
            if normalized_option_id <= 0:
                raise ValueError("option_id must be a positive integer")
            if normalized_option_id in seen_option_ids:
                continue
            seen_option_ids.add(normalized_option_id)
            option_ids.append(normalized_option_id)
        normalized.append(
            {
                "category_key": category_key,
                "category_name": category_name,
                "description": _normalized_text(item.get("description")),
                "sort_order": _normalize_int(item.get("sort_order"), default=index, minimum=0),
                "enabled": _normalize_bool(item.get("enabled"), default=True),
                "option_ids": option_ids,
            }
        )
    return normalized


def _normalize_workflow_audiences(payload: Any) -> list[str]:
    items = payload if isinstance(payload, list) else []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        audience_code = _normalized_text(item.get("audience_code") if isinstance(item, dict) else item)
        if not audience_code:
            continue
        if audience_code not in _ALLOWED_AUDIENCES:
            raise ValueError(f"invalid audience_code: {audience_code}")
        if audience_code in seen:
            continue
        seen.add(audience_code)
        normalized.append(audience_code)
    if not normalized:
        raise ValueError("audiences is required")
    return normalized


def _resolve_agent_pool_reference(payload: dict[str, Any]) -> dict[str, Any]:
    pool_id = _normalize_int(payload.get("agent_pool_id"), default=0, minimum=0)
    pool_code = _normalized_text(payload.get("pool_code"))
    pool = workflow_repo.get_agent_pool_row(pool_id) if pool_id > 0 else None
    if not pool and pool_code:
        pool = workflow_repo.get_agent_pool_row_by_code(pool_code)
    if not pool:
        raise LookupError("agent pool not found")
    return pool


def _normalize_workflow_agent_pool_bindings(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_scope_keys: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("agent_pool_bindings item must be an object")
        pool = _resolve_agent_pool_reference(item)
        binding_scope = _normalized_text(item.get("binding_scope")) or AGENT_POOL_BINDING_SCOPE_DEFAULT
        if binding_scope not in {
            AGENT_POOL_BINDING_SCOPE_DEFAULT,
            AGENT_POOL_BINDING_SCOPE_PROFILE_CATEGORY,
            AGENT_POOL_BINDING_SCOPE_BEHAVIOR_TIER,
            AGENT_POOL_BINDING_SCOPE_PERSONALIZED,
        }:
            raise ValueError("invalid binding_scope")
        segment_key = _normalized_text(item.get("segment_key"))
        identity = (binding_scope, segment_key)
        if identity in seen_scope_keys:
            raise ValueError(f"duplicate binding for {binding_scope}:{segment_key}")
        seen_scope_keys.add(identity)
        normalized.append(
            {
                "agent_pool_id": int(pool["id"]),
                "pool_code": _normalized_text(pool.get("pool_code")),
                "pool_type": _normalized_text(pool.get("pool_type")),
                "binding_scope": binding_scope,
                "segment_key": segment_key,
            }
        )
    return normalized


def _normalize_node_variants_payload(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_segment_keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("content_variants item must be an object")
        segment_key = _normalized_text(item.get("segment_key"))
        if not segment_key:
            raise ValueError("content_variants.segment_key is required")
        if segment_key in seen_segment_keys:
            raise ValueError(f"duplicate content_variants.segment_key: {segment_key}")
        seen_segment_keys.add(segment_key)
        normalized.append(
            {
                "segment_key": segment_key,
                "content_text": _normalized_text(item.get("content_text")),
                "content_payload_json": dict(item.get("content_payload_json") or item.get("content_payload") or {}),
            }
        )
    return normalized


def _validate_agent_members(agent_members: list[dict[str, Any]]) -> None:
    available_codes = set(workflow_repo.list_agent_config_codes())
    for item in agent_members:
        if item["agent_code"] not in available_codes:
            raise ValueError(f"invalid agent_code: {item['agent_code']}")


def _validate_segmentation_question(questionnaire_id: int, question_id: int, categories: list[dict[str, Any]]) -> dict[str, Any]:
    questionnaire = workflow_repo.get_questionnaire_row(questionnaire_id)
    if not questionnaire:
        raise LookupError("questionnaire not found")
    question = workflow_repo.get_questionnaire_question_row(questionnaire_id, question_id)
    if not question:
        raise LookupError("segmentation question not found")
    question_type = _normalized_text(question.get("type"))
    if question_type not in {"single_choice", "multi_choice"}:
        raise ValueError("segmentation question must be single_choice or multi_choice")
    options = workflow_repo.list_questionnaire_option_rows(question_id)
    option_map = {int(item["id"]): dict(item) for item in options}
    used_option_ids: dict[int, str] = {}
    for category in categories:
        for option_id in category["option_ids"]:
            if option_id not in option_map:
                raise ValueError(f"invalid option_id for selected question: {option_id}")
            if option_id in used_option_ids:
                raise ValueError(f"option_id {option_id} is already mapped to category {used_option_ids[option_id]}")
            used_option_ids[option_id] = category["category_key"]
    return {
        "questionnaire": questionnaire,
        "question": question,
        "options": options,
    }


def _serialize_agent_pool(pool: dict[str, Any], agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    agent_items = []
    for item in agents or []:
        agent_items.append(
            {
                "agent_code": _normalized_text(item.get("agent_code")),
                "agent_name": _normalized_text(item.get("agent_display_name")) or _normalized_text(item.get("display_name")),
                "role_code": _normalized_text(item.get("role_code")) or "primary",
                "position_index": int(item.get("position_index") or 0),
            }
        )
    return {
        "id": int(pool.get("id") or 0),
        "pool_code": _normalized_text(pool.get("pool_code")),
        "pool_name": _normalized_text(pool.get("display_name")),
        "display_name": _normalized_text(pool.get("display_name")),
        "pool_type": _normalized_text(pool.get("pool_type")) or AGENT_POOL_TYPE_SHARED,
        "description": _normalized_text(pool.get("description")),
        "status": "enabled" if bool(pool.get("enabled")) else "disabled",
        "enabled": bool(pool.get("enabled")),
        "updated_at": _normalized_text(pool.get("updated_at")),
        "created_at": _normalized_text(pool.get("created_at")),
        "agents": agent_items,
    }


def _serialize_profile_segment_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(template.get("id") or 0),
        "template_code": _normalized_text(template.get("template_code")),
        "template_name": _normalized_text(template.get("template_name")),
        "questionnaire_id": int(template.get("questionnaire_id") or 0) or None,
        "segmentation_question_id": int(template.get("segmentation_question_id") or 0) or None,
        "description": _normalized_text(template.get("description")),
        "enabled": bool(template.get("enabled")),
        "status": "enabled" if bool(template.get("enabled")) else "disabled",
        "version": int(template.get("version") or 1),
        "updated_at": _normalized_text(template.get("updated_at")),
        "created_at": _normalized_text(template.get("created_at")),
    }


def _build_agent_pool_bundle(pool: dict[str, Any]) -> dict[str, Any]:
    return _serialize_agent_pool(pool, workflow_repo.list_agent_pool_agent_rows(int(pool["id"])))


def _build_questionnaire_catalog_item(questionnaire: dict[str, Any]) -> dict[str, Any]:
    questionnaire_id = int(questionnaire.get("id") or 0)
    question_items: list[dict[str, Any]] = []
    for question in workflow_repo.list_questionnaire_question_rows(questionnaire_id):
        option_rows = workflow_repo.list_questionnaire_option_rows(int(question["id"]))
        question_items.append(
            {
                "id": int(question["id"]),
                "title": _normalized_text(question.get("title")),
                "type": _normalized_text(question.get("type")),
                "sort_order": int(question.get("sort_order") or 0),
                "options": [
                    {
                        "id": int(option["id"]),
                        "option_text": _normalized_text(option.get("option_text")),
                        "sort_order": int(option.get("sort_order") or 0),
                    }
                    for option in option_rows
                ],
            }
        )
    return {
        "id": questionnaire_id,
        "name": _normalized_text(questionnaire.get("title")) or _normalized_text(questionnaire.get("name")),
        "slug": _normalized_text(questionnaire.get("slug")),
        "questions": question_items,
    }


def list_conversion_profile_segment_catalog() -> dict[str, Any]:
    items = [_build_questionnaire_catalog_item(row) for row in workflow_repo.list_questionnaire_rows()]
    return {"items": items, "total": len(items)}


def _build_profile_segment_template_bundle(template: dict[str, Any]) -> dict[str, Any]:
    template_id = int(template["id"])
    questionnaire_id = int(template.get("questionnaire_id") or 0)
    question_id = int(template.get("segmentation_question_id") or 0)
    questionnaire = workflow_repo.get_questionnaire_row(questionnaire_id) if questionnaire_id else None
    question = workflow_repo.get_questionnaire_question_row(questionnaire_id, question_id) if questionnaire_id and question_id else None
    options = workflow_repo.list_questionnaire_option_rows(question_id) if question_id else []
    option_map = {int(item["id"]): dict(item) for item in options}
    categories = workflow_repo.list_profile_segment_category_rows(template_id)
    mappings = workflow_repo.list_profile_segment_option_mapping_rows(template_id)
    mappings_by_category: dict[int, list[dict[str, Any]]] = {}
    option_ids_by_category: dict[int, list[int]] = {}
    for mapping in mappings:
        category_id = int(mapping["category_id"])
        option_snapshot = option_map.get(int(mapping["option_id"])) or {}
        enriched_mapping = {
            "id": int(mapping["id"]),
            "question_id": int(mapping["question_id"]),
            "option_id": int(mapping["option_id"]),
            "option": {
                "id": int(option_snapshot.get("id") or 0),
                "option_text": _normalized_text(option_snapshot.get("option_text")),
                "sort_order": int(option_snapshot.get("sort_order") or 0),
            },
        }
        mappings_by_category.setdefault(category_id, []).append(enriched_mapping)
        option_ids_by_category.setdefault(category_id, []).append(int(mapping["option_id"]))
    category_items = [
        {
            "id": int(category["id"]),
            "category_key": _normalized_text(category.get("category_key")),
            "category_name": _normalized_text(category.get("category_name")),
            "description": _normalized_text(category.get("description")),
            "sort_order": int(category.get("sort_order") or 0),
            "enabled": bool(category.get("enabled")),
            "option_ids": option_ids_by_category.get(int(category["id"]), []),
            "option_mappings": mappings_by_category.get(int(category["id"]), []),
        }
        for category in categories
    ]
    return {
        "template": _serialize_profile_segment_template(template),
        "questionnaire": {
            "id": int((questionnaire or {}).get("id") or 0) or None,
            "name": _normalized_text((questionnaire or {}).get("title")) or _normalized_text((questionnaire or {}).get("name")),
            "slug": _normalized_text((questionnaire or {}).get("slug")),
        },
        "segmentation_question": {
            "id": int((question or {}).get("id") or 0) or None,
            "title": _normalized_text((question or {}).get("title")),
            "type": _normalized_text((question or {}).get("type")),
            "sort_order": int((question or {}).get("sort_order") or 0),
        },
        "question_options": [
            {
                "id": int(item["id"]),
                "option_text": _normalized_text(item.get("option_text")),
                "sort_order": int(item.get("sort_order") or 0),
            }
            for item in options
        ],
        "categories": category_items,
        "supports_standard_fallback": True,
    }


def _extract_bundle_categories(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "category_key": _normalized_text(item.get("category_key")),
            "category_name": _normalized_text(item.get("category_name")),
            "description": _normalized_text(item.get("description")),
            "sort_order": _normalize_int(item.get("sort_order"), default=index, minimum=0),
            "enabled": _normalize_bool(item.get("enabled"), default=True),
            "option_ids": [_normalize_int(option_id, default=0, minimum=1) for option_id in item.get("option_ids") or []],
        }
        for index, item in enumerate(bundle.get("categories") or [], start=1)
    ]


def _sync_agent_pool_agents(agent_pool_id: int, agent_members: list[dict[str, Any]]) -> None:
    workflow_repo.delete_agent_pool_agent_rows(agent_pool_id)
    for item in agent_members:
        workflow_repo.insert_agent_pool_agent_row({"agent_pool_id": int(agent_pool_id), **item})


def _sync_profile_template_categories(template_id: int, question_id: int, categories: list[dict[str, Any]]) -> None:
    workflow_repo.delete_profile_segment_option_mapping_rows(template_id)
    workflow_repo.delete_profile_segment_category_rows(template_id)
    for category in categories:
        saved_category = workflow_repo.insert_profile_segment_category_row(
            {
                "template_id": int(template_id),
                "category_key": category["category_key"],
                "category_name": category["category_name"],
                "description": category["description"],
                "sort_order": category["sort_order"],
                "enabled": category["enabled"],
            }
        )
        for option_id in category["option_ids"]:
            workflow_repo.insert_profile_segment_option_mapping_row(
                {
                    "template_id": int(template_id),
                    "category_id": int(saved_category["id"]),
                    "question_id": int(question_id),
                    "option_id": int(option_id),
                }
            )


def _workflow_expected_binding_targets(
    *,
    segmentation_basis: str,
    generation_mode: str,
    profile_segment_template_id: int | None,
) -> dict[str, Any]:
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        return {"binding_scope": AGENT_POOL_BINDING_SCOPE_DEFAULT, "segment_keys": []}
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return {"binding_scope": AGENT_POOL_BINDING_SCOPE_PERSONALIZED, "segment_keys": ["personalized"]}
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        template = get_conversion_profile_segment_template_bundle(int(profile_segment_template_id or 0))
        category_keys = [
            _normalized_text(item.get("category_key"))
            for item in template.get("categories") or []
            if bool(item.get("enabled"))
        ]
        return {"binding_scope": AGENT_POOL_BINDING_SCOPE_PROFILE_CATEGORY, "segment_keys": category_keys}
    if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR:
        return {"binding_scope": AGENT_POOL_BINDING_SCOPE_BEHAVIOR_TIER, "segment_keys": _behavior_tier_codes()}
    raise ValueError("auto_layered_rewrite requires segmentation_basis profile or behavior")


def _validate_workflow_agent_pool_bindings(
    *,
    segmentation_basis: str,
    generation_mode: str,
    profile_segment_template_id: int | None,
    bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        if bindings:
            raise ValueError("manual_layered does not allow agent_pool_bindings")
        return []
    expected = _workflow_expected_binding_targets(
        segmentation_basis=segmentation_basis,
        generation_mode=generation_mode,
        profile_segment_template_id=profile_segment_template_id,
    )
    binding_scope = expected["binding_scope"]
    expected_keys = list(expected["segment_keys"])
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        if len(bindings) != 1:
            raise ValueError("personalized_single requires exactly 1 agent_pool_binding")
    else:
        if len(bindings) != len(expected_keys):
            raise ValueError("agent_pool_bindings does not match expected segmentation targets")
    resolved_by_key: dict[str, dict[str, Any]] = {}
    for item in bindings:
        item_scope = _normalized_text(item.get("binding_scope")) or binding_scope
        segment_key = _normalized_text(item.get("segment_key"))
        if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
            segment_key = "personalized"
            item_scope = AGENT_POOL_BINDING_SCOPE_PERSONALIZED
        if item_scope != binding_scope:
            raise ValueError("invalid binding_scope for workflow generation_mode")
        if generation_mode != GENERATION_MODE_PERSONALIZED_SINGLE and segment_key not in expected_keys:
            raise ValueError(f"unexpected binding segment_key: {segment_key}")
        pool_type = _normalized_text(item.get("pool_type")) or AGENT_POOL_TYPE_SHARED
        if generation_mode == GENERATION_MODE_AUTO_LAYERED_REWRITE and pool_type not in {AGENT_POOL_TYPE_REWRITE, AGENT_POOL_TYPE_SHARED}:
            raise ValueError("auto_layered_rewrite only accepts rewrite/shared agent pools")
        if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE and pool_type not in {AGENT_POOL_TYPE_PERSONALIZED, AGENT_POOL_TYPE_SHARED}:
            raise ValueError("personalized_single only accepts personalized/shared agent pools")
        resolved_by_key[segment_key] = {
            "agent_pool_id": int(item["agent_pool_id"]),
            "binding_scope": item_scope,
            "segment_key": segment_key if generation_mode != GENERATION_MODE_PERSONALIZED_SINGLE else "",
        }
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        only_item = next(iter(resolved_by_key.values()))
        return [only_item]
    if set(resolved_by_key.keys()) != set(expected_keys):
        raise ValueError("agent_pool_bindings must cover every segmentation target")
    return [resolved_by_key[key] for key in expected_keys]


def _normalize_workflow_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(payload or {})
    current = dict(existing or {})
    workflow_name = _normalized_text(source.get("workflow_name") or current.get("workflow_name"))
    if not workflow_name:
        raise ValueError("workflow_name is required")
    workflow_code = _slugify_code(source.get("workflow_code") or current.get("workflow_code") or workflow_name, prefix="workflow")
    audiences = _normalize_workflow_audiences(source.get("audiences") if "audiences" in source else [item.get("audience_code") for item in current.get("audiences") or []])
    segmentation_basis = _normalized_text(source.get("segmentation_basis") or current.get("segmentation_basis")) or SEGMENTATION_BASIS_NONE
    if segmentation_basis not in _ALLOWED_SEGMENTATION_BASES:
        raise ValueError("invalid segmentation_basis")
    generation_mode = _normalized_text(source.get("generation_mode") or current.get("generation_mode")) or GENERATION_MODE_MANUAL_LAYERED
    if generation_mode not in _ALLOWED_GENERATION_MODES:
        raise ValueError("invalid generation_mode")
    profile_segment_template_id = _normalize_int(
        source.get("profile_segment_template_id") if "profile_segment_template_id" in source else current.get("profile_segment_template_id"),
        default=0,
        minimum=0,
    ) or None
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        if not profile_segment_template_id:
            raise ValueError("profile_segment_template_id is required for profile segmentation")
        get_conversion_profile_segment_template_bundle(int(profile_segment_template_id))
    else:
        profile_segment_template_id = None
    if generation_mode == GENERATION_MODE_AUTO_LAYERED_REWRITE and segmentation_basis == SEGMENTATION_BASIS_NONE:
        raise ValueError("auto_layered_rewrite requires profile or behavior segmentation")
    bindings_input = source.get("agent_pool_bindings") if "agent_pool_bindings" in source else current.get("agent_pool_bindings") or []
    bindings = _normalize_workflow_agent_pool_bindings(bindings_input)
    normalized_bindings = _validate_workflow_agent_pool_bindings(
        segmentation_basis=segmentation_basis,
        generation_mode=generation_mode,
        profile_segment_template_id=profile_segment_template_id,
        bindings=bindings,
    )
    status = _normalized_text(source.get("status") or current.get("status")) or WORKFLOW_STATUS_DRAFT
    if status not in _ALLOWED_WORKFLOW_STATUSES:
        raise ValueError("invalid workflow status")
    fallback_to_standard_content = _normalize_bool(
        source.get("fallback_to_standard_content"),
        default=_normalize_bool(current.get("fallback_to_standard_content"), default=True),
    )
    return {
        "workflow_code": workflow_code,
        "workflow_name": workflow_name,
        "description": _normalized_text(source.get("description") if "description" in source else current.get("description")),
        "status": status,
        "segmentation_basis": segmentation_basis,
        "generation_mode": generation_mode,
        "profile_segment_template_id": profile_segment_template_id,
        "behavior_tier_scheme": "fixed_v1",
        "fallback_to_standard_content": fallback_to_standard_content,
        "enabled": _workflow_status_to_enabled(status),
        "audiences": audiences,
        "agent_pool_bindings": normalized_bindings,
    }


def _allowed_manual_variant_keys(workflow_bundle: dict[str, Any]) -> tuple[str, list[str]]:
    workflow = dict(workflow_bundle.get("workflow") or {})
    segmentation_basis = _normalized_text(workflow.get("segmentation_basis"))
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        keys = [_normalized_text(item.get("category_key")) for item in (workflow_bundle.get("profile_segment_template") or {}).get("categories") or [] if bool(item.get("enabled"))]
        return NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY, keys
    if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR:
        return NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER, _behavior_tier_codes()
    return "", []


def _build_node_bundle(node: dict[str, Any], workflow_bundle: dict[str, Any]) -> dict[str, Any]:
    content = workflow_repo.get_workflow_node_content_row(int(node["id"])) or {}
    variants = workflow_repo.list_workflow_node_content_variant_rows(int(content["id"])) if content else []
    return {
        "id": int(node["id"]),
        "node_code": _normalized_text(node.get("node_code")),
        "node_name": _normalized_text(node.get("node_name")),
        "target_audience_code": _normalized_text(node.get("target_audience_code")),
        "trigger_mode": _normalized_text(node.get("trigger_mode")) or NODE_TRIGGER_MODE_SCHEDULED,
        "day_offset": int(node.get("day_offset") or 1),
        "send_time": _normalized_text(node.get("send_time")),
        "timezone": _normalized_text(node.get("timezone")) or "Asia/Shanghai",
        "position_index": int(node.get("position_index") or 0),
        "enabled": bool(node.get("enabled")),
        "status": "enabled" if bool(node.get("enabled")) else "disabled",
        "standard_content_text": _normalized_text(content.get("standard_content_text")),
        "standard_content_payload": dict(content.get("standard_content_payload_json") or {}),
        "fallback_to_standard_content": bool(content.get("fallback_to_standard_content")) if content else True,
        "content_variants": [
            {
                "id": int(item["id"]),
                "variant_scope": _normalized_text(item.get("variant_scope")),
                "segment_key": _normalized_text(item.get("segment_key")),
                "content_text": _normalized_text(item.get("content_text")),
                "content_payload": dict(item.get("content_payload_json") or {}),
            }
            for item in variants
        ],
    }


def _build_workflow_bundle(workflow: dict[str, Any]) -> dict[str, Any]:
    workflow_id = int(workflow["id"])
    audiences = workflow_repo.list_workflow_audience_rows(workflow_id)
    bindings = workflow_repo.list_workflow_agent_pool_binding_rows(workflow_id)
    nodes = workflow_repo.list_workflow_node_rows(workflow_id)
    profile_segment_template = (
        get_conversion_profile_segment_template_bundle(int(workflow.get("profile_segment_template_id") or 0))
        if int(workflow.get("profile_segment_template_id") or 0) > 0
        else None
    )
    binding_items = []
    for binding in bindings:
        pool = workflow_repo.get_agent_pool_row(int(binding["agent_pool_id"]))
        if not pool:
            continue
        binding_items.append(
            {
                "id": int(binding["id"]),
                "binding_scope": _normalized_text(binding.get("binding_scope")),
                "segment_key": _normalized_text(binding.get("segment_key")),
                "agent_pool": _serialize_agent_pool(pool, workflow_repo.list_agent_pool_agent_rows(int(pool["id"]))),
            }
        )
    workflow_payload = {
        "id": workflow_id,
        "workflow_code": _normalized_text(workflow.get("workflow_code")),
        "workflow_name": _normalized_text(workflow.get("workflow_name")),
        "description": _normalized_text(workflow.get("description")),
        "status": _normalized_text(workflow.get("status")) or WORKFLOW_STATUS_DRAFT,
        "enabled": bool(workflow.get("enabled")),
        "segmentation_basis": _normalized_text(workflow.get("segmentation_basis")) or SEGMENTATION_BASIS_NONE,
        "generation_mode": _normalized_text(workflow.get("generation_mode")) or GENERATION_MODE_MANUAL_LAYERED,
        "profile_segment_template_id": int(workflow.get("profile_segment_template_id") or 0) or None,
        "behavior_tier_scheme": _normalized_text(workflow.get("behavior_tier_scheme")) or "fixed_v1",
        "fallback_to_standard_content": bool(workflow.get("fallback_to_standard_content")),
        "updated_at": _normalized_text(workflow.get("updated_at")),
        "created_at": _normalized_text(workflow.get("created_at")),
    }
    bundle = {
        "workflow": workflow_payload,
        "audiences": [
            {
                "audience_code": _normalized_text(item.get("audience_code")),
            }
            for item in audiences
        ],
        "profile_segment_template": profile_segment_template,
        "agent_pool_bindings": binding_items,
        "behavior_tiers": list_supported_behavior_tiers() if workflow_payload["segmentation_basis"] == SEGMENTATION_BASIS_BEHAVIOR else [],
    }
    bundle["nodes"] = [_build_node_bundle(node, bundle) for node in nodes]
    return bundle


def _sync_workflow_children(workflow_id: int, payload: dict[str, Any]) -> None:
    workflow_repo.delete_workflow_audience_rows(workflow_id)
    for audience_code in payload["audiences"]:
        workflow_repo.insert_workflow_audience_row({"workflow_id": int(workflow_id), "audience_code": audience_code})
    workflow_repo.delete_workflow_agent_pool_binding_rows(workflow_id)
    for item in payload["agent_pool_bindings"]:
        workflow_repo.insert_workflow_agent_pool_binding_row({"workflow_id": int(workflow_id), **item})


def _normalize_node_payload(payload: dict[str, Any], workflow_bundle: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(payload or {})
    current = dict(existing or {})
    workflow = dict(workflow_bundle.get("workflow") or {})
    node_name = _normalized_text(source.get("node_name") or current.get("node_name"))
    if not node_name:
        raise ValueError("node_name is required")
    node_code = _slugify_code(source.get("node_code") or current.get("node_code") or node_name, prefix="node")
    target_audience_code = _normalized_text(source.get("target_audience_code") or current.get("target_audience_code"))
    if target_audience_code not in [item["audience_code"] for item in workflow_bundle.get("audiences") or []]:
        raise ValueError("target_audience_code must belong to workflow audiences")
    trigger_mode = _validate_node_trigger_mode(
        source.get("trigger_mode") if "trigger_mode" in source else current.get("trigger_mode") or NODE_TRIGGER_MODE_SCHEDULED
    )
    day_offset = _normalize_int(source.get("day_offset") if "day_offset" in source else current.get("day_offset"), default=1, minimum=1)
    send_time = _validate_send_time(source.get("send_time") if "send_time" in source else current.get("send_time") or "09:00")
    if trigger_mode == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        day_offset = 1
        send_time = "00:00"
    standard_content_text = _normalized_text(
        source.get("standard_content_text")
        if "standard_content_text" in source
        else current.get("standard_content_text")
    )
    if not standard_content_text:
        raise ValueError("standard_content_text is required")
    position_index = _normalize_int(
        source.get("position_index") if "position_index" in source else current.get("position_index"),
        default=len(workflow_bundle.get("nodes") or []),
        minimum=0,
    )
    content_variants = _normalize_node_variants_payload(source.get("content_variants") if "content_variants" in source else current.get("content_variants") or [])
    generation_mode = _normalized_text(workflow.get("generation_mode")) or GENERATION_MODE_MANUAL_LAYERED
    variant_scope, allowed_keys = _allowed_manual_variant_keys(workflow_bundle)
    if generation_mode != GENERATION_MODE_MANUAL_LAYERED and content_variants:
        raise ValueError("content_variants is only allowed for manual_layered workflows")
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        if not allowed_keys and content_variants:
            raise ValueError("current workflow segmentation does not allow content_variants")
        for item in content_variants:
            if item["segment_key"] not in allowed_keys:
                raise ValueError(f"invalid content_variants.segment_key: {item['segment_key']}")
    else:
        variant_scope = ""
        content_variants = []
    return {
        "node_code": node_code,
        "node_name": node_name,
        "target_audience_code": target_audience_code,
        "trigger_mode": trigger_mode,
        "day_offset": day_offset,
        "send_time": send_time,
        "timezone": _normalized_text(source.get("timezone") or current.get("timezone") or "Asia/Shanghai"),
        "position_index": position_index,
        "enabled": _normalize_bool(source.get("enabled"), default=_normalize_bool(current.get("enabled"), default=True)),
        "standard_content_text": standard_content_text,
        "standard_content_payload_json": dict(source.get("standard_content_payload") or source.get("standard_content_payload_json") or current.get("standard_content_payload") or {}),
        "fallback_to_standard_content": _normalize_bool(
            source.get("fallback_to_standard_content"),
            default=_normalize_bool(current.get("fallback_to_standard_content"), default=True),
        ),
        "content_variants": [
            {
                "variant_scope": variant_scope,
                **item,
            }
            for item in content_variants
        ],
    }


def _save_node_content(node_id: int, normalized_node: dict[str, Any]) -> None:
    content_row = workflow_repo.get_workflow_node_content_row(node_id)
    if content_row:
        saved_content = workflow_repo.update_workflow_node_content_row(
            node_id,
            {
                "standard_content_text": normalized_node["standard_content_text"],
                "standard_content_payload_json": normalized_node["standard_content_payload_json"],
                "fallback_to_standard_content": normalized_node["fallback_to_standard_content"],
            },
        )
    else:
        saved_content = workflow_repo.insert_workflow_node_content_row(
            {
                "node_id": int(node_id),
                "standard_content_text": normalized_node["standard_content_text"],
                "standard_content_payload_json": normalized_node["standard_content_payload_json"],
                "fallback_to_standard_content": normalized_node["fallback_to_standard_content"],
            }
        )
    workflow_repo.delete_workflow_node_content_variant_rows(int(saved_content["id"]))
    for item in normalized_node["content_variants"]:
        workflow_repo.insert_workflow_node_content_variant_row(
            {
                "node_content_id": int(saved_content["id"]),
                "variant_scope": item["variant_scope"],
                "segment_key": item["segment_key"],
                "content_text": item["content_text"],
                "content_payload_json": item["content_payload_json"],
            }
        )


def ensure_default_conversion_agent_pools() -> None:
    available_codes = set(workflow_repo.list_agent_config_codes())
    legacy_membership: dict[str, list[dict[str, Any]]] = {}
    for definition in CHILD_AGENT_CONFIG_DEFINITIONS:
        agent_code = _normalized_text(definition.get("agent_code"))
        if agent_code not in available_codes:
            continue
        for index, pool_code in enumerate(definition.get("pool_keys") or []):
            normalized_pool_code = _normalized_text(pool_code)
            if not normalized_pool_code:
                continue
            legacy_membership.setdefault(normalized_pool_code, []).append(
                {
                    "agent_code": agent_code,
                    "role_code": "primary",
                    "position_index": index,
                }
            )
    for legacy_pool_code, display_name in _LEGACY_REPLY_POOL_LABELS.items():
        existing = workflow_repo.get_agent_pool_row_by_code(legacy_pool_code)
        base_payload = {
            "pool_code": legacy_pool_code,
            "display_name": display_name,
            "description": "从旧自动化应答 pool_keys 兼容迁移的通用 Agent 池。",
            "pool_type": AGENT_POOL_TYPE_REPLY,
            "enabled": True,
            "created_by": "system",
            "updated_by": "system",
        }
        saved_pool = workflow_repo.update_agent_pool_row(int(existing["id"]), {**base_payload, "enabled": bool(existing.get("enabled", True))}) if existing else workflow_repo.insert_agent_pool_row(base_payload)
        _sync_agent_pool_agents(int(saved_pool["id"]), legacy_membership.get(legacy_pool_code, []))


def list_conversion_workflow_registry() -> dict[str, Any]:
    return {
        "audiences": list_supported_conversion_audiences(),
        "segmentation_bases": list_supported_segmentation_bases(),
        "generation_modes": list_supported_generation_modes(),
        "node_trigger_modes": list_supported_node_trigger_modes(),
        "behavior_tiers": list_supported_behavior_tiers(),
        "agent_pool_types": list_supported_agent_pool_types(),
        "agent_pool_binding_scopes": list_supported_agent_pool_binding_scopes(),
        "node_content_variant_scopes": list_supported_node_content_variant_scopes(),
        "workflow_statuses": list_supported_workflow_statuses(),
    }


def list_conversion_agent_pools(*, enabled_only: bool = False, pool_type: str = "") -> dict[str, Any]:
    ensure_default_conversion_agent_pools()
    pools = workflow_repo.list_agent_pool_rows(enabled_only=enabled_only, pool_type=pool_type)
    items = [_build_agent_pool_bundle(pool) for pool in pools]
    return {"items": items, "total": len(items)}


def get_conversion_agent_pool_bundle(*, agent_pool_id: int | None = None, pool_code: str = "") -> dict[str, Any]:
    ensure_default_conversion_agent_pools()
    pool = workflow_repo.get_agent_pool_row(int(agent_pool_id)) if agent_pool_id is not None else None
    if not pool and pool_code:
        pool = workflow_repo.get_agent_pool_row_by_code(pool_code)
    if not pool:
        raise LookupError("agent pool not found")
    return _build_agent_pool_bundle(pool)


def list_conversion_agent_pools_for_agent(agent_code: str) -> list[dict[str, Any]]:
    pools = workflow_repo.list_agent_pool_rows_for_agent(_normalized_text(agent_code))
    return [_build_agent_pool_bundle(pool) for pool in pools]


def create_conversion_agent_pool(payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    ensure_default_conversion_agent_pools()
    pool_name = _normalized_text(payload.get("pool_name") or payload.get("display_name"))
    pool_code = _slugify_code(payload.get("pool_code") or pool_name, prefix="agent_pool")
    if workflow_repo.get_agent_pool_row_by_code(pool_code):
        raise ValueError("pool_code already exists")
    pool_type = _normalized_text(payload.get("pool_type")) or AGENT_POOL_TYPE_SHARED
    if pool_type not in _ALLOWED_POOL_TYPES:
        raise ValueError("invalid pool_type")
    if not pool_name:
        raise ValueError("pool_name is required")
    agent_members = _normalize_agent_members_payload(payload.get("agents") or [])
    _validate_agent_members(agent_members)
    saved_pool = workflow_repo.insert_agent_pool_row(
        {
            "pool_code": pool_code,
            "display_name": pool_name,
            "description": _normalized_text(payload.get("description")),
            "pool_type": pool_type,
            "enabled": _normalize_bool(payload.get("enabled"), default=True),
            "created_by": operator_id,
            "updated_by": operator_id,
        }
    )
    _sync_agent_pool_agents(int(saved_pool["id"]), agent_members)
    get_db().commit()
    return {"agent_pool": get_conversion_agent_pool_bundle(agent_pool_id=int(saved_pool["id"]))}


def update_conversion_agent_pool(agent_pool_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    ensure_default_conversion_agent_pools()
    existing = workflow_repo.get_agent_pool_row(int(agent_pool_id))
    if not existing:
        raise LookupError("agent pool not found")
    pool_name = _normalized_text(payload.get("pool_name") or payload.get("display_name") or existing.get("display_name"))
    next_pool_code = _slugify_code(payload.get("pool_code") or existing.get("pool_code") or pool_name, prefix="agent_pool")
    duplicate = workflow_repo.get_agent_pool_row_by_code(next_pool_code)
    if duplicate and int(duplicate["id"]) != int(existing["id"]):
        raise ValueError("pool_code already exists")
    next_pool_type = _normalized_text(payload.get("pool_type") or existing.get("pool_type")) or AGENT_POOL_TYPE_SHARED
    if next_pool_type not in _ALLOWED_POOL_TYPES:
        raise ValueError("invalid pool_type")
    if "agents" in payload:
        agent_members = _normalize_agent_members_payload(payload.get("agents"))
    else:
        agent_members = _normalize_agent_members_payload(get_conversion_agent_pool_bundle(agent_pool_id=int(existing["id"])).get("agents") or [])
    _validate_agent_members(agent_members)
    workflow_repo.update_agent_pool_row(
        int(existing["id"]),
        {
            "pool_code": next_pool_code,
            "display_name": pool_name,
            "description": _normalized_text(payload.get("description") if "description" in payload else existing.get("description")),
            "pool_type": next_pool_type,
            "enabled": _normalize_bool(payload.get("enabled"), default=bool(existing.get("enabled"))),
            "updated_by": operator_id,
        },
    )
    _sync_agent_pool_agents(int(existing["id"]), agent_members)
    get_db().commit()
    return {"agent_pool": get_conversion_agent_pool_bundle(agent_pool_id=int(existing["id"]))}


def list_conversion_profile_segment_templates(*, enabled_only: bool = False) -> dict[str, Any]:
    items = [_build_profile_segment_template_bundle(item) for item in workflow_repo.list_profile_segment_template_rows(enabled_only=enabled_only)]
    return {"items": items, "total": len(items)}


def get_conversion_profile_segment_template_bundle(template_id: int) -> dict[str, Any]:
    template = workflow_repo.get_profile_segment_template_row(int(template_id))
    if not template:
        raise LookupError("profile segment template not found")
    return _build_profile_segment_template_bundle(template)


def create_conversion_profile_segment_template(payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    template_name = _normalized_text(payload.get("template_name"))
    if not template_name:
        raise ValueError("template_name is required")
    template_code = _slugify_code(payload.get("template_code") or template_name, prefix="profile_template")
    if workflow_repo.get_profile_segment_template_row_by_code(template_code):
        raise ValueError("template_code already exists")
    questionnaire_id = _normalize_int(payload.get("questionnaire_id"), default=0, minimum=1)
    question_id = _normalize_int(payload.get("segmentation_question_id"), default=0, minimum=1)
    if questionnaire_id <= 0:
        raise ValueError("questionnaire_id is required")
    if question_id <= 0:
        raise ValueError("segmentation_question_id is required")
    categories = _normalize_template_categories_payload(payload.get("categories") or [])
    _validate_segmentation_question(questionnaire_id, question_id, categories)
    saved_template = workflow_repo.insert_profile_segment_template_row(
        {
            "template_code": template_code,
            "template_name": template_name,
            "questionnaire_id": questionnaire_id,
            "segmentation_question_id": question_id,
            "description": _normalized_text(payload.get("description")),
            "enabled": _normalize_bool(payload.get("enabled"), default=True),
            "version": 1,
            "created_by": operator_id,
            "updated_by": operator_id,
        }
    )
    _sync_profile_template_categories(int(saved_template["id"]), question_id, categories)
    get_db().commit()
    return {"template_bundle": get_conversion_profile_segment_template_bundle(int(saved_template["id"]))}


def update_conversion_profile_segment_template(template_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = workflow_repo.get_profile_segment_template_row(int(template_id))
    if not existing:
        raise LookupError("profile segment template not found")
    existing_bundle = _build_profile_segment_template_bundle(existing)
    next_template_name = _normalized_text(payload.get("template_name") or existing.get("template_name"))
    if not next_template_name:
        raise ValueError("template_name is required")
    next_template_code = _slugify_code(payload.get("template_code") or existing.get("template_code") or next_template_name, prefix="profile_template")
    duplicate = workflow_repo.get_profile_segment_template_row_by_code(next_template_code)
    if duplicate and int(duplicate["id"]) != int(existing["id"]):
        raise ValueError("template_code already exists")
    next_questionnaire_id = _normalize_int(payload.get("questionnaire_id") if "questionnaire_id" in payload else existing.get("questionnaire_id"), default=0, minimum=1)
    next_question_id = _normalize_int(payload.get("segmentation_question_id") if "segmentation_question_id" in payload else existing.get("segmentation_question_id"), default=0, minimum=1)
    if next_questionnaire_id <= 0:
        raise ValueError("questionnaire_id is required")
    if next_question_id <= 0:
        raise ValueError("segmentation_question_id is required")
    next_categories = _normalize_template_categories_payload(payload.get("categories")) if "categories" in payload else _extract_bundle_categories(existing_bundle)
    _validate_segmentation_question(next_questionnaire_id, next_question_id, next_categories)
    next_state = {
        "template_code": next_template_code,
        "template_name": next_template_name,
        "questionnaire_id": next_questionnaire_id,
        "segmentation_question_id": next_question_id,
        "description": _normalized_text(payload.get("description") if "description" in payload else existing.get("description")),
        "enabled": _normalize_bool(payload.get("enabled"), default=bool(existing.get("enabled"))),
        "categories": next_categories,
    }
    previous_state = {
        "template_code": _normalized_text(existing.get("template_code")),
        "template_name": _normalized_text(existing.get("template_name")),
        "questionnaire_id": int(existing.get("questionnaire_id") or 0),
        "segmentation_question_id": int(existing.get("segmentation_question_id") or 0),
        "description": _normalized_text(existing.get("description")),
        "enabled": bool(existing.get("enabled")),
        "categories": _extract_bundle_categories(existing_bundle),
    }
    next_version = int(existing.get("version") or 1) + (1 if _json_fingerprint(next_state) != _json_fingerprint(previous_state) else 0)
    workflow_repo.update_profile_segment_template_row(
        int(existing["id"]),
        {
            "template_code": next_state["template_code"],
            "template_name": next_state["template_name"],
            "questionnaire_id": next_state["questionnaire_id"],
            "segmentation_question_id": next_state["segmentation_question_id"],
            "description": next_state["description"],
            "enabled": next_state["enabled"],
            "version": next_version,
            "updated_by": operator_id,
        },
    )
    _sync_profile_template_categories(int(existing["id"]), next_question_id, next_categories)
    get_db().commit()
    return {"template_bundle": get_conversion_profile_segment_template_bundle(int(existing["id"]))}


def list_conversion_workflows(*, include_archived: bool = False, status: str = "") -> dict[str, Any]:
    items = [_build_workflow_bundle(item) for item in workflow_repo.list_workflow_rows(include_archived=include_archived, status=status)]
    return {"items": items, "total": len(items)}


def get_conversion_workflow_model_bundle(workflow_id: int) -> dict[str, Any]:
    workflow = workflow_repo.get_workflow_row(int(workflow_id))
    if not workflow:
        raise LookupError("workflow not found")
    bundle = _build_workflow_bundle(workflow)
    bundle["registry"] = list_conversion_workflow_registry()
    return bundle


def create_conversion_workflow(payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    normalized = _normalize_workflow_payload(payload)
    duplicate = workflow_repo.get_workflow_row_by_code(normalized["workflow_code"])
    if duplicate:
        raise ValueError("workflow_code already exists")
    saved_workflow = workflow_repo.insert_workflow_row({**normalized, "created_by": operator_id, "updated_by": operator_id})
    _sync_workflow_children(int(saved_workflow["id"]), normalized)
    get_db().commit()
    return {"workflow_bundle": get_conversion_workflow_model_bundle(int(saved_workflow["id"]))}


def update_conversion_workflow(workflow_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = get_conversion_workflow_model_bundle(int(workflow_id))
    normalized = _normalize_workflow_payload(payload, existing={**existing["workflow"], "audiences": existing["audiences"], "agent_pool_bindings": [
        {
            "agent_pool_id": int((item.get("agent_pool") or {}).get("id") or 0),
            "pool_code": _normalized_text((item.get("agent_pool") or {}).get("pool_code")),
            "pool_type": _normalized_text((item.get("agent_pool") or {}).get("pool_type")),
            "binding_scope": _normalized_text(item.get("binding_scope")),
            "segment_key": _normalized_text(item.get("segment_key")),
        }
        for item in existing.get("agent_pool_bindings") or []
    ]})
    duplicate = workflow_repo.get_workflow_row_by_code(normalized["workflow_code"])
    if duplicate and int(duplicate["id"]) != int(workflow_id):
        raise ValueError("workflow_code already exists")
    workflow_repo.update_workflow_row(int(workflow_id), {**normalized, "updated_by": operator_id})
    _sync_workflow_children(int(workflow_id), normalized)
    get_db().commit()
    return {"workflow_bundle": get_conversion_workflow_model_bundle(int(workflow_id))}


def activate_conversion_workflow(workflow_id: int, *, operator_id: str) -> dict[str, Any]:
    return update_conversion_workflow(int(workflow_id), {"status": WORKFLOW_STATUS_ACTIVE}, operator_id=operator_id)


def pause_conversion_workflow(workflow_id: int, *, operator_id: str) -> dict[str, Any]:
    return update_conversion_workflow(int(workflow_id), {"status": WORKFLOW_STATUS_PAUSED}, operator_id=operator_id)


def delete_conversion_workflow(workflow_id: int) -> dict[str, Any]:
    existing = workflow_repo.get_workflow_row(int(workflow_id))
    if not existing:
        raise LookupError("workflow not found")
    workflow_repo.delete_workflow_row(int(workflow_id))
    get_db().commit()
    return {
        "deleted_workflow_id": int(workflow_id),
        "workflow_code": _normalized_text(existing.get("workflow_code")),
        "workflow_name": _normalized_text(existing.get("workflow_name")),
    }


def list_conversion_workflow_nodes(workflow_id: int) -> dict[str, Any]:
    bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    return {"items": list(bundle.get("nodes") or []), "total": len(bundle.get("nodes") or [])}


def create_conversion_workflow_node(workflow_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    workflow_bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    normalized = _normalize_node_payload(payload, workflow_bundle)
    node = workflow_repo.insert_workflow_node_row({"workflow_id": int(workflow_id), **normalized})
    _save_node_content(int(node["id"]), normalized)
    get_db().commit()
    return {"node": _build_node_bundle(workflow_repo.get_workflow_node_row(int(node["id"])) or node, get_conversion_workflow_model_bundle(int(workflow_id)))}


def update_conversion_workflow_node(node_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = workflow_repo.get_workflow_node_row(int(node_id))
    if not existing:
        raise LookupError("workflow node not found")
    workflow_bundle = get_conversion_workflow_model_bundle(int(existing["workflow_id"]))
    existing_node_bundle = _build_node_bundle(existing, workflow_bundle)
    normalized = _normalize_node_payload(payload, workflow_bundle, existing=existing_node_bundle)
    workflow_repo.update_workflow_node_row(int(node_id), normalized)
    _save_node_content(int(node_id), normalized)
    get_db().commit()
    refreshed_workflow_bundle = get_conversion_workflow_model_bundle(int(existing["workflow_id"]))
    refreshed_node = workflow_repo.get_workflow_node_row(int(node_id))
    return {"node": _build_node_bundle(refreshed_node or existing, refreshed_workflow_bundle)}


def delete_conversion_workflow_node(node_id: int) -> dict[str, Any]:
    existing = workflow_repo.get_workflow_node_row(int(node_id))
    if not existing:
        raise LookupError("workflow node not found")
    workflow_repo.delete_workflow_node_row(int(node_id))
    get_db().commit()
    return {"deleted_node_id": int(node_id), "workflow_id": int(existing["workflow_id"])}


def list_conversion_workflow_executions(*, workflow_id: int | None = None, node_id: int | None = None, limit: int = 20) -> dict[str, Any]:
    items = workflow_repo.list_workflow_execution_rows(workflow_id=workflow_id, node_id=node_id, limit=limit)
    return {"items": items, "total": len(items)}


def get_conversion_workflow_execution_bundle(execution_row_id: int) -> dict[str, Any]:
    execution = workflow_repo.get_workflow_execution_row(execution_row_id)
    if not execution:
        raise LookupError("workflow execution not found")
    return {
        "execution": execution,
        "items": workflow_repo.list_workflow_execution_item_rows(execution_row_id),
    }


def _send_record_payload(record_id: int | None, *, include_detail: bool = False) -> dict[str, Any]:
    normalized_record_id = int(record_id or 0)
    if normalized_record_id <= 0:
        return {}
    row = user_ops_page_service._load_send_record_row(normalized_record_id)
    if not row:
        return {}
    task_results = user_ops_page_service._hydrate_task_results(row)
    if include_detail:
        return user_ops_page_service._serialize_send_record_detail(row, task_results)
    return user_ops_page_service._serialize_send_record_summary(row, task_results=task_results)


def _build_execution_item_payload(item: dict[str, Any], *, include_send_record_detail: bool = False) -> dict[str, Any]:
    snapshot = dict(item.get("content_snapshot_json") or {})
    member = workflow_repo.get_automation_member_row(int(item.get("member_id") or 0)) or {}
    send_record_id = int(item.get("send_record_id") or 0) or None
    return {
        **item,
        "member": {
            "id": int(member.get("id") or 0) or None,
            "external_contact_id": _normalized_text(member.get("external_contact_id")),
            "phone": _normalized_text(member.get("phone")),
            "owner_staff_id": _normalized_text(member.get("owner_staff_id")),
            "current_audience_code": _normalized_text(member.get("current_audience_code")),
            "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
        },
        "rendered_content_preview": _truncate_text(item.get("rendered_content_text"), limit=160),
        "generation_summary": {
            "content_source": _normalized_text(snapshot.get("content_source")),
            "fallback_reason": _normalized_text(snapshot.get("fallback_reason")),
            "segment_match": dict(snapshot.get("segment_match") or {}),
            "behavior_match": dict(snapshot.get("behavior_match") or {}),
            "agent_pool_id": int(item.get("agent_pool_id") or 0) or None,
            "agent_run_id": _normalized_text(item.get("agent_run_id")),
            "agent_output_id": _normalized_text(item.get("agent_output_id")),
        },
        "send_record_id": send_record_id,
        "send_record": _send_record_payload(send_record_id, include_detail=include_send_record_detail),
    }


def _build_execution_payload(execution: dict[str, Any]) -> dict[str, Any]:
    workflow = workflow_repo.get_workflow_row(int(execution.get("workflow_id") or 0)) or {}
    node = workflow_repo.get_workflow_node_row(int(execution.get("node_id") or 0)) or {}
    return {
        **execution,
        "workflow": {
            "id": int(workflow.get("id") or 0) or None,
            "workflow_code": _normalized_text(workflow.get("workflow_code")),
            "workflow_name": _normalized_text(workflow.get("workflow_name")),
            "status": _normalized_text(workflow.get("status")),
        },
        "node": {
            "id": int(node.get("id") or 0) or None,
            "node_code": _normalized_text(node.get("node_code")),
            "node_name": _normalized_text(node.get("node_name")),
            "target_audience_code": _normalized_text(node.get("target_audience_code")),
            "trigger_mode": _normalized_text(node.get("trigger_mode")) or NODE_TRIGGER_MODE_SCHEDULED,
            "day_offset": int(node.get("day_offset") or 0),
            "send_time": _normalized_text(node.get("send_time")),
        },
    }


def get_conversion_dashboard_payload(*, execution_limit: int = 8, recent_send_limit: int = 50) -> dict[str, Any]:
    audience_counts = workflow_repo.get_current_audience_member_counts()
    recent_executions = [
        _build_execution_payload(item)
        for item in workflow_repo.list_workflow_execution_rows(limit=max(1, min(int(execution_limit), 50)))
    ]
    recent_send_items = workflow_repo.list_recent_workflow_execution_item_rows(limit=max(1, min(int(recent_send_limit), 200)))
    latest_sent_item = next((item for item in recent_send_items if _normalized_text(item.get("status")) == "sent"), {})
    latest_failed_item = next((item for item in recent_send_items if _normalized_text(item.get("status")) == "failed"), {})
    return {
        "audience_overview": {
            "pending_questionnaire_count": int(audience_counts.get(AUDIENCE_PENDING_QUESTIONNAIRE) or 0),
            "operating_count": int(audience_counts.get(AUDIENCE_OPERATING) or 0),
            "converted_count": int(audience_counts.get(AUDIENCE_CONVERTED) or 0),
            "total_count": sum(int(value or 0) for value in audience_counts.values()),
        },
        "active_workflow_count": workflow_repo.count_workflow_rows(status=WORKFLOW_STATUS_ACTIVE),
        "recent_execution_summary": {
            "items": recent_executions,
            "total": len(recent_executions),
        },
        "recent_send_summary": {
            "total_count": len(recent_send_items),
            "success_count": sum(1 for item in recent_send_items if _normalized_text(item.get("status")) == "sent"),
            "failed_count": sum(1 for item in recent_send_items if _normalized_text(item.get("status")) == "failed"),
            "skipped_count": sum(1 for item in recent_send_items if _normalized_text(item.get("status")) == "skipped"),
            "latest_sent_at": _normalized_text(latest_sent_item.get("sent_at") or latest_sent_item.get("updated_at")),
            "latest_failed_at": _normalized_text(latest_failed_item.get("updated_at") or latest_failed_item.get("created_at")),
        },
    }


def get_conversion_workflow_detail_summary(workflow_id: int) -> dict[str, Any]:
    bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    recent_executions = [
        _build_execution_payload(item)
        for item in workflow_repo.list_workflow_execution_rows(workflow_id=int(workflow_id), limit=5)
    ]
    latest_execution = dict(recent_executions[0]) if recent_executions else {}
    bindings_summary = [
        {
            "binding_scope": _normalized_text(item.get("binding_scope")),
            "segment_key": _normalized_text(item.get("segment_key")),
            "pool_id": int(((item.get("agent_pool") or {}).get("id")) or 0) or None,
            "pool_code": _normalized_text((item.get("agent_pool") or {}).get("pool_code")),
            "pool_name": _normalized_text((item.get("agent_pool") or {}).get("pool_name")),
            "pool_type": _normalized_text((item.get("agent_pool") or {}).get("pool_type")),
            "agent_count": len((item.get("agent_pool") or {}).get("agents") or []),
        }
        for item in bundle.get("agent_pool_bindings") or []
    ]
    return {
        "workflow_id": int((bundle.get("workflow") or {}).get("id") or 0),
        "node_count": len(bundle.get("nodes") or []),
        "enabled_node_count": sum(1 for item in bundle.get("nodes") or [] if bool(item.get("enabled"))),
        "latest_execution_at": _normalized_text((latest_execution.get("scheduled_for") or latest_execution.get("updated_at"))),
        "latest_execution": latest_execution,
        "recent_execution_summary": {
            "items": recent_executions,
            "total": len(recent_executions),
        },
        "agent_pool_binding_summary": bindings_summary,
    }


def list_conversion_agent_pool_options(*, enabled_only: bool = True) -> dict[str, Any]:
    items = [
        {
            "id": int(item.get("id") or 0),
            "pool_code": _normalized_text(item.get("pool_code")),
            "pool_name": _normalized_text(item.get("display_name")),
            "pool_type": _normalized_text(item.get("pool_type")),
            "enabled": bool(item.get("enabled")),
            "updated_at": _normalized_text(item.get("updated_at")),
        }
        for item in workflow_repo.list_agent_pool_rows(enabled_only=enabled_only)
    ]
    return {"items": items, "total": len(items)}


def list_conversion_profile_segment_template_options(*, enabled_only: bool = True) -> dict[str, Any]:
    items = [
        {
            "id": int(item.get("id") or 0),
            "template_code": _normalized_text(item.get("template_code")),
            "template_name": _normalized_text(item.get("template_name")),
            "questionnaire_id": int(item.get("questionnaire_id") or 0) or None,
            "segmentation_question_id": int(item.get("segmentation_question_id") or 0) or None,
            "enabled": bool(item.get("enabled")),
            "updated_at": _normalized_text(item.get("updated_at")),
        }
        for item in workflow_repo.list_profile_segment_template_rows(enabled_only=enabled_only)
    ]
    return {"items": items, "total": len(items)}


def list_conversion_workflow_execution_records(*, workflow_id: int | None = None, node_id: int | None = None, limit: int = 20) -> dict[str, Any]:
    items = [
        _build_execution_payload(item)
        for item in workflow_repo.list_workflow_execution_rows(workflow_id=workflow_id, node_id=node_id, limit=limit)
    ]
    return {"items": items, "total": len(items)}


def get_conversion_workflow_execution_detail(execution_row_id: int) -> dict[str, Any]:
    execution = workflow_repo.get_workflow_execution_row(int(execution_row_id))
    if not execution:
        raise LookupError("workflow execution not found")
    items = [
        _build_execution_item_payload(item)
        for item in workflow_repo.list_workflow_execution_item_rows(int(execution_row_id))
    ]
    return {
        "execution": _build_execution_payload(execution),
        "summary": {
            "hit_count": len(items),
            "success_count": sum(1 for item in items if _normalized_text(item.get("status")) == "sent"),
            "failed_count": sum(1 for item in items if _normalized_text(item.get("status")) == "failed"),
            "skipped_count": sum(1 for item in items if _normalized_text(item.get("status")) == "skipped"),
        },
        "items": items,
    }


def list_conversion_workflow_execution_items(execution_row_id: int) -> dict[str, Any]:
    execution = workflow_repo.get_workflow_execution_row(int(execution_row_id))
    if not execution:
        raise LookupError("workflow execution not found")
    items = [
        _build_execution_item_payload(item)
        for item in workflow_repo.list_workflow_execution_item_rows(int(execution_row_id))
    ]
    return {"execution": _build_execution_payload(execution), "items": items, "total": len(items)}


def get_conversion_workflow_execution_item_detail(execution_item_id: int) -> dict[str, Any]:
    item = workflow_repo.get_workflow_execution_item_row(int(execution_item_id))
    if not item:
        raise LookupError("workflow execution item not found")
    execution = workflow_repo.get_workflow_execution_row(int(item.get("execution_id") or 0)) or {}
    return {
        "execution": _build_execution_payload(execution) if execution else {},
        "item": _build_execution_item_payload(item, include_send_record_detail=True),
    }
