from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.admin_jobs.routes import ensure_admin_action_token
from aicrm_next.cloud_orchestrator.repository import build_cloud_plan_repository
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "cloud-plan-recipient-test")
    return TestClient(create_app())


def _token_headers() -> dict[str, str]:
    return {
        "X-Admin-Action-Token": ensure_admin_action_token(),
        "X-Admin-Operator": "tester",
    }


def _approve_plan(client: TestClient, plan_id: str = "plan_probe"):
    return client.post(f"/api/admin/cloud-orchestrator/plans/{plan_id}/approve", headers=_token_headers())


def test_plan_list_is_lightweight_and_omits_nested_payloads(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/admin/cloud-orchestrator/plans?limit=20&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"ok", "plans", "limit", "offset", "total"}
    assert payload["ok"] is True
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert payload["total"] == 4
    assert payload["plans"][0]["plan_id"] == "plan_probe"
    assert payload["plans"][0]["target_count"] == 2
    for plan in payload["plans"]:
        assert "recipients" not in plan
        assert "messages" not in plan
        assert "content_payload" not in plan
        assert "selection_json" not in plan


def test_plan_list_pagination_keyword_status_and_empty_state(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    first_page = client.get("/api/admin/cloud-orchestrator/plans?limit=2&offset=0").json()
    second_page = client.get("/api/admin/cloud-orchestrator/plans?limit=2&offset=2").json()
    clamped = client.get("/api/admin/cloud-orchestrator/plans?limit=999&offset=0").json()
    by_name = client.get("/api/admin/cloud-orchestrator/plans?keyword=高意向").json()
    by_plan_id = client.get("/api/admin/cloud-orchestrator/plans?keyword=plan_rejected").json()
    by_owner = client.get("/api/admin/cloud-orchestrator/plans?keyword=EmptyOwner").json()
    pending = client.get("/api/admin/cloud-orchestrator/plans?status=pending_review").json()
    approved = client.get("/api/admin/cloud-orchestrator/plans?status=approved").json()
    rejected = client.get("/api/admin/cloud-orchestrator/plans?status=rejected").json()
    active = client.get("/api/admin/cloud-orchestrator/plans?status=active").json()

    assert [item["plan_id"] for item in first_page["plans"]] == ["plan_probe", "plan_approved"]
    assert [item["plan_id"] for item in second_page["plans"]] == ["plan_rejected", "plan_empty"]
    assert clamped["limit"] == 100
    assert [item["plan_id"] for item in by_name["plans"]] == ["plan_approved"]
    assert [item["plan_id"] for item in by_plan_id["plans"]] == ["plan_rejected"]
    assert [item["plan_id"] for item in by_owner["plans"]] == ["plan_empty"]
    assert [item["plan_id"] for item in pending["plans"]] == ["plan_probe", "plan_empty"]
    assert [item["plan_id"] for item in approved["plans"]] == ["plan_approved"]
    assert [item["plan_id"] for item in rejected["plans"]] == ["plan_rejected"]
    assert [item["plan_id"] for item in active["plans"]] == ["plan_approved"]

    repo.plans.clear()
    repo.recipients.clear()
    empty = client.get("/api/admin/cloud-orchestrator/plans").json()
    assert empty["plans"] == []
    assert empty["total"] == 0


def test_plan_detail_summary_has_counts_and_no_nested_rows(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/admin/cloud-orchestrator/plans/plan_approved")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["target_count"] == 4
    assert payload["plan"]["approved_count"] == 3
    assert payload["plan"]["pending_count"] == 0
    assert payload["plan"]["rejected_count"] == 1
    assert payload["plan"]["sent_count"] == 1
    assert payload["plan"]["failed_count"] == 1
    assert payload["stats"] == {
        "target_count": 4,
        "approved_count": 3,
        "pending_count": 0,
        "rejected_count": 1,
        "sent_count": 1,
        "failed_count": 1,
    }
    assert "recipients" not in payload["plan"]
    assert "messages" not in payload["plan"]


def test_plan_detail_404_and_rejected_plan_blocks_recipient_approve(monkeypatch):
    client = _client(monkeypatch)

    missing = client.get("/api/admin/cloud-orchestrator/plans/missing")
    rejected = client.post("/api/admin/cloud-orchestrator/plans/plan_rejected/recipients/999/approve", headers=_token_headers())

    assert missing.status_code == 404
    assert rejected.status_code == 409
    assert "plan is rejected" in rejected.json()["detail"]


def test_recipient_list_paginates_filters_and_omits_messages(monkeypatch):
    client = _client(monkeypatch)

    first_page = client.get("/api/admin/cloud-orchestrator/plans/plan_approved/recipients?limit=2&offset=0").json()
    second_page = client.get("/api/admin/cloud-orchestrator/plans/plan_approved/recipients?limit=2&offset=2").json()
    pending = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients?status=pending").json()
    approved = client.get("/api/admin/cloud-orchestrator/plans/plan_approved/recipients?status=approved").json()
    sent = client.get("/api/admin/cloud-orchestrator/plans/plan_approved/recipients?status=sent").json()
    empty = client.get("/api/admin/cloud-orchestrator/plans/plan_empty/recipients").json()
    missing = client.get("/api/admin/cloud-orchestrator/plans/missing/recipients")

    assert first_page["total"] == 4
    assert [row["recipient_id"] for row in first_page["rows"]] == [3, 4]
    assert [row["recipient_id"] for row in second_page["rows"]] == [5, 6]
    assert len(first_page["rows"]) <= 2
    assert "messages" not in first_page["rows"][0]
    assert [row["recipient_id"] for row in pending["rows"]] == [1, 2]
    assert [row["recipient_id"] for row in approved["rows"]] == [3, 4, 5]
    assert [row["recipient_id"] for row in sent["rows"]] == [4]
    assert empty["rows"] == []
    assert empty["total"] == 0
    assert missing.status_code == 404


def test_recipient_detail_returns_ordered_messages_and_empty_messages(monkeypatch):
    client = _client(monkeypatch)

    detail = client.get("/api/admin/cloud-orchestrator/plans/plan_approved/recipients/3").json()
    empty_detail = client.get("/api/admin/cloud-orchestrator/plans/plan_approved/recipients/6").json()
    wrong_plan = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/3")

    assert detail["recipient"]["recipient_id"] == 3
    assert [item["sequence_index"] for item in detail["messages"]] == [1, 2]
    assert detail["messages"][0]["day_offset"] == 0
    assert detail["messages"][0]["send_time"] == "10:00"
    assert detail["messages"][0]["content_text"] == "第一条"
    assert detail["messages"][0]["attachments"] == []
    assert detail["messages"][0]["status"] == "pending"
    assert detail["messages"][1]["attachments"] == [{"msgtype": "file"}]
    assert empty_detail["messages"] == []
    assert wrong_plan.status_code == 404


def test_plan_approve_only_changes_review_state_and_audits(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    first = _approve_plan(client)
    second = _approve_plan(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["plan"]["review_status"] == "approved"
    assert second.json()["plan"]["review_status"] == "approved"
    assert repo.broadcast_jobs == []
    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()["rows"]
    assert [row["approval_status"] for row in recipients] == ["pending", "pending"]
    assert [item["action_type"] for item in repo.audits].count("cloud_plan_approve") == 2


def test_rejected_plan_cannot_be_approved(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_rejected/approve", headers=_token_headers())

    assert response.status_code == 409
    assert "plan is rejected" in response.json()["detail"]


def test_recipient_approve_enqueues_single_idempotent_cloud_plan_job(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    _approve_plan(client)
    first = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())
    second = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "approved"
    assert second.json()["status"] == "already_approved"
    assert len(repo.broadcast_jobs) == 1
    job = repo.broadcast_jobs[0]
    assert job["source_type"] == "cloud_plan"
    assert job["source_table"] == "cloud_broadcast_plan_recipients"
    assert job["source_id"] == "plan_probe:1"
    assert job["target_external_userids"] == ["wm_a"]
    assert job["target_count"] == 1
    assert job["idempotency_key"] == "cloud_plan_recipient:plan_probe:1"
    assert job["content_payload"] == {
        "plan_id": "plan_probe",
        "recipient_id": 1,
        "external_userid": "wm_a",
        "message_mode": "recipient_messages",
    }
    assert first.json()["recipient"]["approval_status"] == "approved"
    assert first.json()["recipient"]["send_status"] == "queued"
    assert [item["action_type"] for item in repo.audits].count("cloud_plan_recipient_approve") == 2


def test_recipient_approve_requires_plan_level_approval(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())

    assert response.status_code == 409
    assert "plan is not approved" in response.json()["detail"]


def test_recipient_approve_does_not_affect_other_recipients(monkeypatch):
    client = _client(monkeypatch)

    _approve_plan(client)
    client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())
    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()["rows"]

    assert recipients[0]["approval_status"] == "approved"
    assert recipients[1]["approval_status"] == "pending"
    assert recipients[1]["send_status"] == "pending"


def test_rejected_or_sent_recipient_cannot_be_approved_again(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    rejected = client.post("/api/admin/cloud-orchestrator/plans/plan_approved/recipients/6/approve", headers=_token_headers())
    sent = client.post("/api/admin/cloud-orchestrator/plans/plan_approved/recipients/4/approve", headers=_token_headers())

    assert rejected.status_code == 409
    assert "recipient is rejected" in rejected.json()["detail"]
    assert sent.status_code == 200
    assert sent.json()["status"] == "already_sent"
    assert repo.broadcast_jobs == []


def test_recipient_reject_only_rejects_current_recipient_and_audits(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    _approve_plan(client)
    response = client.post(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/reject",
        json={"reason": "no send"},
        headers=_token_headers(),
    )
    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()["rows"]

    assert response.status_code == 200
    assert response.json()["recipient"]["approval_status"] == "rejected"
    assert response.json()["recipient"]["send_status"] == "cancelled"
    assert recipients[0]["approval_status"] == "rejected"
    assert recipients[1]["approval_status"] == "pending"
    assert repo.broadcast_jobs == []
    assert repo.audits[-1]["action_type"] == "cloud_plan_recipient_reject"


def test_sent_recipient_cannot_be_rejected(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_approved/recipients/4/reject", headers=_token_headers())

    assert response.status_code == 409
    assert "sent recipient cannot be rejected" in response.json()["detail"]


def test_recipient_approve_idempotency_blocks_duplicate_jobs(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    _approve_plan(client)
    responses = [
        client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers()),
        client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers()),
    ]

    assert [response.status_code for response in responses] == [200, 200]
    assert len(repo.broadcast_jobs) == 1
    assert len({item["idempotency_key"] for item in repo.broadcast_jobs}) == 1


def test_cloud_plan_handler_rejects_legacy_bulk_jobs(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    result = execute_job({"id": 99, "source_type": "cloud_plan", "content_payload": {"plan_id": "plan_probe"}})

    assert result["ok"] is False
    assert "bulk job is disabled" in result["error"]


def test_cloud_plan_handler_routes_recipient_jobs(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs import handlers

    called = {}

    def fake_execute_recipient_messages(*, plan_id, recipient_id, broadcast_job_id=None):
        called.update({"plan_id": plan_id, "recipient_id": recipient_id, "broadcast_job_id": broadcast_job_id})
        return {"ok": True, "sent_count": 1, "failed_count": 0}

    monkeypatch.setattr(
        "wecom_ability_service.domains.cloud_orchestrator.broadcast_planner.execute_recipient_messages",
        fake_execute_recipient_messages,
    )

    result = handlers.execute_job(
        {
            "id": 99,
            "source_type": "cloud_plan",
            "content_payload": {"plan_id": "plan_probe", "recipient_id": 1},
        }
    )

    assert result == {"ok": True, "sent_count": 1, "failed_count": 0}
    assert called == {"plan_id": "plan_probe", "recipient_id": 1, "broadcast_job_id": 99}


def test_worker_marks_single_recipient_job_sent_or_failed(monkeypatch):
    monkeypatch.syspath_prepend("scripts")

    from scripts.run_broadcast_queue_worker import _process_one_job

    sent_calls = []
    failed_calls = []

    monkeypatch.setattr(
        "wecom_ability_service.domains.broadcast_jobs.handlers.execute_job",
        lambda job: {"ok": True, "sent_count": 1, "failed_count": 0, "outbound_task_id": 88},
    )
    monkeypatch.setattr("wecom_ability_service.domains.broadcast_jobs.service.record_job_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "wecom_ability_service.domains.broadcast_jobs.service.mark_sent",
        lambda job_id, **kwargs: sent_calls.append({"job_id": job_id, **kwargs}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.broadcast_jobs.service.mark_failed",
        lambda job_id, **kwargs: failed_calls.append({"job_id": job_id, **kwargs}),
    )

    sent = _process_one_job({"id": 42, "source_type": "cloud_plan", "content_payload": {"plan_id": "plan_probe", "recipient_id": 1}})

    assert sent == {"id": 42, "status": "sent", "outbound_task_id": 88, "sent_count": 1}
    assert sent_calls == [{"job_id": 42, "outbound_task_id": 88, "sent_count": 1, "failed_count": 0}]
    assert failed_calls == []

    monkeypatch.setattr(
        "wecom_ability_service.domains.broadcast_jobs.handlers.execute_job",
        lambda job: {"ok": False, "error": "safe failure"},
    )
    failed = _process_one_job({"id": 43, "source_type": "cloud_plan", "content_payload": {"plan_id": "plan_probe", "recipient_id": 1}})

    assert failed == {"id": 43, "status": "failed", "reason": "safe failure"}
    assert failed_calls == [{"job_id": 43, "error": "safe failure", "failure_type": "handler_error"}]
