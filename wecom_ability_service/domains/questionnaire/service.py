from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from flask import current_app, has_request_context, session

from ...db import get_db
from ..tags import repo as tags_repo

questionnaire_logger = logging.getLogger("questionnaire")
QUESTIONNAIRE_TYPES = {"single_choice", "multi_choice", "textarea", "mobile"}


class QuestionnaireAlreadySubmittedError(ValueError):
    pass
def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_array(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _dedupe_strings(values: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_float(value: Any, field_name: str, *, allow_none: bool = False) -> float | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def _normalize_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sort_order must be an integer") from exc


def _normalize_required_integer(value: Any, field_name: str, *, allow_none: bool = False) -> int | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _validate_tag_codes_payload(value: Any, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return _dedupe_strings(value)


def _slugify_questionnaire(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not base:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        base = f"q-{timestamp}-{suffix}"
    return base[:120]


def _questionnaire_exists_by_slug(slug: str, *, exclude_id: int | None = None) -> bool:
    sql = "SELECT id FROM questionnaires WHERE slug = ?"
    params: list[Any] = [slug]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_id))
    row = get_db().execute(sql, tuple(params)).fetchone()
    return row is not None


def _normalize_tag_codes(value: Any) -> list[str]:
    # The questionnaire schema keeps the historical field name `tag_codes`,
    # but values are treated end-to-end as the exact WeCom tag identifiers
    # accepted by externalcontact/mark_tag.
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            return _dedupe_strings(_json_array(candidate))
        if "/" in candidate:
            return _dedupe_strings(candidate.split("/"))
        if "," in candidate:
            return _dedupe_strings(candidate.split(","))
        return _dedupe_strings([candidate])
    if isinstance(value, (list, tuple)):
        return _dedupe_strings(list(value))
    return []


def _normalize_questionnaire_payload(
    payload: dict[str, Any],
    *,
    questionnaire_id: int | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    redirect_url = str(payload.get("redirect_url") or "").strip()
    slug_source = str(payload.get("slug") or (existing or {}).get("slug") or name or title).strip()
    slug = _slugify_questionnaire(slug_source)

    if not name:
        raise ValueError("name is required")
    if not title:
        raise ValueError("title is required")
    if _questionnaire_exists_by_slug(slug, exclude_id=questionnaire_id):
        raise ValueError("slug already exists")

    raw_questions = payload.get("questions", [])
    if raw_questions is None:
        raw_questions = []
    if not isinstance(raw_questions, list):
        raise ValueError("questions must be an array")

    normalized_questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            raise ValueError("question must be an object")
        question_type = str(item.get("type") or "").strip()
        if question_type not in QUESTIONNAIRE_TYPES:
            raise ValueError("question type must be single_choice, multi_choice, textarea or mobile")
        question_title = str(item.get("title") or "").strip()
        if not question_title:
            raise ValueError("question title is required")
        question_payload = {
            "id": int(item["id"]) if item.get("id") not in (None, "") else None,
            "type": question_type,
            "title": question_title,
            "required": _normalize_bool(item.get("required")),
            "sort_order": _normalize_int(item.get("sort_order"), index),
            "options": [],
        }
        raw_options = item.get("options") or []
        if question_type in {"single_choice", "multi_choice"}:
            if not isinstance(raw_options, list) or not raw_options:
                raise ValueError(f"question '{question_title}' must have options")
            normalized_options: list[dict[str, Any]] = []
            for option_index, option in enumerate(raw_options, start=1):
                if not isinstance(option, dict):
                    raise ValueError("option must be an object")
                option_text = str(option.get("option_text") or "").strip()
                if not option_text:
                    raise ValueError(f"question '{question_title}' has an empty option_text")
                normalized_options.append(
                    {
                        "id": int(option["id"]) if option.get("id") not in (None, "") else None,
                        "option_text": option_text,
                        "score": _normalize_required_integer(option.get("score"), "score"),
                        "tag_codes": _validate_tag_codes_payload(option.get("tag_codes"), "tag_codes"),
                        "sort_order": _normalize_int(option.get("sort_order"), option_index),
                    }
                )
            question_payload["options"] = normalized_options
        normalized_questions.append(question_payload)

    raw_score_rules = payload.get("score_rules") or []
    if not isinstance(raw_score_rules, list):
        raise ValueError("score_rules must be an array")
    normalized_score_rules: list[dict[str, Any]] = []
    for index, item in enumerate(raw_score_rules, start=1):
        if not isinstance(item, dict):
            raise ValueError("score rule must be an object")
        min_score = _normalize_required_integer(item.get("min_score"), "min_score", allow_none=True)
        max_score = _normalize_required_integer(item.get("max_score"), "max_score", allow_none=True)
        if min_score is None and max_score is None:
            raise ValueError("score rule must have min_score or max_score")
        if min_score is not None and max_score is not None and min_score > max_score:
            raise ValueError("score rule min_score cannot be greater than max_score")
        tag_codes = _validate_tag_codes_payload(item.get("tag_codes"), "tag_codes")
        if not tag_codes:
            raise ValueError("score rule tag_codes cannot be empty")
        normalized_score_rules.append(
            {
                "id": int(item["id"]) if item.get("id") not in (None, "") else None,
                "min_score": min_score,
                "max_score": max_score,
                "tag_codes": tag_codes,
                "sort_order": _normalize_int(item.get("sort_order"), index),
            }
        )

    return {
        "slug": slug,
        "name": name,
        "title": title,
        "description": description,
        "is_disabled": _normalize_bool(payload.get("is_disabled", (existing or {}).get("is_disabled"))),
        "redirect_url": redirect_url,
        "questions": normalized_questions,
        "score_rules": normalized_score_rules,
    }


def _get_questionnaire_row(questionnaire_id: int) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
        FROM questionnaires
        WHERE id = ?
        """,
        (int(questionnaire_id),),
    ).fetchone()


def _serialize_questionnaire_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "slug": row.get("slug", ""),
        "name": row.get("name", ""),
        "title": row.get("title", ""),
        "description": row.get("description", "") or "",
        "is_disabled": _normalize_bool(row.get("is_disabled")),
        "redirect_url": row.get("redirect_url", "") or "",
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _load_questionnaire_questions(questionnaire_id: int) -> list[dict[str, Any]]:
    question_rows = get_db().execute(
        """
        SELECT id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    if not question_rows:
        return []
    question_ids = [int(row["id"]) for row in question_rows]
    placeholders = ",".join("?" for _ in question_ids)
    option_rows = get_db().execute(
        f"""
        SELECT id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_options
        WHERE question_id IN ({placeholders})
        ORDER BY sort_order ASC, id ASC
        """,
        tuple(question_ids),
    ).fetchall()
    options_by_question: dict[int, list[dict[str, Any]]] = {}
    for row in option_rows:
        options_by_question.setdefault(int(row["question_id"]), []).append(
            {
                "id": int(row["id"]),
                "question_id": int(row["question_id"]),
                "option_text": row.get("option_text", ""),
                "score": float(row.get("score") or 0),
                "tag_codes": _normalize_tag_codes(row.get("tag_codes")),
                "sort_order": int(row.get("sort_order") or 0),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
        )
    return [
        {
            "id": int(row["id"]),
            "questionnaire_id": int(row["questionnaire_id"]),
            "type": row.get("type", ""),
            "title": row.get("title", ""),
            "required": _normalize_bool(row.get("required")),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
            "options": options_by_question.get(int(row["id"]), []),
        }
        for row in question_rows
    ]


def _load_questionnaire_score_rules(questionnaire_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT id, questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_score_rules
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "questionnaire_id": int(row["questionnaire_id"]),
            "min_score": float(row["min_score"]) if row.get("min_score") is not None else None,
            "max_score": float(row["max_score"]) if row.get("max_score") is not None else None,
            "tag_codes": _normalize_tag_codes(row.get("tag_codes")),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
        for row in rows
    ]


def _questionnaire_submission_stats(questionnaire_id: int) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT COUNT(*) AS submission_count, MAX(submitted_at) AS last_submitted_at
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        """,
        (int(questionnaire_id),),
    ).fetchone()
    return {
        "submission_count": int(row["submission_count"] or 0) if row else 0,
        "last_submitted_at": row.get("last_submitted_at", "") if row else "",
    }


def _build_questionnaire_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = _serialize_questionnaire_row(row)
    detail["questions"] = _load_questionnaire_questions(int(row["id"]))
    detail["score_rules"] = _load_questionnaire_score_rules(int(row["id"]))
    detail.update(_questionnaire_submission_stats(int(row["id"])))
    return detail


def _insert_questionnaire_options(question_id: int, options: list[dict[str, Any]]) -> None:
    db = get_db()
    for item in options:
        db.execute(
            """
            INSERT INTO questionnaire_options (
                question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(question_id),
                item["option_text"],
                item["score"],
                _json_dumps(item["tag_codes"]),
                item["sort_order"],
            ),
        )


def _sync_questionnaire_questions(questionnaire_id: int, questions: list[dict[str, Any]]) -> None:
    db = get_db()
    db.execute("DELETE FROM questionnaire_questions WHERE questionnaire_id = ?", (int(questionnaire_id),))

    for item in questions:
        row = db.execute(
            """
            INSERT INTO questionnaire_questions (
                questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                int(questionnaire_id),
                item["type"],
                item["title"],
                item["required"],
                item["sort_order"],
            ),
        ).fetchone()
        current_question_id = int(row["id"])
        if item["type"] not in {"textarea", "mobile"}:
            _insert_questionnaire_options(current_question_id, item.get("options") or [])


def _sync_questionnaire_score_rules(questionnaire_id: int, score_rules: list[dict[str, Any]]) -> None:
    db = get_db()
    db.execute("DELETE FROM questionnaire_score_rules WHERE questionnaire_id = ?", (int(questionnaire_id),))

    for item in score_rules:
        db.execute(
            """
            INSERT INTO questionnaire_score_rules (
                questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(questionnaire_id),
                item["min_score"],
                item["max_score"],
                _json_dumps(item["tag_codes"]),
                item["sort_order"],
            ),
        )


def list_questionnaires() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT q.id, q.slug, q.name, q.title, q.description, q.is_disabled, q.redirect_url, q.created_at, q.updated_at,
               COUNT(s.id) AS submission_count, MAX(s.submitted_at) AS last_submitted_at
        FROM questionnaires q
        LEFT JOIN questionnaire_submissions s ON s.questionnaire_id = q.id
        GROUP BY q.id, q.slug, q.name, q.title, q.description, q.is_disabled, q.redirect_url, q.created_at, q.updated_at
        ORDER BY q.updated_at DESC, q.id DESC
        """
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_questionnaire_row(row)
        item["submission_count"] = int(row["submission_count"] or 0)
        item["last_submitted_at"] = row.get("last_submitted_at", "") or ""
        results.append(item)
    return results


def list_available_wecom_tags() -> list[dict[str, Any]]:
    from ...wecom_client import WeComClient

    client = WeComClient.from_app()
    payload = client.list_external_contact_tags()
    items: list[dict[str, Any]] = []
    for group in payload.get("tag_group") or []:
        group_name = str(group.get("group_name") or "").strip()
        group_id = str(group.get("group_id") or "").strip()
        for tag in group.get("tag") or []:
            tag_id = str(tag.get("id") or "").strip()
            tag_name = str(tag.get("name") or "").strip()
            if not tag_id or not tag_name:
                continue
            items.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "group_name": group_name,
                    "group_id": group_id,
                }
            )
    return sorted(items, key=lambda item: ((item.get("group_name") or ""), (item.get("tag_name") or ""), item["tag_id"]))


def get_latest_questionnaire_submit_debug(questionnaire_id: int) -> dict[str, Any] | None:
    submission = get_db().execute(
        """
        SELECT id, questionnaire_id, submitted_at, matched_by, identity_map_id, openid, unionid,
               external_userid, follow_user_userid, total_score, final_tags, redirect_url_snapshot
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (int(questionnaire_id),),
    ).fetchone()
    if not submission:
        return None

    scrm_apply = get_db().execute(
        """
        SELECT status, error_message
        FROM questionnaire_scrm_apply_logs
        WHERE submission_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(submission["id"]),),
    ).fetchone()
    return {
        "questionnaire_id": int(submission["questionnaire_id"]),
        "submission_id": int(submission["id"]),
        "submitted_at": submission.get("submitted_at", "") or "",
        "matched_by": submission.get("matched_by", "") or "",
        "identity_map_id": int(submission["identity_map_id"]) if submission.get("identity_map_id") is not None else None,
        "openid": submission.get("openid", "") or "",
        "unionid": submission.get("unionid", "") or "",
        "external_userid": submission.get("external_userid", "") or "",
        "follow_user_userid": submission.get("follow_user_userid", "") or "",
        "total_score": float(submission.get("total_score") or 0),
        "final_tags": _dedupe_strings(_json_array(submission.get("final_tags"))),
        "redirect_url_snapshot": submission.get("redirect_url_snapshot", "") or "",
        "scrm_apply_status": (scrm_apply or {}).get("status", "") or "",
        "scrm_apply_error": (scrm_apply or {}).get("error_message", "") or "",
    }


def create_questionnaire(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_questionnaire_payload(payload)
    db = get_db()
    try:
        row = db.execute(
            """
            INSERT INTO questionnaires (
                slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                normalized["slug"],
                normalized["name"],
                normalized["title"],
                normalized["description"],
                normalized["is_disabled"],
                normalized["redirect_url"],
            ),
        ).fetchone()
        questionnaire_id = int(row["id"])
        _sync_questionnaire_questions(questionnaire_id, normalized["questions"])
        _sync_questionnaire_score_rules(questionnaire_id, normalized["score_rules"])
        db.commit()
        created = get_questionnaire_detail(questionnaire_id)
        if created is None:
            raise RuntimeError("questionnaire creation failed")
        return created
    except Exception:
        db.rollback()
        raise


def get_questionnaire_detail(questionnaire_id: int) -> dict[str, Any] | None:
    row = _get_questionnaire_row(int(questionnaire_id))
    if not row:
        return None
    return _build_questionnaire_detail(row)


def update_questionnaire(questionnaire_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    existing = _get_questionnaire_row(int(questionnaire_id))
    if not existing:
        return None
    normalized = _normalize_questionnaire_payload(payload, questionnaire_id=int(questionnaire_id), existing=existing)
    db = get_db()
    try:
        db.execute(
            """
            UPDATE questionnaires
            SET slug = ?, name = ?, title = ?, description = ?, is_disabled = ?, redirect_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                normalized["slug"],
                normalized["name"],
                normalized["title"],
                normalized["description"],
                normalized["is_disabled"],
                normalized["redirect_url"],
                int(questionnaire_id),
            ),
        )
        _sync_questionnaire_questions(int(questionnaire_id), normalized["questions"])
        _sync_questionnaire_score_rules(int(questionnaire_id), normalized["score_rules"])
        db.commit()
        return get_questionnaire_detail(int(questionnaire_id))
    except Exception:
        db.rollback()
        raise


def disable_questionnaire(questionnaire_id: int, is_disabled: bool = True) -> dict[str, Any] | None:
    db = get_db()
    db.execute(
        """
        UPDATE questionnaires
        SET is_disabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_normalize_bool(is_disabled), int(questionnaire_id)),
    )
    db.commit()
    return get_questionnaire_detail(int(questionnaire_id))


def delete_questionnaire(questionnaire_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM questionnaires WHERE id = ?", (int(questionnaire_id),))
    db.commit()
    return cursor.rowcount > 0


def _list_questionnaire_export_records(questionnaire_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    db = get_db()
    submission_rows = db.execute(
        """
        SELECT id, submitted_at, respondent_key, openid, unionid, external_userid, follow_user_userid,
               matched_by, source_channel, campaign_id, staff_id, total_score, final_tags
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    answer_rows = db.execute(
        """
        SELECT submission_id, question_id, question_type, question_title_snapshot,
               selected_option_texts_snapshot, text_value
        FROM questionnaire_submission_answers
        WHERE submission_id IN (
            SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ?
        )
        ORDER BY submission_id ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    return submission_rows, answer_rows


def _build_questionnaire_export_columns(
    questionnaire: dict[str, Any],
    answer_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_sort_order = {
        int(question["id"]): int(question.get("sort_order") or 0) for question in questionnaire["questions"]
    }
    if not answer_rows:
        return [
            {
                "question_id": int(question["id"]),
                "title": question["title"],
                "sort_order": int(question.get("sort_order") or 0),
            }
            for question in questionnaire["questions"]
        ]
    question_columns: list[dict[str, Any]] = []
    seen_question_ids: set[int] = set()
    for row in answer_rows:
        question_id = int(row["question_id"])
        if question_id in seen_question_ids:
            continue
        seen_question_ids.add(question_id)
        question_columns.append(
            {
                "question_id": question_id,
                "title": row.get("question_title_snapshot", "") or f"Question {question_id}",
                "sort_order": current_sort_order.get(question_id, 10_000 + len(question_columns)),
            }
        )
    question_columns.sort(key=lambda item: (item["sort_order"], item["question_id"]))
    return question_columns


def _build_questionnaire_export_answer_values(answer_rows: list[dict[str, Any]]) -> dict[int, dict[int, str]]:
    answer_values_by_submission: dict[int, dict[int, str]] = {}
    for row in answer_rows:
        submission_id = int(row["submission_id"])
        question_id = int(row["question_id"])
        question_type = row.get("question_type", "")
        if question_type in {"textarea", "mobile"}:
            cell_value = row.get("text_value", "") or ""
        else:
            cell_value = "/".join(_dedupe_strings(_json_array(row.get("selected_option_texts_snapshot"))))
        answer_values_by_submission.setdefault(submission_id, {})[question_id] = cell_value
    return answer_values_by_submission


def _build_questionnaire_export_row(
    questionnaire_name: str,
    submission: dict[str, Any],
    *,
    answer_map: dict[int, str],
    question_order: list[int],
) -> list[str]:
    return [
        submission.get("submitted_at", "") or "",
        questionnaire_name,
        submission.get("respondent_key", "") or "",
        submission.get("openid", "") or "",
        submission.get("unionid", "") or "",
        submission.get("external_userid", "") or "",
        submission.get("follow_user_userid", "") or "",
        submission.get("matched_by", "") or "",
        submission.get("source_channel", "") or "",
        submission.get("campaign_id", "") or "",
        submission.get("staff_id", "") or "",
        str(submission.get("total_score", "") or 0),
        "/".join(_dedupe_strings(_json_array(submission.get("final_tags")))),
        *[answer_map.get(question_id, "") for question_id in question_order],
    ]


def export_questionnaire_submissions(questionnaire_id: int) -> dict[str, Any]:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        raise LookupError("questionnaire not found")

    submission_rows, answer_rows = _list_questionnaire_export_records(int(questionnaire_id))
    question_columns = _build_questionnaire_export_columns(questionnaire, answer_rows)
    question_headers = [column["title"] for column in question_columns]
    question_order = [column["question_id"] for column in question_columns]
    answer_values_by_submission = _build_questionnaire_export_answer_values(answer_rows)
    headers = [
        "提交时间",
        "问卷名称",
        "respondent_key",
        "openid",
        "unionid",
        "external_userid",
        "follow_user_userid",
        "matched_by",
        "source_channel",
        "campaign_id",
        "staff_id",
        "总分",
        "最终标签",
        *question_headers,
    ]
    rows: list[list[str]] = []
    for submission in submission_rows:
        submission_id = int(submission["id"])
        rows.append(
            _build_questionnaire_export_row(
                questionnaire["name"],
                submission,
                answer_map=answer_values_by_submission.get(submission_id, {}),
                question_order=question_order,
            )
        )

    return {
        "questionnaire": questionnaire,
        "headers": headers,
        "rows": rows,
        "filename": f"questionnaire-{questionnaire['slug']}-submissions.xls",
    }


def get_public_questionnaire_by_slug(slug: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
        FROM questionnaires
        WHERE slug = ? AND is_disabled = ?
        LIMIT 1
        """,
        (slug.strip(), False),
    ).fetchone()
    if not row:
        return None
    detail = _build_questionnaire_detail(row)
    detail["questions"] = [
        {
            "id": question["id"],
            "type": question["type"],
            "title": question["title"],
            "required": question["required"],
            "sort_order": question["sort_order"],
            "options": [
                {
                    "id": option["id"],
                    "option_text": option["option_text"],
                    "sort_order": option["sort_order"],
                }
                for option in question["options"]
            ],
        }
        for question in detail["questions"]
    ]
    detail.pop("score_rules", None)
    detail.pop("submission_count", None)
    detail.pop("last_submitted_at", None)
    return detail


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
        from ...wecom_client import WeComClient

        client = WeComClient.from_app()
        result = client.mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=final_tags,
            remove_tags=None,
        )
        tags_repo.save_tag_snapshot(follow_user_userid, external_userid, final_tags)
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
