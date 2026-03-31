
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from flask import current_app, has_request_context, session

from .archive_message_service import save_tag_snapshot
from .db import get_db
from .identity_binding_service import (
    _normalize_mobile,
    bind_mobile_to_external_contact,
    bind_openid_to_external_contact,
    resolve_external_contact_identity,
)
from .questionnaire_admin_service import _build_questionnaire_detail
from .questionnaire_shared import (
    _dedupe_strings,
    _json_array,
    _json_dumps,
    _normalize_bool,
    _normalize_tag_codes,
)
from .services import QUESTIONNAIRE_TYPES, QuestionnaireAlreadySubmittedError

questionnaire_logger = logging.getLogger("questionnaire")

def _normalize_answer_payload(answers: Any) -> dict[str, Any]:
    if isinstance(answers, dict):
        return {str(key): value for key, value in answers.items()}
    if isinstance(answers, list):
        normalized: dict[str, Any] = {}
        for item in answers:
            if not isinstance(item, dict):
                continue
            question_id = item.get("question_id") or item.get("id")
            if question_id in (None, ""):
                continue
            value = item.get("value")
            if value is None and "selected_option_ids" in item:
                value = item.get("selected_option_ids")
            if value is None and "text_value" in item:
                value = item.get("text_value")
            normalized[str(question_id)] = value
        return normalized
    raise ValueError("answers must be an object or array")

def validate_questionnaire_answers(questionnaire: dict[str, Any], answers: Any) -> list[dict[str, Any]]:
    normalized_answers = _normalize_answer_payload(answers)
    known_question_ids = {str(int(question["id"])) for question in questionnaire.get("questions") or []}
    unknown_question_ids = sorted(set(normalized_answers.keys()) - known_question_ids)
    if unknown_question_ids:
        raise ValueError(f"unknown question_id: {','.join(unknown_question_ids)}")
    validated: list[dict[str, Any]] = []

    for question in questionnaire.get("questions") or []:
        question_id = int(question["id"])
        question_key = str(question_id)
        question_type = question["type"]
        raw_value = normalized_answers.get(question_key)
        option_map = {int(option["id"]): option for option in question.get("options") or []}

        if question_type in {"textarea", "mobile"}:
            text_value = str(raw_value or "").strip()
            if question_type == "mobile" and text_value:
                text_value = _normalize_mobile(text_value)
            if question["required"] and not text_value:
                raise ValueError(f"question '{question['title']}' is required")
            validated.append(
                {
                    "question": question,
                    "question_id": question_id,
                    "question_type": question_type,
                    "selected_options": [],
                    "text_value": text_value,
                }
            )
            continue

        selected_ids_raw: list[Any]
        if raw_value in (None, ""):
            selected_ids_raw = []
        elif isinstance(raw_value, list):
            selected_ids_raw = raw_value
        else:
            selected_ids_raw = [raw_value]

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for raw_id in selected_ids_raw:
            try:
                option_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"question '{question['title']}' has an invalid option") from exc
            if option_id in seen_ids:
                continue
            if option_id not in option_map:
                raise ValueError(f"question '{question['title']}' has an invalid option")
            seen_ids.add(option_id)
            normalized_ids.append(option_id)

        if question_type == "single_choice" and len(normalized_ids) > 1:
            raise ValueError(f"question '{question['title']}' only allows one option")
        if question["required"] and not normalized_ids:
            raise ValueError(f"question '{question['title']}' is required")

        validated.append(
            {
                "question": question,
                "question_id": question_id,
                "question_type": question_type,
                "selected_options": [option_map[option_id] for option_id in normalized_ids],
                "text_value": "",
            }
        )

    return validated

def compute_questionnaire_result(questionnaire: dict[str, Any], answers: Any) -> dict[str, Any]:
    validated_answers = answers if isinstance(answers, list) and answers and "question" in answers[0] else validate_questionnaire_answers(questionnaire, answers)
    total_score = 0.0
    option_tags: list[str] = []
    answer_snapshots: list[dict[str, Any]] = []

    for item in validated_answers:
        question = item["question"]
        selected_options = item.get("selected_options") or []
        selected_option_ids = [int(option["id"]) for option in selected_options]
        selected_option_texts = [option["option_text"] for option in selected_options]
        selected_option_scores = [float(option.get("score") or 0) for option in selected_options]
        selected_option_tags = _dedupe_strings(
            [tag for option in selected_options for tag in _normalize_tag_codes(option.get("tag_codes"))]
        )
        score_contribution = sum(selected_option_scores)
        if question["type"] in {"single_choice", "multi_choice"}:
            total_score += score_contribution
            option_tags.extend(selected_option_tags)

        answer_snapshots.append(
            {
                "question_id": int(question["id"]),
                "question_type": question["type"],
                "question_title_snapshot": question["title"],
                "selected_option_ids": selected_option_ids,
                "selected_option_texts_snapshot": selected_option_texts,
                "selected_option_scores_snapshot": selected_option_scores,
                "selected_option_tags_snapshot": selected_option_tags,
                "text_value": item.get("text_value", ""),
                "score_contribution": score_contribution if question["type"] not in {"textarea", "mobile"} else 0.0,
            }
        )

    matched_rule_tags: list[str] = []
    for rule in questionnaire.get("score_rules") or []:
        min_score = rule.get("min_score")
        max_score = rule.get("max_score")
        if min_score is not None and total_score < float(min_score):
            continue
        if max_score is not None and total_score > float(max_score):
            continue
        matched_rule_tags.extend(_normalize_tag_codes(rule.get("tag_codes")))

    final_tags = _dedupe_strings(option_tags + matched_rule_tags)
    return {
        "validated_answers": validated_answers,
        "answer_snapshots": answer_snapshots,
        "total_score": total_score,
        "final_tags": final_tags,
        "redirect_url": questionnaire.get("redirect_url", "") or "",
    }

def resolve_questionnaire_submit_identity(
    openid: str = "",
    unionid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
    if not corp_id:
        return None
    lookup_order = [
        ("unionid", str(unionid or "").strip()),
        ("openid", str(openid or "").strip()),
        ("external_userid", str(external_userid or "").strip()),
    ]
    for matched_by, value in lookup_order:
        if not value:
            continue
        resolved = resolve_external_contact_identity(corp_id, **{matched_by: value})
        if resolved:
            identity = dict(resolved)
            identity["matched_by"] = matched_by
            return identity
    return None

def _get_questionnaire_session_identity() -> dict[str, str]:
    if not has_request_context():
        return {}
    identity = session.get("questionnaire_h5_identity") or {}
    if not isinstance(identity, dict):
        return {}
    return {
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or "").strip(),
    }

def _extract_mobile_snapshot_from_validated_answers(validated_answers: list[dict[str, Any]]) -> str:
    for item in validated_answers or []:
        question = item.get("question") or {}
        if str(question.get("type") or "").strip() != "mobile":
            continue
        text_value = str(item.get("text_value") or "").strip()
        if text_value:
            return text_value
    return ""

def _build_respondent_key(identity: dict[str, Any] | None, request_meta: dict[str, Any] | None) -> str:
    meta = request_meta or {}
    explicit = str(meta.get("respondent_key") or "").strip()
    if explicit:
        return explicit
    if identity:
        for field in ["unionid", "openid", "external_userid"]:
            value = str(identity.get(field) or "").strip()
            if value:
                return value
    for field in ["unionid", "openid", "external_userid"]:
        value = str(meta.get(field) or "").strip()
        if value:
            return value
    ip = str(meta.get("ip") or "").strip()
    if ip:
        return f"ip:{ip}"
    return f"anon:{uuid4().hex}"

def has_questionnaire_submission(questionnaire_id: int, identity: dict[str, Any] | None) -> bool:
    normalized = identity or {}
    lookup_order = [
        ("external_userid", str(normalized.get("external_userid") or "").strip()),
        ("unionid", str(normalized.get("unionid") or "").strip()),
        ("openid", str(normalized.get("openid") or "").strip()),
        ("respondent_key", str(normalized.get("respondent_key") or "").strip()),
    ]
    db = get_db()
    for field, value in lookup_order:
        if not value:
            continue
        row = db.execute(
            f"""
            SELECT id
            FROM questionnaire_submissions
            WHERE questionnaire_id = ? AND {field} = ?
            LIMIT 1
            """,
            (int(questionnaire_id), value),
        ).fetchone()
        if row:
            return True
    return False

def save_questionnaire_submission(
    questionnaire: dict[str, Any],
    identity: dict[str, Any] | None,
    computed_result: dict[str, Any],
    answers: Any,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del answers
    meta = request_meta or {}
    identity = identity or {}
    db = get_db()
    respondent_key = _build_respondent_key(identity, meta)
    openid = str(identity.get("openid") or meta.get("openid") or "").strip()
    unionid = str(identity.get("unionid") or meta.get("unionid") or "").strip()
    external_userid = str(identity.get("external_userid") or meta.get("external_userid") or "").strip()
    follow_user_userid = str(identity.get("follow_user_userid") or "").strip()
    mobile_snapshot = str(computed_result.get("mobile_snapshot") or "").strip()
    row = db.execute(
        """
        INSERT INTO questionnaire_submissions (
            questionnaire_id, identity_map_id, respondent_key, openid, unionid, external_userid,
            follow_user_userid, matched_by, mobile_snapshot, source_channel, campaign_id, staff_id,
            total_score, final_tags, redirect_url_snapshot, submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id, submitted_at
        """,
        (
            int(questionnaire["id"]),
            identity.get("identity_map_id"),
            respondent_key,
            openid,
            unionid,
            external_userid,
            follow_user_userid,
            str(identity.get("matched_by") or "").strip(),
            mobile_snapshot,
            str(meta.get("source_channel") or "").strip(),
            str(meta.get("campaign_id") or "").strip(),
            str(meta.get("staff_id") or "").strip(),
            float(computed_result.get("total_score") or 0),
            _json_dumps(computed_result.get("final_tags") or []),
            str(computed_result.get("redirect_url") or questionnaire.get("redirect_url") or "").strip(),
        ),
    ).fetchone()
    submission_id = int(row["id"])

    for item in computed_result.get("answer_snapshots") or []:
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                submission_id,
                int(item["question_id"]),
                item["question_type"],
                item["question_title_snapshot"],
                _json_dumps(item.get("selected_option_ids") or []),
                _json_dumps(item.get("selected_option_texts_snapshot") or []),
                _json_dumps(item.get("selected_option_scores_snapshot") or []),
                _json_dumps(item.get("selected_option_tags_snapshot") or []),
                item.get("text_value", "") or "",
                float(item.get("score_contribution") or 0),
            ),
        )
    db.commit()
    questionnaire_logger.info(
        "questionnaire submission saved submission_id=%s total_score=%s final_tags=%s",
        submission_id,
        float(computed_result.get("total_score") or 0),
        ",".join(computed_result.get("final_tags") or []),
    )
    return {
        "id": submission_id,
        "submitted_at": row.get("submitted_at", ""),
        "questionnaire_id": int(questionnaire["id"]),
        "respondent_key": respondent_key,
        "openid": openid,
        "unionid": unionid,
        "external_userid": external_userid,
        "follow_user_userid": follow_user_userid,
        "matched_by": str(identity.get("matched_by") or "").strip(),
        "mobile_snapshot": mobile_snapshot,
        "total_score": float(computed_result.get("total_score") or 0),
        "final_tags": computed_result.get("final_tags") or [],
        "redirect_url_snapshot": str(computed_result.get("redirect_url") or questionnaire.get("redirect_url") or "").strip(),
    }

def apply_questionnaire_mobile_binding(submission: dict[str, Any]) -> dict[str, Any]:
    mobile_snapshot = str((submission or {}).get("mobile_snapshot") or "").strip()
    external_userid = str((submission or {}).get("external_userid") or "").strip()
    follow_user_userid = str((submission or {}).get("follow_user_userid") or "").strip()
    if not mobile_snapshot:
        return {"bound": False, "reason": "no_mobile_snapshot"}
    if not external_userid:
        return {"bound": False, "reason": "no_external_userid"}
    try:
        binding = bind_mobile_to_external_contact(
            external_userid=external_userid,
            owner_userid=follow_user_userid,
            bind_by_userid="questionnaire_submit",
            mobile=mobile_snapshot,
            force_rebind=True,
        )
        questionnaire_logger.info(
            "questionnaire mobile bound submission_id=%s external_userid=%s mobile=%s person_id=%s",
            int(submission.get("id") or 0),
            external_userid,
            mobile_snapshot,
            str(binding.get("person_id") or ""),
        )
        return {"bound": True, "binding": binding}
    except Exception as exc:
        questionnaire_logger.exception(
            "questionnaire mobile bind failed submission_id=%s external_userid=%s",
            int(submission.get("id") or 0),
            external_userid,
        )
        return {"bound": False, "reason": "bind_failed", "error": str(exc)}

def _log_questionnaire_scrm_apply(
    submission_id: int,
    *,
    external_userid: str,
    follow_user_userid: str,
    final_tags: list[str],
    status: str,
    error_message: str = "",
) -> None:
    get_db().execute(
        """
        INSERT INTO questionnaire_scrm_apply_logs (
            submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(submission_id),
            external_userid,
            follow_user_userid,
            _json_dumps(final_tags),
            status,
            error_message,
        ),
    )
    get_db().commit()

def apply_questionnaire_result_to_scrm(submission_id: int) -> dict[str, Any]:
    submission = get_db().execute(
        """
        SELECT id, external_userid, follow_user_userid, final_tags
        FROM questionnaire_submissions
        WHERE id = ?
        """,
        (int(submission_id),),
    ).fetchone()
    if not submission:
        return {"applied": False, "reason": "submission_not_found"}

    external_userid = str(submission.get("external_userid") or "").strip()
    follow_user_userid = str(submission.get("follow_user_userid") or "").strip()
    final_tags = _dedupe_strings(_json_array(submission.get("final_tags")))
    if not external_userid:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="skipped",
            error_message="no_external_userid",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_external_userid", submission_id)
        return {"applied": False, "reason": "no_external_userid"}

    if not follow_user_userid:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="skipped",
            error_message="no_follow_user_userid",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_follow_user_userid", submission_id)
        return {"applied": False, "reason": "no_follow_user_userid"}

    if not final_tags:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="skipped",
            error_message="no_final_tags",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_final_tags", submission_id)
        return {"applied": False, "reason": "no_final_tags"}

    try:
        from .wecom_client import WeComClient

        client = WeComClient.from_app()
        result = client.mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=final_tags,
            remove_tags=None,
        )
        save_tag_snapshot(follow_user_userid, external_userid, final_tags)
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="success",
        )
        questionnaire_logger.info(
            "questionnaire scrm applied submission_id=%s external_userid=%s follow_user_userid=%s tags=%s",
            submission_id,
            external_userid,
            follow_user_userid,
            ",".join(final_tags),
        )
        return {"applied": True, "result": result}
    except Exception as exc:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="failed",
            error_message=str(exc),
        )
        questionnaire_logger.exception(
            "questionnaire scrm apply failed submission_id=%s external_userid=%s follow_user_userid=%s",
            submission_id,
            external_userid,
            follow_user_userid,
        )
        return {"applied": False, "reason": "wecom_error", "error": str(exc)}

def submit_questionnaire(slug: str, payload: dict[str, Any], request_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    slug_value = str(slug or "").strip()
    row = get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
        FROM questionnaires
        WHERE slug = ? AND is_disabled = ?
        LIMIT 1
        """,
        (slug_value, False),
    ).fetchone()
    if not row:
        raise LookupError("questionnaire not found")
    questionnaire = _build_questionnaire_detail(row)

    answers = payload.get("answers")
    if answers is None:
        raise ValueError("answers is required")

    submit_meta = dict(request_meta or {})
    session_identity = _get_questionnaire_session_identity()
    for field in ["source_channel", "campaign_id", "staff_id"]:
        if field in payload and payload.get(field) is not None:
            submit_meta[field] = payload.get(field)
    submit_meta["respondent_key"] = session_identity.get("respondent_key") or str(payload.get("respondent_key") or "").strip()
    submit_meta["openid"] = session_identity.get("openid") or str(payload.get("openid") or "").strip()
    submit_meta["unionid"] = session_identity.get("unionid") or str(payload.get("unionid") or "").strip()
    submit_meta["external_userid"] = str(payload.get("external_userid") or "").strip()

    resolved_unionid = submit_meta["unionid"]
    resolved_openid = submit_meta["openid"]
    payload_external_userid = submit_meta["external_userid"]

    identity = resolve_questionnaire_submit_identity(
        openid=resolved_openid,
        unionid=resolved_unionid,
        external_userid=payload_external_userid,
    )
    if identity and identity.get("matched_by") == "unionid" and resolved_openid and not str(identity.get("openid") or "").strip():
        corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
        rebound = bind_openid_to_external_contact(
            corp_id,
            str(identity.get("external_userid") or "").strip(),
            resolved_openid,
            unionid=resolved_unionid,
        )
        if rebound:
            identity = dict(rebound)
            identity["matched_by"] = "unionid"
    if identity:
        identity["openid"] = str(identity.get("openid") or resolved_openid or "").strip()
        identity["unionid"] = str(identity.get("unionid") or resolved_unionid or "").strip()

    questionnaire_logger.info(
        "questionnaire identity resolved slug=%s questionnaire_id=%s matched_by=%s identity_map_id=%s external_userid=%s follow_user_userid=%s",
        slug_value,
        int(questionnaire["id"]),
        str((identity or {}).get("matched_by") or ""),
        str((identity or {}).get("identity_map_id") or ""),
        str((identity or {}).get("external_userid") or ""),
        str((identity or {}).get("follow_user_userid") or ""),
    )

    duplicate_identity = {
        "external_userid": str((identity or {}).get("external_userid") or payload_external_userid or "").strip(),
        "unionid": str((identity or {}).get("unionid") or resolved_unionid or "").strip(),
        "openid": str((identity or {}).get("openid") or resolved_openid or "").strip(),
        "respondent_key": _build_respondent_key(identity, submit_meta),
    }
    if has_questionnaire_submission(int(questionnaire["id"]), duplicate_identity):
        raise QuestionnaireAlreadySubmittedError("已经提交")

    validated_answers = validate_questionnaire_answers(questionnaire, answers)
    computed_result = compute_questionnaire_result(questionnaire, validated_answers)
    computed_result["mobile_snapshot"] = _extract_mobile_snapshot_from_validated_answers(
        computed_result.get("validated_answers") or validated_answers
    )
    submission = save_questionnaire_submission(
        questionnaire,
        identity,
        computed_result,
        answers,
        request_meta=submit_meta,
    )
    apply_questionnaire_mobile_binding(submission)
    apply_questionnaire_result_to_scrm(submission["id"])
    return {
        "success": True,
        "redirect_url": computed_result.get("redirect_url", "") or "",
        "message": "已收到提交",
    }
