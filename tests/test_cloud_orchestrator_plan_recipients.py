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


def test_cloud_plan_list_does_not_embed_recipients_or_messages(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/admin/cloud-orchestrator/plans?limit=20&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["plans"][0]["plan_id"] == "plan_probe"
    assert payload["plans"][0]["target_count"] == 2
    assert "recipients" not in payload["plans"][0]
    assert "messages" not in payload["plans"][0]


def test_plan_approve_only_changes_plan_review_state(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/approve", headers=_token_headers())

    assert response.status_code == 200
    assert response.json()["plan"]["review_status"] == "approved"
    assert repo.broadcast_jobs == []
    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()["rows"]
    assert [row["approval_status"] for row in recipients] == ["pending", "pending"]


def test_recipient_approve_enqueues_single_idempotent_cloud_plan_job(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    client.post("/api/admin/cloud-orchestrator/plans/plan_probe/approve", headers=_token_headers())
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
    assert job["content_payload"] == {
        "plan_id": "plan_probe",
        "recipient_id": 1,
        "external_userid": "wm_a",
        "message_mode": "recipient_messages",
    }


def test_recipient_approve_requires_plan_level_approval(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())

    assert response.status_code == 409
    assert "plan is not approved" in response.json()["detail"]


def test_recipient_detail_is_the_only_endpoint_returning_messages(monkeypatch):
    client = _client(monkeypatch)

    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()
    detail = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1").json()

    assert "messages" not in recipients["rows"][0]
    assert detail["messages"][0]["content_text"] == "你好"


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
