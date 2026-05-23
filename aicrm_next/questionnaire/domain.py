from __future__ import annotations

from typing import Any

from aicrm_next.shared.errors import ContractError


def _item_has_key(item: dict[str, Any], key: str) -> bool:
    return key in item and item.get(key) is not None


def _external_push_bool(item: dict[str, Any], config: dict[str, Any], key: str, config_key: str) -> bool:
    if _item_has_key(item, key):
        return bool(item.get(key))
    return bool(config.get(config_key))


def _external_push_text(item: dict[str, Any], config: dict[str, Any], key: str, config_key: str) -> str:
    if _item_has_key(item, key):
        return str(item.get(key) or "").strip()
    return str(config.get(config_key) or "").strip()


def _external_push_value(item: dict[str, Any], config: dict[str, Any], key: str, config_key: str) -> Any:
    if _item_has_key(item, key):
        return item.get(key)
    return config.get(config_key)


def normalize_questionnaire(item: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(item.get("enabled", not bool(item.get("is_disabled", False))))
    external_push_config = dict(item.get("external_push_config") or {})
    normalized = {
        "id": item["id"],
        "slug": str(item.get("slug") or "").strip(),
        "title": str(item.get("title") or item.get("name") or "").strip(),
        "name": str(item.get("name") or item.get("title") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "enabled": enabled,
        "is_disabled": not enabled,
        "redirect_url": str(item.get("redirect_url") or "").strip(),
        "submit_button_text": str(item.get("submit_button_text") or "提交").strip(),
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
        "questions": [normalize_question(question) for question in item.get("questions", [])],
        "external_push_config": external_push_config,
        "external_push_enabled": _external_push_bool(item, external_push_config, "external_push_enabled", "enabled"),
        "external_push_url": _external_push_text(item, external_push_config, "external_push_url", "webhook_url"),
        "external_push_type": _external_push_text(item, external_push_config, "external_push_type", "type"),
        "external_push_expires_at_ts": _external_push_value(
            item,
            external_push_config,
            "external_push_expires_at_ts",
            "expires_at_ts",
        ),
        "external_push_day": _external_push_value(item, external_push_config, "external_push_day", "day"),
        "external_push_frequency": _external_push_value(
            item,
            external_push_config,
            "external_push_frequency",
            "frequency",
        ),
        "external_push_remark": _external_push_text(item, external_push_config, "external_push_remark", "remark"),
        "external_push_custom_params": list(
            _external_push_value(item, external_push_config, "external_push_custom_params", "custom_params") or []
        ),
        "submission_count": int(item.get("submission_count") or 0),
        "assessment_enabled": bool(item.get("assessment_enabled", False)),
    }
    normalized["question_count"] = len(normalized["questions"])
    normalized["public_path"] = f"/s/{normalized['slug']}"
    normalized["submitted_path"] = f"/s/{normalized['slug']}/submitted"
    return normalized


def normalize_question(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": question["id"],
        "type": str(question.get("type") or "single_choice"),
        "title": str(question.get("title") or "").strip(),
        "required": bool(question.get("required", False)),
        "sidebar_profile_field": str(question.get("sidebar_profile_field") or "").strip(),
        "options": [normalize_option(option) for option in question.get("options", [])],
        "placeholder_text": str(question.get("placeholder_text") or ""),
    }


def normalize_option(option: dict[str, Any]) -> dict[str, Any]:
    label = str(option.get("label") or option.get("option_text") or option.get("value") or "").strip()
    value = str(option.get("value") or option.get("id") or label).strip()
    return {
        "id": option.get("id") or value,
        "label": label,
        "option_text": label,
        "value": value,
        "tag_codes": list(option.get("tag_codes") or []),
        "score": int(option.get("score") or 0),
    }


def summary_projection(item: dict[str, Any]) -> dict[str, Any]:
    questionnaire = normalize_questionnaire(item)
    keys = [
        "id",
        "slug",
        "title",
        "name",
        "description",
        "enabled",
        "is_disabled",
        "redirect_url",
        "created_at",
        "updated_at",
        "question_count",
        "submission_count",
        "assessment_enabled",
        "public_path",
        "submitted_path",
    ]
    return {key: questionnaire[key] for key in keys}


def admin_detail_projection(item: dict[str, Any]) -> dict[str, Any]:
    questionnaire = normalize_questionnaire(item)
    admin_questionnaire = {key: value for key, value in questionnaire.items() if key != "questions"}
    admin_questionnaire["questions"] = questionnaire["questions"]
    return {
        "questionnaire": admin_questionnaire,
        "questions": questionnaire["questions"],
        "external_push_config": questionnaire["external_push_config"],
    }


def public_projection(item: dict[str, Any]) -> dict[str, Any]:
    questionnaire = normalize_questionnaire(item)
    public_questionnaire = {
        key: questionnaire[key]
        for key in [
            "id",
            "slug",
            "title",
            "description",
            "enabled",
            "redirect_url",
            "submit_button_text",
            "created_at",
            "updated_at",
        ]
    }
    public_questions = [
        {key: value for key, value in question.items() if key != "sidebar_profile_field"}
        for question in questionnaire["questions"]
    ]
    return {"questionnaire": public_questionnaire, "questions": public_questions}


def validate_required_answers(questionnaire: dict[str, Any], answers: dict[str, Any]) -> None:
    for question in normalize_questionnaire(questionnaire)["questions"]:
        if not question["required"]:
            continue
        value = answers.get(str(question["id"]))
        if value in (None, "", []):
            raise ContractError(f"missing required answer: {question['id']}")


def score_and_tags(questionnaire: dict[str, Any], answers: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    tags: list[str] = []
    for question in normalize_questionnaire(questionnaire)["questions"]:
        raw_value = answers.get(str(question["id"]))
        selected_values = {str(item) for item in raw_value} if isinstance(raw_value, list) else {str(raw_value)}
        for option in question["options"]:
            if str(option["id"]) in selected_values or str(option["value"]) in selected_values:
                score += int(option.get("score") or 0)
                for tag_code in option.get("tag_codes") or []:
                    if tag_code not in tags:
                        tags.append(str(tag_code))
    return score, tags
