from __future__ import annotations

from typing import Any

from aicrm_next.shared.errors import ContractError


def normalize_questionnaire(item: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(item.get("enabled", not bool(item.get("is_disabled", False))))
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
        "external_push_config": dict(item.get("external_push_config") or {}),
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
    return {
        "questionnaire": {key: value for key, value in questionnaire.items() if key != "questions"},
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
    return {"questionnaire": public_questionnaire, "questions": questionnaire["questions"]}


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
