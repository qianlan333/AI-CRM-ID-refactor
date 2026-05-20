from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_1_media_production_signoff_readiness as checker

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_doc(name: str) -> str:
    return (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_args(
    tmp_path: Path,
    *,
    write_included: bool = False,
    cloud_upload: bool = False,
    pre_approved: bool = False,
    missing_rollback_owner: bool = False,
    missing_stop_conditions: bool = False,
) -> Namespace:
    signoff_packet = tmp_path / "signoff.md"
    approval_package = tmp_path / "approval.md"
    readiness = tmp_path / "readiness.json"
    smoke = tmp_path / "smoke.json"
    parity = tmp_path / "parity.json"

    included = "\n".join(f"- `{route}`" for route in sorted(checker.REQUIRED_INCLUDED_ROUTES))
    if write_included:
        included += "\n- `POST /api/admin/image-library`"
    excluded = "\n".join(f"- {route}" for route in sorted(checker.REQUIRED_EXCLUDED_MARKERS))
    rollback_owner = "" if missing_rollback_owner else "| Rollback owner | pending |"
    stop_conditions = "" if missing_stop_conditions else "## G. Stop Conditions\n\n- any 5xx increase\n- route smoke fails\n"
    approval_value = "yes" if pre_approved else "pending_human_signoff"
    signoff_packet.write_text(
        f"""# Batch 1 Media Readonly Production Canary Human Signoff Packet

| field | value |
| --- | --- |
| target batch | Batch 1 Media readonly |
| target status | `pending_human_signoff` |
| production execution | not executed |
| canary type | readonly route-level canary |
| external adapters | cloud storage disabled; WeCom media disabled |
| write routes | excluded |

Included readonly routes:

{included}

Excluded routes and operations:

{excluded}

## C. Required Evidence

## E. Human Signoff Roles

{rollback_owner}

## F. Proposed Production Route Flags

Proposed only. Do not apply without human approval. No secrets or production hosts are recorded here.

```bash
AICRM_NEXT_ROUTE_MEDIA_READONLY=true
AICRM_NEXT_ROUTE_MEDIA_WRITES=false
AICRM_NEXT_EXTERNAL_CLOUD_STORAGE=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

{stop_conditions}

## H. Rollback Summary

`AICRM_NEXT_ROUTE_MEDIA_READONLY=false`

## I. Final Decision Block

| field | value |
| --- | --- |
| approve production canary | {approval_value} |
| rollback owner |  |
""",
        encoding="utf-8",
    )
    approval_package.write_text(
        "not a production cutover\npending_human_signoff\nBatch 1 Media readonly\n",
        encoding="utf-8",
    )
    safety = {
        "production_config_modified": False,
        "old_write_endpoints_executed": False,
        "cloud_storage_upload_executed": cloud_upload,
        "external_upload_executed": False,
        "wecom_media_upload_executed": False,
        "real_traffic_cutover_executed": False,
        "default_endpoints_get_only": True,
    }
    _write_json(
        readiness,
        {
            "ok": True,
            "approval_status": "pending_human_signoff",
            "recommended_next_action": "REQUEST_HUMAN_SIGNOFF_FOR_BATCH_1_MEDIA_READONLY",
            "blockers": [],
            "side_effect_safety": safety,
        },
    )
    _write_json(smoke, {"ok": True, "blockers": [], "side_effect_safety": safety})
    _write_json(parity, {"ok": True, "overall": "PASS", "blockers": []})
    return Namespace(
        signoff_packet=str(signoff_packet),
        approval_package=str(approval_package),
        readiness_json=str(readiness),
        media_smoke_json=str(smoke),
        media_parity_json=str(parity),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_signoff_packet_exists() -> None:
    assert (PROJECT_ROOT / "docs" / "batch_1_media_readonly_production_canary_signoff_packet.md").exists()


def test_signoff_packet_includes_target_routes() -> None:
    text = _read_doc("batch_1_media_readonly_production_canary_signoff_packet.md")
    for route in checker.REQUIRED_INCLUDED_ROUTES:
        assert route in text


def test_signoff_packet_excludes_write_routes() -> None:
    text = _read_doc("batch_1_media_readonly_production_canary_signoff_packet.md")
    excluded = text[text.index("Excluded routes and operations:") : text.index("## C. Required Evidence")]
    assert "POST /api/admin/image-library" in excluded
    assert "PUT /api/admin/image-library/{image_id}" in excluded
    assert "DELETE /api/admin/image-library/{image_id}" in excluded
    assert "cloud storage upload" in excluded
    assert "WeCom media upload" in excluded


def test_signoff_packet_has_pending_human_signoff() -> None:
    text = _read_doc("batch_1_media_readonly_production_canary_signoff_packet.md")
    assert "pending_human_signoff" in text
    assert "This packet does not mark the production canary as approved." in text


def test_execution_checklist_says_it_is_not_an_automation_script() -> None:
    text = _read_doc("batch_1_media_readonly_production_execution_checklist.md")
    assert "not an automation script" in text
    assert "does not execute route changes" in text


def test_checker_passes_with_good_fixture_evidence(tmp_path: Path) -> None:
    report = checker.build_report(_fixture_args(tmp_path))
    assert report["ok"] is True
    assert report["signoff_status"] == "pending_human_signoff"
    assert report["recommended_next_action"] == "REQUEST_HUMAN_SIGNOFF"


def test_checker_fails_when_write_route_is_included(tmp_path: Path) -> None:
    report = checker.build_report(_fixture_args(tmp_path, write_included=True))
    assert report["ok"] is False
    assert any(item["reason"] == "write_route_included_in_readonly_section" for item in report["blockers"])


def test_checker_fails_when_cloud_upload_safety_flag_true(tmp_path: Path) -> None:
    report = checker.build_report(_fixture_args(tmp_path, cloud_upload=True))
    assert report["ok"] is False
    assert any(item.get("field") == "cloud_storage_upload_executed" for item in report["blockers"])


def test_checker_fails_when_final_decision_is_pre_approved(tmp_path: Path) -> None:
    report = checker.build_report(_fixture_args(tmp_path, pre_approved=True))
    assert report["ok"] is False
    assert any(item["reason"] == "final_decision_pre_approved" for item in report["blockers"])


def test_checker_requires_rollback_owner_field(tmp_path: Path) -> None:
    report = checker.build_report(_fixture_args(tmp_path, missing_rollback_owner=True))
    assert report["ok"] is False
    assert any(item.get("marker") == "Rollback owner" for item in report["blockers"])


def test_checker_requires_stop_conditions(tmp_path: Path) -> None:
    report = checker.build_report(_fixture_args(tmp_path, missing_stop_conditions=True))
    assert report["ok"] is False
    assert any(item.get("marker") == "## G. Stop Conditions" for item in report["blockers"])


def test_no_production_host_or_secret_in_docs() -> None:
    docs = [
        "batch_1_media_readonly_production_canary_signoff_packet.md",
        "batch_1_media_readonly_production_execution_checklist.md",
    ]
    for name in docs:
        lowered = _read_doc(name).lower()
        for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
            assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_1_media_production_signoff_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
