from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from aicrm_next.platform_foundation.legacy_cleanup.repo import build_legacy_cleanup_repository, reset_legacy_cleanup_fixture_state
from aicrm_next.platform_foundation.legacy_cleanup.service import DEFAULT_LEGACY_DEPRECATIONS, LegacyWebhookCleanupService


def _fixed_now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def test_legacy_deprecation_registry_bootstrap_is_idempotent_and_schedules_seven_days() -> None:
    reset_legacy_cleanup_fixture_state()
    now = _fixed_now()
    service = LegacyWebhookCleanupService()

    first = service.ensure_default_deprecations(now=now)
    second = service.ensure_default_deprecations(now=now + timedelta(hours=1))

    assert len(first) == len(DEFAULT_LEGACY_DEPRECATIONS)
    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].delete_scheduled_at == "2026-06-21T12:00:00Z"
    assert first[0].replacement_route == "/admin/push-center"
    assert first[0].notes_json["real_external_call_executed"] is False


def test_cleanup_preview_and_not_due_run_do_not_delete() -> None:
    reset_legacy_cleanup_fixture_state()
    now = _fixed_now()
    service = LegacyWebhookCleanupService()
    service.ensure_default_deprecations(now=now)

    preview = service.preview_due(now=now, limit=20)
    run = service.run_due(dry_run=False, now=now, limit=20, operator="pytest")
    status = service.status()

    assert preview["counts"]["candidate_count"] == 0
    assert run["counts"]["deleted"] == 0
    assert status["counts"]["scheduled"] == len(DEFAULT_LEGACY_DEPRECATIONS)


def test_status_preview_and_run_due_are_read_only_before_marking() -> None:
    reset_legacy_cleanup_fixture_state()
    service = LegacyWebhookCleanupService()

    status = service.status()
    preview = service.preview_due(now=_fixed_now(), limit=20)
    run = service.run_due(dry_run=True, now=_fixed_now(), limit=20, operator="pytest")
    after = service.status()

    assert status["total"] == 0
    assert preview["counts"]["candidate_count"] == 0
    assert run["counts"]["candidate_count"] == 0
    assert after["total"] == 0


def test_cleanup_run_due_deletes_due_entries_without_history_data_deletion() -> None:
    reset_legacy_cleanup_fixture_state()
    now = _fixed_now()
    service = LegacyWebhookCleanupService()
    service.ensure_default_deprecations(now=now - timedelta(days=8))

    preview = service.preview_due(now=now, limit=20)
    result = service.run_due(dry_run=False, now=now, limit=20, operator="pytest-cleanup")
    repo = build_legacy_cleanup_repository()
    audits = repo.list_audits(limit=20)

    assert preview["counts"]["candidate_count"] == len(DEFAULT_LEGACY_DEPRECATIONS)
    assert result["counts"]["deleted"] == len(DEFAULT_LEGACY_DEPRECATIONS)
    assert result["counts"]["failed"] == 0
    assert all(item["item"]["delete_status"] == "deleted" for item in result["items"])
    assert all(item["item"]["notes_json"]["history_data_deleted"] is False for item in result["items"])
    assert len([audit for audit in audits if audit.action == "delete_legacy_entry"]) == len(DEFAULT_LEGACY_DEPRECATIONS)


def test_cleanup_run_due_blocks_when_recent_legacy_execution_exists() -> None:
    reset_legacy_cleanup_fixture_state()
    now = _fixed_now()
    service = LegacyWebhookCleanupService()
    service.ensure_default_deprecations(now=now - timedelta(days=8))
    repo = build_legacy_cleanup_repository()
    repo.record_audit(
        legacy_key="old_ai_assist_direct_send",
        action="legacy_real_execution",
        operator="pytest",
        before={},
        after={"real_external_call_executed": True},
    )

    result = service.run_due(dry_run=False, now=now, limit=1, operator="pytest-cleanup")
    failed = repo.get_deprecation("old_ai_assist_direct_send")

    assert result["counts"]["failed"] == 1
    assert failed is not None
    assert failed.delete_status == "failed"
    assert failed.notes_json["error"] == "recent_legacy_execution_detected"
    assert repo.list_audits(legacy_key="old_ai_assist_direct_send", limit=10)[0].action == "delete_legacy_entry_failed"


def test_legacy_cleanup_api_requires_token_for_run_due(next_client: TestClient, monkeypatch) -> None:
    reset_legacy_cleanup_fixture_state()
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "pytest-internal")

    status = next_client.get("/api/admin/legacy-webhook-cleanup/status")
    rejected_mark = next_client.post("/api/admin/legacy-webhook-cleanup/deprecations/mark", json={"operator": "pytest"})
    marked = next_client.post(
        "/api/admin/legacy-webhook-cleanup/deprecations/mark",
        headers={"Authorization": "Bearer pytest-internal"},
        json={"operator": "pytest"},
    )
    rejected = next_client.post("/api/admin/legacy-webhook-cleanup/run-due/preview", json={"dry_run": True})
    accepted = next_client.post(
        "/api/admin/legacy-webhook-cleanup/run-due/preview",
        headers={"Authorization": "Bearer pytest-internal"},
        json={"dry_run": True},
    )

    assert status.status_code == 200
    assert status.json()["total"] == 0
    assert rejected_mark.status_code == 401
    assert marked.status_code == 200
    assert marked.json()["total"] == len(DEFAULT_LEGACY_DEPRECATIONS)
    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["dry_run"] is True
    assert accepted.json()["real_external_call_executed"] is False


def test_legacy_cleanup_cli_preview_is_json(monkeypatch, capsys) -> None:
    reset_legacy_cleanup_fixture_state()
    from aicrm_next.platform_foundation.legacy_cleanup.jobs import print_mark_deprecated_result, print_run_due_result

    print_run_due_result(dry_run=True, limit=3, operator="pytest-cli")
    preview_output = capsys.readouterr().out
    print_mark_deprecated_result(operator="pytest-cli")
    mark_output = capsys.readouterr().out

    assert '"ok": true' in preview_output
    assert '"dry_run": true' in preview_output
    assert '"candidate_count": 0' in preview_output
    assert "real_external_call_executed" in preview_output
    assert '"ok": true' in mark_output
    assert f'"total": {len(DEFAULT_LEGACY_DEPRECATIONS)}' in mark_output
