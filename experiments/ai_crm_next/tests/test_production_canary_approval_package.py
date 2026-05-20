from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_production_canary_approval_package as approval

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_doc(name: str) -> str:
    return (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_args(
    tmp_path: Path,
    *,
    batch: str = "media_readonly",
    readiness_blocker: bool = False,
    external_call: bool = False,
) -> Namespace:
    approval_package = tmp_path / "production_canary_approval_package.md"
    readiness = tmp_path / "readiness.json"
    smoke = tmp_path / "smoke.json"
    parity = tmp_path / "parity.json"
    approval_package.write_text(
        "\n".join(
            [
                "not a production cutover",
                "pending_human_signoff",
                "Batch 1",
                "Batch 2",
                "Batch 3",
                "Batch 4",
                "Batch 5",
                "Batch 6",
                "Batch 1 Media readonly",
                batch,
            ]
        ),
        encoding="utf-8",
    )
    safety = {
        "old_write_endpoints_executed": False,
        "cloud_storage_upload_executed": external_call,
        "real_traffic_cutover_executed": False,
        "production_config_modified": False,
        "default_endpoints_get_only": True,
        "fake_writes_next_testclient_only": True,
    }
    _write_json(
        readiness,
        {
            "ok": not readiness_blocker,
            "readiness_status": "canary_plan_ready" if not readiness_blocker else "blocked",
            "blockers": [{"reason": "fixture_blocker"}] if readiness_blocker else [],
            "side_effect_safety": safety,
            "rollback_dry_run": {
                "route_flag_rollback_instruction": "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
                "expected_owner_after_rollback": "old Flask",
            },
        },
    )
    _write_json(smoke, {"ok": True, "blockers": [], "warnings": [], "skipped": [], "side_effect_safety": safety})
    _write_json(parity, {"ok": True, "overall": "PASS", "blockers": [], "warnings": [], "skipped": []})
    return Namespace(
        approval_package=str(approval_package),
        batch=batch,
        batch_readiness_json=str(readiness),
        smoke_json=str(smoke),
        parity_json=str(parity),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_approval_package_exists_and_mentions_no_production_cutover() -> None:
    text = _read_doc("production_canary_approval_package.md")
    assert "not a production cutover" in text
    assert "pending_human_signoff" in text
    assert "No production route has been enabled" in text


def test_approval_package_lists_batch_1_to_6() -> None:
    text = _read_doc("production_canary_approval_package.md")
    for batch in range(1, 7):
        assert f"Batch {batch}" in text


def test_recommended_first_production_canary_is_media_readonly() -> None:
    text = _read_doc("production_canary_approval_package.md")
    assert "Recommended first candidate: Batch 1 Media readonly." in text


def test_change_request_template_includes_rollback_owner() -> None:
    text = _read_doc("production_canary_change_request_template.md")
    assert "rollback owner" in text
    assert "latest smoke" in text
    assert "human" in text.lower()


def test_observability_plan_includes_core_signals() -> None:
    text = _read_doc("production_canary_observability_plan.md")
    for expected in ("status code", "latency", "4xx / 5xx", "error logs", "access logs"):
        assert expected in text


def test_rollback_runbook_includes_route_flags_for_all_six_batches() -> None:
    text = _read_doc("production_canary_rollback_runbook.md")
    for flag in (
        "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
        "AICRM_NEXT_ROUTE_PRODUCT_READONLY=false",
        "AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false",
        "AICRM_NEXT_ROUTE_USER_OPS_READONLY=false",
        "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false",
        "AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false",
    ):
        assert flag in text


def test_readiness_checker_passes_with_good_media_readonly_fixture_evidence(tmp_path: Path) -> None:
    report = approval.build_report(_fixture_args(tmp_path))
    assert report["ok"] is True
    assert report["approval_status"] == "pending_human_signoff"
    assert report["recommended_next_action"] == "REQUEST_HUMAN_SIGNOFF_FOR_BATCH_1_MEDIA_READONLY"


def test_readiness_checker_fails_if_batch_unknown(tmp_path: Path) -> None:
    report = approval.build_report(_fixture_args(tmp_path, batch="unknown_batch"))
    assert report["ok"] is False
    assert any(item["reason"] == "unknown_batch" for item in report["blockers"])


def test_readiness_checker_fails_if_side_effect_safety_has_external_call_true(tmp_path: Path) -> None:
    report = approval.build_report(_fixture_args(tmp_path, external_call=True))
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "cloud_storage_upload_executed"} in report["blockers"]


def test_readiness_checker_status_remains_pending_human_signoff(tmp_path: Path) -> None:
    report = approval.build_report(_fixture_args(tmp_path))
    assert report["approval_status"] == "pending_human_signoff"
    assert "approved" not in report["approval_status"]


def test_new_documents_do_not_mark_production_ready_or_approved() -> None:
    docs = [
        "production_canary_approval_package.md",
        "production_canary_change_request_template.md",
        "production_canary_observability_plan.md",
        "production_canary_rollback_runbook.md",
    ]
    for name in docs:
        text = _read_doc(name)
        assert "production_ready" not in text
        assert "production_approved" not in text


def test_approval_docs_have_no_production_host_or_secrets() -> None:
    docs = [
        "production_canary_approval_package.md",
        "production_canary_change_request_template.md",
        "production_canary_observability_plan.md",
        "production_canary_rollback_runbook.md",
    ]
    for name in docs:
        lowered = _read_doc(name).lower()
        for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
            assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_production_canary_approval_package.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
