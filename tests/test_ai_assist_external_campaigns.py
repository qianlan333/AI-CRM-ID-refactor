from __future__ import annotations

import json
from typing import Any

from fastapi.responses import JSONResponse

from aicrm_next.ai_assist import external_campaigns as service
from aicrm_next.platform_foundation.external_effects import AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK, ExternalEffectService, reset_external_effect_fixture_state


def _json_response_payload(response: Any) -> dict[str, Any]:
    assert isinstance(response, JSONResponse)
    return json.loads(response.body.decode("utf-8"))


class FakeExternalCampaignRepository:
    def __init__(self) -> None:
        self.pool_rows: dict[str, dict[str, Any]] = {}
        self.member_rows: dict[str, dict[str, Any]] = {}
        self.contact_rows: dict[str, dict[str, Any]] = {}
        self.backfill_rows: dict[str, dict[str, Any]] = {}
        self.campaigns_by_code: dict[str, dict[str, Any]] = {}
        self.campaigns_by_id: dict[int, dict[str, Any]] = {}
        self.segments_by_code: dict[str, dict[str, Any]] = {}
        self.overview: dict[str, Any] | None = None
        self.allocate_result: dict[str, Any] | None = None
        self.calls: list[str] = []
        self.write_calls: list[str] = []
        self.cleanup_calls: list[int] = []
        self.steps: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self.real_outbound_send_called = False
        self._campaign_id = 100
        self._segment_id = 200
        self._campaign_segment_id = 300

    def table_columns(self, table_name: str) -> set[str]:
        return {
            "id",
            "unionid",
            "owner_staff_id",
            "current_step_index",
            "trace_id",
            "master_customer_id",
            "source_type",
        }

    def fetch_user_ops_pool_current_row(self, external_userid: str) -> dict[str, Any]:
        self.calls.append("fetch_user_ops_pool_current_row")
        return dict(self.pool_rows.get(external_userid) or {})

    def fetch_contact_row(self, external_userid: str) -> dict[str, Any]:
        self.calls.append("fetch_contact_row")
        return dict(self.contact_rows.get(external_userid) or {})

    def get_campaign_by_code(self, campaign_code: str) -> dict[str, Any] | None:
        self.calls.append("get_campaign_by_code")
        item = self.campaigns_by_code.get(campaign_code)
        return dict(item) if item else None

    def get_campaign_by_id(self, campaign_id: int) -> dict[str, Any] | None:
        item = self.campaigns_by_id.get(int(campaign_id))
        return dict(item) if item else None

    def count_open_campaign_jobs(self, campaign_id: int) -> int:
        self.calls.append("count_open_campaign_jobs")
        return 0

    def get_segment_by_code(self, segment_code: str) -> dict[str, Any] | None:
        item = self.segments_by_code.get(segment_code)
        return dict(item) if item else None

    def create_or_update_external_segment(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_or_update_external_segment")
        self.write_calls.append("create_or_update_external_segment")
        code = kwargs["segment_code"]
        self._segment_id += 1
        segment = {
            "id": self._segment_id,
            "segment_code": code,
            "cached_headcount": int(kwargs.get("headcount") or 1),
            "status": "active",
            "source_type": "external_campaign",
            "sql_params": kwargs.get("sql_params") or {},
        }
        self.segments_by_code[code] = segment
        return dict(segment)

    def create_campaign_draft(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_campaign_draft")
        self.write_calls.append("create_campaign_draft")
        self._campaign_id += 1
        campaign = {
            "id": self._campaign_id,
            "campaign_code": kwargs["campaign_code"],
            "review_status": "draft",
            "run_status": "draft",
            "trace_id": kwargs.get("trace_id", ""),
        }
        self.campaigns_by_code[kwargs["campaign_code"]] = campaign
        self.campaigns_by_id[self._campaign_id] = campaign
        return dict(campaign)

    def add_segment_to_campaign(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("add_segment_to_campaign")
        self.write_calls.append("add_segment_to_campaign")
        self._campaign_segment_id += 1
        return {"id": self._campaign_segment_id, "segment_id": self._segment_id}

    def add_step_to_campaign(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("add_step_to_campaign")
        self.write_calls.append("add_step_to_campaign")
        self.steps.append(dict(kwargs))
        return {"campaign_segment_id": kwargs["campaign_segment_id"], "step_index": kwargs["step_index"]}

    def allocate_campaign_members(self, campaign_id: int) -> dict[str, Any]:
        self.calls.append("allocate_campaign_members")
        self.write_calls.append("allocate_campaign_members")
        if self.allocate_result is not None:
            return dict(self.allocate_result)
        return {"campaign_id": campaign_id, "allocated": 1, "skipped_collisions": 0, "errors": []}

    def submit_campaign_for_review(self, campaign_id: int, operator: str) -> dict[str, Any]:
        self.calls.append("submit_campaign_for_review")
        self.write_calls.append("submit_campaign_for_review")
        campaign = self.campaigns_by_id[int(campaign_id)]
        campaign["review_status"] = "pending_review"
        campaign["run_status"] = "draft"
        return dict(campaign)

    def delete_campaign(self, campaign_id: int) -> dict[str, Any]:
        self.calls.append("delete_campaign")
        self.write_calls.append("delete_campaign")
        self.cleanup_calls.append(int(campaign_id))
        return {"ok": True, "deleted_id": int(campaign_id)}

    def assemble_campaign_overview(self, campaign_id: int) -> dict[str, Any]:
        self.calls.append("assemble_campaign_overview")
        if self.overview is not None:
            return dict(self.overview)
        campaign = self.campaigns_by_id.get(int(campaign_id)) or {"id": int(campaign_id), "campaign_code": "camp"}
        return {
            "campaign": dict(campaign),
            "segments": [{"segment_code": "seg", "allocated_count": 1, "steps": []}],
            "member_status_counts": {"pending": 1},
            "total_members": 1,
        }

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _payload(**extra: Any) -> dict[str, Any]:
    payload = {
        "owner_userid": "owner_1",
        "external_userid": "ext_1",
        "scheduled_for": "2026-06-09 10:30",
        "message": "hello",
        "idempotency_key": "idem_1",
        "group_code": "group_1",
    }
    payload.update(extra)
    return payload


def _repo_with_target(external_userid: str = "ext_1") -> FakeExternalCampaignRepository:
    repo = FakeExternalCampaignRepository()
    repo.pool_rows[external_userid] = {"external_userid": external_userid, "owner_userid": "owner_1"}
    repo.contact_rows[external_userid] = {"external_userid": external_userid, "owner_userid": "owner_1"}
    return repo


def test_external_campaign_token_required(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_EXTERNAL_CAMPAIGN_TOKEN", raising=False)
    monkeypatch.delenv("AUTOMATION_INTERNAL_API_TOKEN", raising=False)
    assert _json_response_payload(service.create_external_campaigns_response(_payload(), headers={}))["error"] == "external_campaign_token_not_configured"

    monkeypatch.setenv("AICRM_EXTERNAL_CAMPAIGN_TOKEN", "secret")
    assert _json_response_payload(service.create_external_campaigns_response(_payload(), headers={}))["error"] == "missing_internal_token"
    assert _json_response_payload(service.create_external_campaigns_response(_payload(), headers={"Authorization": "Bearer bad"}))["error"] == "invalid_internal_token"

    monkeypatch.setattr(service, "create_external_campaigns", lambda payload: {"ok": True, "entered": True})
    assert service.create_external_campaigns_response(_payload(), headers={"Authorization": "Bearer secret"}) == {"ok": True, "entered": True}


def test_external_campaign_dry_run_preview_no_write() -> None:
    reset_external_effect_fixture_state()
    repo = _repo_with_target()
    result = service.create_external_campaigns(_payload(dry_run=True), repo=repo)
    _items, total = ExternalEffectService().list_jobs({"effect_type": AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK})

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["side_effect_executed"] is False
    assert result["campaigns"][0]["would_create"] is True
    assert repo.write_calls == []
    assert total == 0


def test_external_campaign_create_single_recipient_success() -> None:
    reset_external_effect_fixture_state()
    repo = _repo_with_target()
    result = service.create_external_campaigns(_payload(), repo=repo)
    _items, total = ExternalEffectService().list_jobs({"effect_type": AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK})

    campaign = result["campaigns"][0]
    assert campaign["status"] == "created"
    assert campaign["review_status"] == "pending_review"
    assert campaign["run_status"] == "draft"
    assert result["created_count"] == 1
    assert campaign["requires_human_review"] is True
    assert campaign["scheduled_jobs"] == 0
    assert repo.write_calls == [
        "create_or_update_external_segment",
        "create_campaign_draft",
        "add_segment_to_campaign",
        "add_step_to_campaign",
        "allocate_campaign_members",
        "submit_campaign_for_review",
    ]
    assert repo.real_outbound_send_called is False
    assert total == 0


def test_external_campaign_allows_attachment_only_step() -> None:
    repo = _repo_with_target()
    payload = _payload(
        message="",
        steps=[
            {
                "scheduled_for": "2026-06-09 10:30",
                "content_payload": {"miniprogram_library_ids": [17]},
            }
        ],
    )

    result = service.create_external_campaigns(payload, repo=repo)

    assert result["created_count"] == 1
    assert repo.steps[0]["content_text"] == ""
    assert repo.steps[0]["content_payload"] == {"miniprogram_library_ids": [17]}


def test_campaign_private_broadcast_job_fields_are_complete() -> None:
    from aicrm_next.cloud_orchestrator.repository import (
        _campaign_private_broadcast_job_extra_fields,
        _campaign_private_broadcast_payload,
    )

    columns, placeholders, params = _campaign_private_broadcast_job_extra_fields(
        {"business_domain", "channel", "target_kind"}
    )
    payload = _campaign_private_broadcast_payload(
        campaign={"owner_userid": "owner_1"},
        step={"content_text": "", "content_payload_json": {"miniprogram_library_ids": [17]}},
        members=[{"unionid": "union_1"}],
    )

    assert columns == ["business_domain", "channel", "target_kind"]
    assert placeholders == ["%s", "%s", "%s"]
    assert params == ["automation_ops", "wecom_private", "unionid"]
    assert payload["channel"] == "wecom_private"
    assert payload["target_kind"] == "unionid"
    assert payload["step"]["content_payload_json"] == {"miniprogram_library_ids": [17]}


def test_external_campaign_idempotent_existing_campaign() -> None:
    repo = _repo_with_target()
    repo.campaigns_by_code["fixed_code"] = {"id": 9, "campaign_code": "fixed_code", "review_status": "pending_review", "run_status": "draft"}
    result = service.create_external_campaigns(_payload(campaign_code="fixed_code"), repo=repo)

    assert result["campaigns"][0]["status"] == "exists"
    assert "create_campaign_draft" not in repo.write_calls


def test_external_campaign_target_not_found() -> None:
    repo = FakeExternalCampaignRepository()

    try:
        service.create_external_campaigns(_payload(), repo=repo)
    except service.ExternalCampaignError as exc:
        payload = exc.to_response()
        status_code = exc.status_code
    else:  # pragma: no cover
        raise AssertionError("expected ExternalCampaignError")

    assert payload["error"] == "target_not_found"
    assert payload["phase"] == "target_lookup"
    assert status_code == 404


def test_external_campaign_owner_mismatch() -> None:
    repo = FakeExternalCampaignRepository()
    repo.contact_rows["ext_1"] = {"external_userid": "ext_1", "owner_userid": "owner_2"}

    try:
        service.create_external_campaigns(_payload(), repo=repo)
    except service.ExternalCampaignError as exc:
        payload = exc.to_response()
        status_code = exc.status_code
    else:  # pragma: no cover
        raise AssertionError("expected ExternalCampaignError")

    assert payload["error"] == "owner_mismatch"
    assert status_code == 409


def test_external_campaign_automation_member_backfill_is_retired() -> None:
    repo = FakeExternalCampaignRepository()
    repo.backfill_rows["ext_1"] = {"source": "sidebar_binding", "owner_userid": "owner_1", "customer_name": "Alice"}

    try:
        service.create_external_campaigns(_payload(dry_run=True, auto_backfill_automation_member=True), repo=repo)
    except service.ExternalCampaignError as exc:
        payload = exc.to_response()
        status_code = exc.status_code
    else:  # pragma: no cover
        raise AssertionError("expected ExternalCampaignError")

    assert status_code == 410
    assert payload["error"] == "automation_member_backfill_retired"
    assert "insert_automation_member" not in repo.write_calls
    assert repo.write_calls == []


def test_external_campaign_multi_recipient_campaign_code_suffix() -> None:
    repo = _repo_with_target("ext_1")
    repo.pool_rows["ext_2"] = {"external_userid": "ext_2", "owner_userid": "owner_1"}
    repo.contact_rows["ext_2"] = {"external_userid": "ext_2", "owner_userid": "owner_1"}
    result = service.create_external_campaigns(
        _payload(campaign_code="fixed_code", recipients=["ext_1", "ext_2"]),
        repo=repo,
    )

    codes = [item["campaign_code"] for item in result["campaigns"]]
    assert len(codes) == 2
    assert len(set(codes)) == 2
    assert all(code.startswith("fixed_code_") for code in codes)


def test_external_campaign_allocation_failure_cleans_up() -> None:
    repo = _repo_with_target()
    repo.allocate_result = {"campaign_id": 101, "allocated": 0, "errors": [{"reason": "empty"}]}

    try:
        service.create_external_campaigns(_payload(), repo=repo)
    except service.ExternalCampaignError as exc:
        payload = exc.to_response()
    else:  # pragma: no cover
        raise AssertionError("expected ExternalCampaignError")

    assert payload["error"] == "campaign_member_allocation_failed"
    assert payload["cleanup_ok"] is True
    assert repo.cleanup_calls


def test_external_campaign_status_uses_next_repo() -> None:
    repo = FakeExternalCampaignRepository()
    repo.campaigns_by_code["camp_1"] = {"id": 7, "campaign_code": "camp_1", "review_status": "pending_review", "run_status": "draft"}
    repo.campaigns_by_id[7] = repo.campaigns_by_code["camp_1"]
    result = service.get_external_campaign_status("camp_1", repo=repo)

    assert result["ok"] is True
    assert result["campaign"]["campaign_code"] == "camp_1"
    assert result["segments"]
    assert result["member_status_counts"] == {"pending": 1}
    assert result["scheduled_jobs"] == 0
    assert "assemble_campaign_overview" in repo.calls


def test_external_campaign_status_not_found() -> None:
    repo = FakeExternalCampaignRepository()

    try:
        service.get_external_campaign_status("missing", repo=repo)
    except service.ExternalCampaignError as exc:
        payload = exc.to_response()
        status_code = exc.status_code
    else:  # pragma: no cover
        raise AssertionError("expected ExternalCampaignError")

    assert payload["error"] == "campaign_not_found"
    assert status_code == 404
