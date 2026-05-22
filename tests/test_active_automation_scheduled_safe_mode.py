from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.integration_gateway import legacy_flask_facade
from aicrm_next.main import create_app
from tools import check_active_automation_scheduled_safe_mode as checker


def _production_client(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    monkeypatch.setenv("SECRET_KEY", "active-automation-scheduled-safe-mode")
    return TestClient(create_app())


def _auth_headers():
    return {"Authorization": "Bearer probe-token"}


def _raise_if_legacy_forwarded():
    raise AssertionError("scheduled safe mode must not forward to legacy")


def test_jobs_scheduled_safe_mode_no_due_returns_idle_200(monkeypatch):
    client = _production_client(monkeypatch)
    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", _raise_if_legacy_forwarded)

    response = client.post(
        checker.ACTIVE_JOBS_ROUTE,
        json={"operator": "aicrm-automation-jobs-run-due", "jobs": ["sop", "conversion_workflow"], "scheduled_safe_mode": True},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "idle"
    assert payload["scheduled_safe_mode"] is True
    assert payload["side_effect_executed"] is False
    assert payload["legacy_forwarded"] is False
    assert payload["preview"]["estimated_send_count"] == 0


def test_campaign_scheduled_safe_mode_no_due_returns_idle_200(monkeypatch):
    client = _production_client(monkeypatch)
    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", _raise_if_legacy_forwarded)

    response = client.post(
        checker.CAMPAIGN_ROUTE,
        json={"operator": "aicrm-campaign-run-due", "batch_size": 200, "scheduled_safe_mode": True},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "idle"
    assert payload["side_effect_executed"] is False
    assert payload["legacy_forwarded"] is False
    assert payload["preview"]["estimated_dispatch_count"] == 0


def test_jobs_scheduled_safe_mode_due_without_allowlist_returns_blocked_200(monkeypatch):
    client = _production_client(monkeypatch)
    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", _raise_if_legacy_forwarded)
    monkeypatch.setattr(legacy_flask_facade, "_active_automation_preview_payload", _synthetic_due_preview)

    response = client.post(
        checker.ACTIVE_JOBS_ROUTE,
        json={"operator": "aicrm-automation-jobs-run-due", "jobs": ["sop", "conversion_workflow"], "scheduled_safe_mode": True},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "blocked_not_executed"
    assert payload["manual_action_required"] is True
    assert payload["error_code"] == "active_automation_due_candidates_require_allowlist"
    assert payload["side_effect_executed"] is False
    assert payload["legacy_forwarded"] is False
    assert payload["preview"]["estimated_send_count"] == 1


def test_campaign_scheduled_safe_mode_due_without_allowlist_returns_blocked_200(monkeypatch):
    client = _production_client(monkeypatch)
    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", _raise_if_legacy_forwarded)
    monkeypatch.setattr(legacy_flask_facade, "_active_automation_preview_payload", _synthetic_due_preview)

    response = client.post(
        checker.CAMPAIGN_ROUTE,
        json={"operator": "aicrm-campaign-run-due", "batch_size": 200, "scheduled_safe_mode": True},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked_not_executed"
    assert payload["error_code"] == "active_automation_due_candidates_require_allowlist"
    assert payload["side_effect_executed"] is False
    assert payload["legacy_forwarded"] is False
    assert payload["preview"]["estimated_dispatch_count"] == 1


def test_raw_true_execution_without_allowlist_still_returns_409(monkeypatch):
    client = _production_client(monkeypatch)
    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", _raise_if_legacy_forwarded)

    jobs = client.post(checker.ACTIVE_JOBS_ROUTE, json={"operator": "manual", "jobs": ["sop"]}, headers=_auth_headers())
    campaign = client.post(checker.CAMPAIGN_ROUTE, json={"operator": "manual", "batch_size": 1}, headers=_auth_headers())

    assert jobs.status_code == 409
    assert jobs.json()["error_code"] == "automation_run_due_allowlist_required"
    assert campaign.status_code == 409
    assert campaign.json()["error_code"] == "campaign_run_due_allowlist_required"


def test_checker_returns_ok_and_keeps_local_sentinel_stable():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["scheduled_safe_mode_idle_ok"] is True
    assert result["scheduled_safe_mode_blocked_ok"] is True
    assert result["raw_true_execution_without_allowlist_still_409"] is True
    assert result["db_sentinel"]["ok"] is True
    assert result["timers_not_enabled"] is True


def test_checker_detects_sentinel_change(monkeypatch):
    monkeypatch.setattr(checker, "scheduled_safe_mode_probe_env", lambda: _NoopContext())

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return dict(self._payload)

    class FakeClient:
        def post(self, route, json=None, headers=None, follow_redirects=False):
            if (json or {}).get("scheduled_safe_mode"):
                return FakeResponse(
                    200,
                    {
                        "ok": True,
                        "status": "idle",
                        "scheduled_safe_mode": True,
                        "side_effect_executed": False,
                        "legacy_forwarded": False,
                        "preview": {"estimated_send_count": 0, "estimated_dispatch_count": 0},
                    },
                )
            return FakeResponse(409, {"error_code": "automation_run_due_allowlist_required"})

    sentinels = iter(
        [
            {"available": True, "reason": "", "values": {key: "before" for key in checker.DB_SENTINEL_QUERIES}},
            {"available": True, "reason": "", "values": {key: "after" for key in checker.DB_SENTINEL_QUERIES}},
        ]
    )
    monkeypatch.setattr(checker, "_client", lambda: FakeClient())
    monkeypatch.setattr(checker, "_read_db_sentinel", lambda: next(sentinels))
    monkeypatch.setattr(checker, "_timer_enablement_status", lambda: {"timers_not_enabled": True, "units": {}})
    monkeypatch.setattr(checker, "_docs_payloads_ready", lambda: (True, []))

    result = checker.run_check()

    assert result["ok"] is False
    assert "db_sentinel_changed_or_unavailable" in result["blockers"]


def test_runbook_mentions_exact_systemd_payloads():
    content = open("docs/active_automation_reenable_runbook.md", encoding="utf-8").read()

    assert checker.SYSTEMD_JOBS_PAYLOAD in content
    assert checker.SYSTEMD_CAMPAIGN_PAYLOAD in content
    assert "scheduled_safe_mode" in content


def test_docs_do_not_use_forbidden_status_markers():
    content = "\n".join(
        open(path, encoding="utf-8").read()
        for path in [
            "docs/reply_system_reenable_runbook.md",
            "docs/active_automation_reenable_runbook.md",
        ]
    )
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


def _synthetic_due_preview(path: str, payload: dict):
    if path == checker.ACTIVE_JOBS_ROUTE:
        return {
            "ok": True,
            "preview": True,
            "side_effect_executed": False,
            "legacy_forwarded": False,
            "route_owner": "ai_crm_next",
            "compatibility_facade": "legacy_flask_facade",
            "path": path,
            "jobs": [
                {
                    "job_code": "sop",
                    "due_count": 1,
                    "candidate_task_ids": [101],
                    "candidate_workflow_ids": [],
                    "candidate_node_ids": [],
                    "estimated_audience_count": 1,
                    "estimated_send_count": 1,
                    "sample_targets": [{"id": "sample"}],
                    "content_preview": ["sample"],
                    "risk_flags": ["synthetic_due_candidate"],
                }
            ],
            "total_due_count": 1,
            "estimated_send_count": 1,
        }
    return {
        "ok": True,
        "preview": True,
        "side_effect_executed": False,
        "legacy_forwarded": False,
        "route_owner": "ai_crm_next",
        "compatibility_facade": "legacy_flask_facade",
        "path": path,
        "batch_size": 1,
        "campaigns": [{"campaign_id": 201}],
        "due_count": 1,
        "estimated_dispatch_count": 1,
        "sample_targets": [{"id": "sample"}],
        "content_preview": ["sample"],
        "risk_flags": ["synthetic_due_candidate"],
    }
