from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aicrm_next.automation_engine.programs import (
    create_automation_program_operation_task,
    preview_automation_program_operation_task_audience,
)
from aicrm_next.main import create_app
from automation_channel_admission_helpers import (
    create_channel,
    create_program,
    disabled_entry_rule,
    save_audience_entry_rule,
)
from wecom_ability_service.domains.automation_conversion.admission_service import admit_channel_contact_to_program
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program
from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job


ROOT = Path(__file__).resolve().parents[1]


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def _load_due_script():
    path = ROOT / "scripts" / "run_automation_conversion_due_jobs.py"
    spec = importlib.util.spec_from_file_location("run_automation_conversion_due_jobs_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _bind(program_id: int, channel_id: int) -> int:
    return int(bind_channels_to_program(program_id, [channel_id], {}, "pytest")["bindings"][0]["id"])


def test_operation_runtime_contract_rejects_unpublishable_active_content(app):
    with app.app_context():
        program_id = create_program("runtime_contract_validation")

        with pytest.raises(ValueError, match="统一内容"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "empty unified",
                    "status": "active",
                    "trigger_type": "audience_entered",
                    "target_stage_code": "operating",
                    "content_mode": "unified",
                    "unified_content_json": {},
                },
                operator_id="pytest",
            )

        with pytest.raises(ValueError, match="触发方式"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "bad trigger",
                    "status": "active",
                    "trigger_type": "unknown",
                    "content_mode": "unified",
                    "unified_content_json": {"content_text": "ok"},
                },
                operator_id="pytest",
            )

        with pytest.raises(ValueError, match="fallback"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "agent without runtime body",
                    "status": "active",
                    "trigger_type": "audience_entered",
                    "target_stage_code": "operating",
                    "content_mode": "agent",
                    "agent_config_json": {"agent_code": "welcome_agent"},
                },
                operator_id="pytest",
            )


def test_operation_runtime_contract_preview_is_read_only_and_reports_reasons(app):
    with app.app_context():
        program_id = create_program("runtime_contract_preview")
        channel = create_channel("runtime_contract_preview_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())

        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_contract_preview",
            trigger_time="2026-06-05 10:00:00",
        )
        assert admitted["audience_code"] == "operating"

        payload = {
            "task_name": "preview task",
            "status": "draft",
            "trigger_type": "scheduled_daily",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": "hello"},
        }
        result = preview_automation_program_operation_task_audience(program_id, payload)

        preview = result["preview"]
        assert preview["target_count"] == 1
        assert preview["segment_counts"]["unified"] == 1
        assert preview["filtered_out_counts"] == {}
        assert preview["reasons"] == []

        missing_content = preview_automation_program_operation_task_audience(
            program_id,
            {**payload, "unified_content_json": {}},
        )["preview"]
        assert missing_content["target_count"] == 0
        assert missing_content["filtered_out_counts"]["content_missing"] == 1
        assert "content_missing" in missing_content["reasons"]


def test_operation_runtime_contract_preview_uses_program_channel_binding(app):
    with app.app_context():
        old_program_id = create_program("runtime_contract_preview_old_channel_program")
        new_program_id = create_program("runtime_contract_preview_bound_program")
        channel = create_channel("runtime_contract_preview_bound_channel", program_id=old_program_id)
        binding_id = _bind(new_program_id, int(channel["id"]))
        save_audience_entry_rule(new_program_id, disabled_entry_rule())

        admitted = admit_channel_contact_to_program(
            new_program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_contract_preview_binding",
            trigger_time="2026-06-05 10:00:00",
        )
        assert admitted["audience_code"] == "operating"

        result = preview_automation_program_operation_task_audience(
            new_program_id,
            {
                "task_name": "preview bound channel task",
                "status": "draft",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "none",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "hello"},
            },
        )

        preview = result["preview"]
        assert preview["target_count"] == 1
        assert preview["segment_counts"]["unified"] == 1
        assert "program_channel_not_matched" not in preview["reasons"]


def test_operation_runtime_contract_due_script_supports_operation_task_without_defaulting_it(monkeypatch):
    module = _load_due_script()
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "body": json.loads(request.data.decode("utf-8")),
            }
        )
        return _FakeResponse(b'{"ok": true, "enqueued_count": 2}')

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert "operation_task" in module.JOB_DEFINITIONS
    assert module.DEFAULT_JOB_CODES == ["sop", "conversion_workflow"]
    body = json.loads(module.run(jobs=["operation_task"]))

    assert captured[0]["body"] == {"operator": "automation_conversion_due_runner", "jobs": ["operation_task"]}
    assert body["requested_job_codes"] == ["operation_task"]
    assert body["jobs"][0]["job_code"] == "operation_task"


def test_operation_runtime_contract_next_jobs_route_is_plan_only_for_operation_task(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"jobs": ["operation_task"], "dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jobs_run_due_executed"] is False
    assert body["operation_tasks_executed"] == 0
    assert body["planned_count"] >= 0
    assert body["actual_enqueued_count"] == 0
    assert body["blocked_reason"] == "next_plan_only_route"


def test_operation_runtime_contract_worker_routes_operation_task_handler(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_operation_task_broadcast_job(job):
        captured["job"] = dict(job)
        return {"ok": True, "sent_count": 1, "failed_count": 0, "outbound_task_id": 321}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.operation_task_service.run_operation_task_broadcast_job",
        fake_run_operation_task_broadcast_job,
    )

    result = execute_job({"id": 99, "source_type": "operation_task", "content_payload": {"task_id": 1}})

    assert result["ok"] is True
    assert result["sent_count"] == 1
    assert captured["job"]["source_type"] == "operation_task"
