from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import assert_repository_allowed

from .domain import member_matches_filters
from .state_machine import POOL_DEFINITIONS, project_member, utc_now_iso


class AutomationRepository(Protocol):
    def list_pools(self) -> list[dict[str, Any]]: ...
    def list_members(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_member(self, member_id: str) -> dict[str, Any] | None: ...
    def find_member(self, *, external_userid: str | None = None, mobile: str | None = None, person_id: str | None = None) -> dict[str, Any] | None: ...
    def save_member(self, member: dict[str, Any]) -> dict[str, Any]: ...
    def append_history(self, member_id: str, event: dict[str, Any]) -> None: ...
    def list_history(self, member_id: str) -> list[dict[str, Any]]: ...
    def create_execution_record(self, record: dict[str, Any]) -> dict[str, Any]: ...
    def list_execution_records(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...


def _fixture_members() -> list[dict[str, Any]]:
    return [
        {
            "member_id": "member_001",
            "person_id": "person_001",
            "external_userid": "wx_ext_001",
            "mobile": "13800138000",
            "customer_name": "黄小璨学员 A",
            "owner_userid": "owner_001",
            "current_pool": "new_user",
            "followup_type": "normal",
            "questionnaire_followup_type": "normal",
            "manual_followup_type": "",
            "trial_opened": False,
            "activated": False,
            "converted": False,
            "exited": False,
            "silent": False,
            "latest_event_at": "2026-05-20T09:00:00Z",
            "history": [],
            "warnings": [],
        },
        {
            "member_id": "member_002",
            "person_id": "person_002",
            "external_userid": "wx_ext_002",
            "mobile": "13800138001",
            "customer_name": "黄小璨学员 B",
            "owner_userid": "owner_002",
            "current_pool": "unactivated_priority",
            "followup_type": "priority",
            "questionnaire_followup_type": "priority",
            "manual_followup_type": "",
            "trial_opened": True,
            "activated": False,
            "converted": False,
            "exited": False,
            "silent": False,
            "latest_event_at": "2026-05-20T09:30:00Z",
            "history": [
                {
                    "event_id": "hist_member_002_1",
                    "member_id": "member_002",
                    "before_pool": "new_user",
                    "after_pool": "unactivated_priority",
                    "trigger": "trial_opened",
                    "source": "fixture",
                    "operator": "system",
                    "reason": "fixture_seed",
                    "occurred_at": "2026-05-20T09:30:00Z",
                }
            ],
            "warnings": [],
        },
        {
            "member_id": "member_003",
            "person_id": "person_003",
            "external_userid": "wx_ext_003",
            "mobile": "13800138002",
            "customer_name": "黄小璨学员 C",
            "owner_userid": "",
            "current_pool": "silent",
            "followup_type": "normal",
            "questionnaire_followup_type": "normal",
            "manual_followup_type": "",
            "trial_opened": True,
            "activated": True,
            "converted": False,
            "exited": False,
            "silent": True,
            "latest_event_at": "2026-05-20T10:00:00Z",
            "history": [],
            "warnings": ["fixture_missing_owner"],
        },
    ]


class InMemoryAutomationRepository:
    def __init__(self, members: list[dict[str, Any]] | None = None) -> None:
        self._members = {item["member_id"]: deepcopy(item) for item in (members or _fixture_members())}
        self._execution_records: list[dict[str, Any]] = [
            {
                "id": "exec_001",
                "record_type": "state_transition",
                "member_id": "member_002",
                "trigger": "trial_opened",
                "status": "succeeded",
                "status_label": "已记录",
                "delivery_status": "fixture",
                "payload_preview": {"after_pool": "unactivated_priority"},
                "created_at": "2026-05-20T09:30:00Z",
            }
        ]

    def list_pools(self) -> list[dict[str, Any]]:
        return deepcopy(POOL_DEFINITIONS)

    def list_members(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = [project_member(member) for member in self._members.values()]
        filters = filters or {}
        rows = [item for item in rows if member_matches_filters(item, filters)]
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def get_member(self, member_id: str) -> dict[str, Any] | None:
        member = self._members.get(member_id)
        return project_member(member) if member else None

    def find_member(self, *, external_userid: str | None = None, mobile: str | None = None, person_id: str | None = None) -> dict[str, Any] | None:
        for member in self._members.values():
            if external_userid and member.get("external_userid") == external_userid:
                return project_member(member)
            if mobile and member.get("mobile") == mobile:
                return project_member(member)
            if person_id and member.get("person_id") == person_id:
                return project_member(member)
        return None

    def save_member(self, member: dict[str, Any]) -> dict[str, Any]:
        self._members[member["member_id"]] = deepcopy(project_member(member))
        return self.get_member(member["member_id"]) or deepcopy(member)

    def append_history(self, member_id: str, event: dict[str, Any]) -> None:
        if member_id in self._members:
            self._members[member_id].setdefault("history", []).append(deepcopy(event))

    def list_history(self, member_id: str) -> list[dict[str, Any]]:
        return deepcopy((self._members.get(member_id) or {}).get("history") or [])

    def create_member_from_questionnaire(self, payload: dict[str, Any]) -> dict[str, Any]:
        next_number = len(self._members) + 1
        member_id = f"member_{next_number:03d}"
        member = {
            "member_id": member_id,
            "person_id": payload.get("person_id") or f"person_fixture_{next_number:03d}",
            "external_userid": payload.get("external_userid") or "",
            "mobile": payload.get("mobile") or "",
            "customer_name": payload.get("customer_name") or "问卷提交用户",
            "owner_userid": "",
            "current_pool": "new_user",
            "followup_type": payload.get("followup_type") or "normal",
            "questionnaire_followup_type": payload.get("followup_type") or "normal",
            "manual_followup_type": "",
            "trial_opened": False,
            "activated": False,
            "converted": False,
            "exited": False,
            "silent": False,
            "latest_event_at": utc_now_iso(),
            "history": [],
            "warnings": ["fixture_created_from_questionnaire"],
        }
        self._members[member_id] = member
        return project_member(member)

    def create_execution_record(self, record: dict[str, Any]) -> dict[str, Any]:
        saved = deepcopy(record)
        saved.setdefault("id", f"exec_{len(self._execution_records) + 1:03d}")
        saved.setdefault("created_at", utc_now_iso())
        saved.setdefault("delivery_status", "fake")
        self._execution_records.insert(0, saved)
        return deepcopy(saved)

    def list_execution_records(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return deepcopy(self._execution_records[offset : offset + limit]), len(self._execution_records)


_fixture_repo = InMemoryAutomationRepository()


def build_automation_repository() -> AutomationRepository:
    return assert_repository_allowed(_fixture_repo, capability_owner="automation_engine")


def reset_automation_fixture_state() -> None:
    global _fixture_repo
    _fixture_repo = InMemoryAutomationRepository()


FixtureAutomationRepository = InMemoryAutomationRepository
