from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import RepositoryProviderError
from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url


class QuestionnaireRepository(Protocol):
    source_status: str
    read_model_status: str

    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None: ...
    def list_questions(self, questionnaire_id: int) -> list[dict[str, Any]] | None: ...
    def get_results_summary(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def list_submissions(self, questionnaire_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int] | None: ...
    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]: ...
    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None: ...
    def delete_questionnaire(self, questionnaire_id: int) -> bool: ...
    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_submission(self, submission_id: str) -> dict[str, Any] | None: ...
    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _json_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _initial_questionnaires() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "slug": "hxc-activation-v1",
            "title": "黄小璨激活问卷",
            "name": "黄小璨激活问卷",
            "description": "用于收集用户激活状态和后续运营标签。",
            "enabled": True,
            "redirect_url": "/s/hxc-activation-v1/submitted",
            "submit_button_text": "提交问卷",
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-20T10:00:00Z",
            "submission_count": 1,
            "assessment_enabled": False,
            "external_push_config": {
                "enabled": False,
                "status": "stubbed",
                "note": "第一阶段不真实外发 webhook。",
            },
            "questions": [
                {
                    "id": "q_activation",
                    "type": "single_choice",
                    "title": "黄小璨是否已激活？",
                    "required": True,
                    "options": [
                        {
                            "id": "activated",
                            "label": "已激活",
                            "value": "activated",
                            "tag_codes": ["tag_hxc_activated"],
                            "score": 10,
                        },
                        {
                            "id": "not_activated",
                            "label": "未激活",
                            "value": "not_activated",
                            "tag_codes": ["tag_hxc_not_activated"],
                            "score": 0,
                        },
                    ],
                },
                {
                    "id": "q_interest",
                    "type": "multi_choice",
                    "title": "你关注哪些能力？",
                    "required": False,
                    "options": [
                        {"id": "private_domain", "label": "私域运营", "value": "private_domain", "tag_codes": ["tag_interest_private_domain"], "score": 3},
                        {"id": "ai_tools", "label": "AI 工具", "value": "ai_tools", "tag_codes": ["tag_interest_ai_tools"], "score": 3},
                    ],
                },
                {
                    "id": "q_note",
                    "type": "textarea",
                    "title": "还有什么想补充？",
                    "required": False,
                    "options": [],
                    "placeholder_text": "可填写你最想解决的问题",
                },
            ],
        },
        {
            "id": 2,
            "slug": "disabled-demo",
            "title": "停用问卷样例",
            "name": "停用问卷样例",
            "description": "用于验证 disabled questionnaire contract。",
            "enabled": False,
            "redirect_url": "",
            "submit_button_text": "提交",
            "created_at": "2026-05-02T10:00:00Z",
            "updated_at": "2026-05-20T10:00:00Z",
            "submission_count": 0,
            "assessment_enabled": False,
            "external_push_config": {"enabled": False, "status": "stubbed"},
            "questions": [
                {
                    "id": "q_disabled",
                    "type": "single_choice",
                    "title": "停用问卷问题",
                    "required": True,
                    "options": [{"id": "yes", "label": "是", "value": "yes", "tag_codes": [], "score": 0}],
                }
            ],
        },
    ]


class InMemoryQuestionnaireRepository:
    source_status = "local_contract_probe"
    read_model_status = "fixture"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._questionnaires = _initial_questionnaires()
        self._submissions: list[dict[str, Any]] = [
            {
                "submission_id": "sub_fixture_001",
                "questionnaire_id": 1,
                "slug": "hxc-activation-v1",
                "answers": {"q_activation": "activated"},
                "respondent_identity": {"mobile": "mobile_masked_fixture"},
                "person_id": "person_fixture",
                "external_userid": "external_user_masked_fixture",
                "mobile": "mobile_masked_fixture",
                "score": 10,
                "final_tags": ["tag_hxc_activated"],
                "created_at": "2026-05-20T10:10:00Z",
            }
        ]
        self._next_id = max(item["id"] for item in self._questionnaires) + 1
        self._next_submission = len(self._submissions) + 1

    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = deepcopy(self._questionnaires)
        return rows[offset : offset + limit], len(rows)

    def _raw_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        for item in self._questionnaires:
            if int(item["id"]) == int(questionnaire_id):
                return item
        return None

    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        item = self._raw_questionnaire(questionnaire_id)
        if item is None:
            return None
        payload = deepcopy(item)
        payload["submissions_summary"] = self.get_results_summary(questionnaire_id) or {}
        payload["submissions"] = (self.list_submissions(questionnaire_id, limit=10, offset=0) or ([], 0))[0]
        return payload

    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None:
        slug = str(slug or "").strip()
        for item in self._questionnaires:
            if item.get("slug") == slug:
                return deepcopy(item)
        return None

    def list_questions(self, questionnaire_id: int) -> list[dict[str, Any]] | None:
        item = self._raw_questionnaire(questionnaire_id)
        if not item:
            return None
        return deepcopy(item.get("questions") or [])

    def get_results_summary(self, questionnaire_id: int) -> dict[str, Any] | None:
        item = self._raw_questionnaire(questionnaire_id)
        if not item:
            return None
        rows = [submission for submission in self._submissions if int(submission.get("questionnaire_id") or 0) == int(questionnaire_id)]
        return {
            "questionnaire_id": int(questionnaire_id),
            "submission_count": len(rows),
            "latest_submitted_at": rows[-1].get("created_at") if rows else "",
            "average_score": sum(float(row.get("score") or 0) for row in rows) / len(rows) if rows else 0,
            "result_config": deepcopy(item.get("result_config") or {}),
            "rules": deepcopy(item.get("rules") or []),
        }

    def list_submissions(self, questionnaire_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int] | None:
        if not self._raw_questionnaire(questionnaire_id):
            return None
        rows = [deepcopy(item) for item in self._submissions if int(item.get("questionnaire_id") or 0) == int(questionnaire_id)]
        return rows[int(offset) : int(offset) + int(limit)], len(rows)

    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]:
        now = _now()
        if questionnaire_id is None:
            item = {
                "id": self._next_id,
                "slug": str(payload.get("slug") or f"questionnaire-{self._next_id}").strip(),
                "created_at": now,
                "submission_count": 0,
                "assessment_enabled": False,
            }
            self._next_id += 1
            self._questionnaires.append(item)
        else:
            item = next((entry for entry in self._questionnaires if int(entry["id"]) == int(questionnaire_id)), None)
            if item is None:
                return {}
        item.update(
            {
                "title": str(payload.get("title") or item.get("title") or "").strip(),
                "name": str(payload.get("title") or item.get("name") or "").strip(),
                "description": str(payload.get("description") or ""),
                "enabled": bool(payload.get("enabled", item.get("enabled", True))),
                "redirect_url": str(payload.get("redirect_url") or ""),
                "submit_button_text": str(payload.get("submit_button_text") or "提交"),
                "updated_at": now,
                "questions": deepcopy(payload.get("questions") or item.get("questions") or []),
                "external_push_config": deepcopy(payload.get("external_push_config") or item.get("external_push_config") or {}),
            }
        )
        return deepcopy(item)

    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None:
        item = next((entry for entry in self._questionnaires if int(entry["id"]) == int(questionnaire_id)), None)
        if item is None:
            return None
        item["enabled"] = bool(enabled)
        item["updated_at"] = _now()
        return deepcopy(item)

    def delete_questionnaire(self, questionnaire_id: int) -> bool:
        before = len(self._questionnaires)
        self._questionnaires = [item for item in self._questionnaires if int(item["id"]) != int(questionnaire_id)]
        return len(self._questionnaires) < before

    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        submission = deepcopy(payload)
        submission["submission_id"] = submission.get("submission_id") or f"sub_next_{self._next_submission:03d}"
        submission["created_at"] = submission.get("created_at") or _now()
        self._next_submission += 1
        self._submissions.append(submission)
        for item in self._questionnaires:
            if int(item["id"]) == int(submission["questionnaire_id"]):
                item["submission_count"] = int(item.get("submission_count") or 0) + 1
                item["updated_at"] = _now()
        return deepcopy(submission)

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        for item in self._submissions:
            if item.get("submission_id") == submission_id:
                return deepcopy(item)
        return None

    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None:
        for item in reversed(self._submissions):
            if int(item.get("questionnaire_id") or 0) == int(questionnaire_id):
                return deepcopy(item)
        return None

    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None:
        if not self.get_questionnaire(questionnaire_id):
            return None
        rows = [item for item in self._submissions if int(item.get("questionnaire_id") or 0) == int(questionnaire_id)]
        return {
            "filename": f"questionnaire_{questionnaire_id}_submissions.json",
            "items": deepcopy(rows),
            "total": len(rows),
            "format": "json",
        }


class PostgresQuestionnaireReadRepository:
    source_status = "next_read_model"
    read_model_status = "primary"

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())
        if not self._database_url:
            raise RepositoryProviderError("questionnaire production read repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - dependency failure varies by runtime
            raise RepositoryProviderError("psycopg is required for questionnaire production read repository") from exc
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _questionnaire_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        enabled = not bool(row.get("is_disabled"))
        external_push_config = {
            "enabled": bool(row.get("external_push_enabled")),
            "webhook_url": _text(row.get("external_push_url")),
            "type": _text(row.get("external_push_type")),
            "expires_at_ts": row.get("external_push_expires_at_ts"),
            "day": row.get("external_push_day"),
            "frequency": row.get("external_push_frequency"),
            "remark": _text(row.get("external_push_remark")),
            "custom_params": _json_list(row.get("external_push_custom_params")),
        }
        return {
            "id": int(row["id"]),
            "slug": _text(row.get("slug")),
            "name": _text(row.get("name")),
            "title": _text(row.get("title") or row.get("name")),
            "description": _text(row.get("description")),
            "enabled": enabled,
            "is_disabled": not enabled,
            "status": "disabled" if not enabled else "published",
            "version": int(row.get("version") or 1),
            "redirect_url": _text(row.get("redirect_url")),
            "answer_display_mode": _text(row.get("answer_display_mode") or "all_in_one"),
            "assessment_enabled": bool(row.get("assessment_enabled")),
            "assessment_config": _json_dict(row.get("assessment_config")),
            "result_config": _json_dict(row.get("assessment_config")),
            "external_push_config": external_push_config,
            "external_push_enabled": external_push_config["enabled"],
            "external_push_url": external_push_config["webhook_url"],
            "external_push_type": external_push_config["type"],
            "external_push_expires_at_ts": external_push_config["expires_at_ts"],
            "external_push_day": external_push_config["day"],
            "external_push_frequency": external_push_config["frequency"],
            "external_push_remark": external_push_config["remark"],
            "external_push_custom_params": external_push_config["custom_params"],
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
            "question_count": int(row.get("question_count") or 0),
            "submission_count": int(row.get("submission_count") or 0),
            "last_submitted_at": _timestamp(row.get("last_submitted_at")),
            "questions": [],
            "rules": [],
            "score_rules": [],
            "submissions_summary": {},
            "submissions": [],
        }

    def _base_select(self) -> str:
        return """
            SELECT
                q.*,
                1 AS version,
                COALESCE(question_counts.question_count, 0) AS question_count,
                COALESCE(submission_counts.submission_count, 0) AS submission_count,
                submission_counts.last_submitted_at AS last_submitted_at
            FROM questionnaires q
            LEFT JOIN (
                SELECT questionnaire_id, COUNT(*) AS question_count
                FROM questionnaire_questions
                GROUP BY questionnaire_id
            ) question_counts ON question_counts.questionnaire_id = q.id
            LEFT JOIN (
                SELECT questionnaire_id, COUNT(*) AS submission_count, MAX(submitted_at) AS last_submitted_at
                FROM questionnaire_submissions
                GROUP BY questionnaire_id
            ) submission_counts ON submission_counts.questionnaire_id = q.id
        """

    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as conn:
            total = int((conn.execute("SELECT COUNT(*) AS total FROM questionnaires").fetchone() or {}).get("total") or 0)
            rows = conn.execute(
                self._base_select() + " ORDER BY q.updated_at DESC, q.id DESC LIMIT %s OFFSET %s",
                (int(limit), int(offset)),
            ).fetchall()
        return [self._questionnaire_from_row(dict(row)) for row in rows], total

    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(self._base_select() + " WHERE q.id = %s", (int(questionnaire_id),)).fetchone()
        if not row:
            return None
        item = self._questionnaire_from_row(dict(row))
        item["questions"] = self.list_questions(questionnaire_id) or []
        item["rules"] = self._list_score_rules(questionnaire_id)
        item["score_rules"] = deepcopy(item["rules"])
        item["submissions_summary"] = self.get_results_summary(questionnaire_id) or {}
        submissions = self.list_submissions(questionnaire_id, limit=10, offset=0)
        item["submissions"] = submissions[0] if submissions else []
        return item

    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(self._base_select() + " WHERE q.slug = %s", (str(slug or "").strip(),)).fetchone()
        if not row:
            return None
        return self.get_questionnaire(int(row["id"]))

    def list_questions(self, questionnaire_id: int) -> list[dict[str, Any]] | None:
        if not self._exists(questionnaire_id):
            return None
        with self._connect() as conn:
            question_rows = conn.execute(
                """
                SELECT *
                FROM questionnaire_questions
                WHERE questionnaire_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (int(questionnaire_id),),
            ).fetchall()
            option_rows = conn.execute(
                """
                SELECT qo.*
                FROM questionnaire_options qo
                JOIN questionnaire_questions qq ON qq.id = qo.question_id
                WHERE qq.questionnaire_id = %s
                ORDER BY qo.sort_order ASC, qo.id ASC
                """,
                (int(questionnaire_id),),
            ).fetchall()
        options_by_question: dict[int, list[dict[str, Any]]] = {}
        for row in option_rows:
            payload = dict(row)
            question_id = int(payload.get("question_id") or 0)
            options_by_question.setdefault(question_id, []).append(
                {
                    "id": int(payload["id"]),
                    "label": _text(payload.get("option_text")),
                    "value": _text(payload.get("id")),
                    "option_text": _text(payload.get("option_text")),
                    "score": int(float(payload.get("score") or 0)),
                    "tag_codes": _json_list(payload.get("tag_codes")),
                    "sort_order": int(payload.get("sort_order") or 0),
                }
            )
        questions: list[dict[str, Any]] = []
        for row in question_rows:
            payload = dict(row)
            question_id = int(payload["id"])
            questions.append(
                {
                    "id": question_id,
                    "type": _text(payload.get("type") or "single_choice"),
                    "title": _text(payload.get("title")),
                    "required": bool(payload.get("required")),
                    "placeholder_text": _text(payload.get("placeholder_text")),
                    "assessment_dimension_key": _text(payload.get("assessment_dimension_key")),
                    "sidebar_profile_field": _text(payload.get("sidebar_profile_field")),
                    "sort_order": int(payload.get("sort_order") or 0),
                    "created_at": _timestamp(payload.get("created_at")),
                    "updated_at": _timestamp(payload.get("updated_at")),
                    "options": options_by_question.get(question_id, []),
                }
            )
        return questions

    def get_results_summary(self, questionnaire_id: int) -> dict[str, Any] | None:
        if not self._exists(questionnaire_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS submission_count,
                    MAX(submitted_at) AS latest_submitted_at,
                    COALESCE(AVG(total_score), 0) AS average_score
                FROM questionnaire_submissions
                WHERE questionnaire_id = %s
                """,
                (int(questionnaire_id),),
            ).fetchone()
        return {
            "questionnaire_id": int(questionnaire_id),
            "submission_count": int((row or {}).get("submission_count") or 0),
            "latest_submitted_at": _timestamp((row or {}).get("latest_submitted_at")),
            "average_score": float((row or {}).get("average_score") or 0),
            "rules": self._list_score_rules(questionnaire_id),
        }

    def list_submissions(self, questionnaire_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int] | None:
        if not self._exists(questionnaire_id):
            return None
        with self._connect() as conn:
            total = int(
                (conn.execute("SELECT COUNT(*) AS total FROM questionnaire_submissions WHERE questionnaire_id = %s", (int(questionnaire_id),)).fetchone() or {}).get("total")
                or 0
            )
            rows = conn.execute(
                """
                SELECT id, questionnaire_id, respondent_key, openid, unionid, external_userid,
                       follow_user_userid, matched_by, mobile_snapshot, source_channel, campaign_id,
                       staff_id, total_score, final_tags, result_token, redirect_url_snapshot,
                       submitted_at
                FROM questionnaire_submissions
                WHERE questionnaire_id = %s
                ORDER BY submitted_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (int(questionnaire_id), int(limit), int(offset)),
            ).fetchall()
        items = [
            {
                **dict(row),
                "submission_id": str(row.get("id")),
                "submitted_at": _timestamp(row.get("submitted_at")),
                "final_tags": _json_list(row.get("final_tags")),
                "score": float(row.get("total_score") or 0),
            }
            for row in rows
        ]
        return items, total

    def _exists(self, questionnaire_id: int) -> bool:
        with self._connect() as conn:
            return bool(conn.execute("SELECT 1 FROM questionnaires WHERE id = %s", (int(questionnaire_id),)).fetchone())

    def _list_score_rules(self, questionnaire_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
                FROM questionnaire_score_rules
                WHERE questionnaire_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (int(questionnaire_id),),
            ).fetchall()
        return [
            {
                **dict(row),
                "tag_codes": _json_list(row.get("tag_codes")),
                "created_at": _timestamp(row.get("created_at")),
                "updated_at": _timestamp(row.get("updated_at")),
            }
            for row in rows
        ]

    # Write/export behavior remains intentionally outside the admin-read replacement.
    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]:
        raise RepositoryProviderError("questionnaire writes remain out of scope for the admin read replacement")

    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None:
        raise RepositoryProviderError("questionnaire enable/disable remains out of scope for the admin read replacement")

    def delete_questionnaire(self, questionnaire_id: int) -> bool:
        raise RepositoryProviderError("questionnaire delete remains out of scope for the admin read replacement")

    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RepositoryProviderError("questionnaire submit remains out of scope for the admin read replacement")

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        return None

    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None:
        submissions = self.list_submissions(questionnaire_id, limit=1, offset=0)
        if not submissions or not submissions[0]:
            return None
        return submissions[0][0]

    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None:
        raise RepositoryProviderError("questionnaire export remains out of scope for the admin read replacement")


_DEFAULT_REPO = InMemoryQuestionnaireRepository()


def build_questionnaire_repository() -> QuestionnaireRepository:
    if production_data_ready():
        return assert_repository_allowed(PostgresQuestionnaireReadRepository(), capability_owner="questionnaire")
    return assert_repository_allowed(_DEFAULT_REPO, capability_owner="questionnaire")


def reset_questionnaire_fixture_state() -> None:
    _DEFAULT_REPO.reset()
