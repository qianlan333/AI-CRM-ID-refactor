from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import assert_repository_allowed


class QuestionnaireRepository(Protocol):
    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None: ...
    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]: ...
    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None: ...
    def delete_questionnaire(self, questionnaire_id: int) -> bool: ...
    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_submission(self, submission_id: str) -> dict[str, Any] | None: ...
    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None: ...


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        for item in self._questionnaires:
            if int(item["id"]) == int(questionnaire_id):
                return deepcopy(item)
        return None

    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None:
        slug = str(slug or "").strip()
        for item in self._questionnaires:
            if item.get("slug") == slug:
                return deepcopy(item)
        return None

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


_DEFAULT_REPO = InMemoryQuestionnaireRepository()


def build_questionnaire_repository() -> QuestionnaireRepository:
    return assert_repository_allowed(_DEFAULT_REPO, capability_owner="questionnaire")


def reset_questionnaire_fixture_state() -> None:
    _DEFAULT_REPO.reset()
