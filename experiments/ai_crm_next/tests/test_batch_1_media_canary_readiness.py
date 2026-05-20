from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_1_media_canary_readiness as readiness

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_doc(name: str) -> str:
    return (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_reports(tmp_path: Path, *, smoke_blocker: bool = False, external_upload: bool = False, rollback: bool = True) -> Namespace:
    smoke = tmp_path / "media_smoke.json"
    parity = tmp_path / "media_parity.json"
    rehearsal = tmp_path / "batch_rehearsal.json"
    route_status = tmp_path / "route_status.json"

    _write_json(
        smoke,
        {
            "ok": not smoke_blocker,
            "blockers": [{"reason": "route_returned_5xx"}] if smoke_blocker else [],
            "warnings": [],
            "skipped": [],
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "external_upload_executed": external_upload,
                "wecom_media_upload_executed": False,
                "default_endpoints_get_only": True,
            },
        },
    )
    _write_json(parity, {"ok": True, "overall": "PASS", "blockers": [], "warnings": [], "skipped": []})
    rehearsal_payload = {
        "ok": True,
        "recommendation": "GO",
        "included_routes": sorted(readiness.REQUIRED_INCLUDED_ROUTES),
        "excluded_routes": sorted(readiness.REQUIRED_WRITE_EXCLUSIONS),
        "route_flags": {
            "AICRM_NEXT_ROUTE_MEDIA_READONLY": True,
            "AICRM_NEXT_ROUTE_MEDIA_WRITES": False,
            "AICRM_NEXT_EXTERNAL_CLOUD_STORAGE": False,
            "AICRM_NEXT_EXTERNAL_WECOM_MEDIA": False,
        },
        "side_effect_safety": {
            "production_config_modified": False,
            "old_write_endpoints_executed": False,
            "cloud_storage_upload_executed": False,
            "wecom_media_upload_executed": False,
            "real_traffic_cutover_executed": False,
            "default_endpoints_get_only": True,
        },
    }
    if rollback:
        rehearsal_payload["rollback_dry_run"] = {
            "route_flag_rollback_instruction": "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
            "expected_owner_after_rollback": "old Flask",
        }
    _write_json(rehearsal, rehearsal_payload)
    _write_json(
        route_status,
        {
            "ok": True,
            "summary": {"routes": 14, "passed": 14, "screenshots_generated": 14},
            "route_results": [{"route": route, "ok": True} for route in sorted(readiness.REQUIRED_SCREENSHOT_ROUTES)],
        },
    )
    return Namespace(
        media_smoke_json=str(smoke),
        media_parity_json=str(parity),
        batch_rehearsal_json=str(rehearsal),
        route_status_json=str(route_status),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_canary_plan_includes_only_readonly_routes() -> None:
    text = _read_doc("batch_1_media_readonly_canary_plan.md")
    included = text[text.index("Included readonly routes:") : text.index("Excluded routes:")]
    assert "GET /admin/image-library" in included
    assert "GET /api/admin/miniprogram-library" in included
    assert "POST " not in included
    assert "PUT " not in included
    assert "DELETE " not in included


def test_canary_plan_excludes_write_routes() -> None:
    text = _read_doc("batch_1_media_readonly_canary_plan.md")
    excluded = text[text.index("Excluded routes:") : text.index("## Canary Mode Options")]
    assert "POST /api/admin/image-library" in excluded
    assert "PUT /api/admin/image-library/{image_id}" in excluded
    assert "DELETE /api/admin/image-library/{image_id}" in excluded
    assert "cloud upload" in excluded
    assert "WeCom media upload" in excluded


def test_readiness_checker_passes_with_good_fixture_reports(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert report["readiness_status"] == "canary_plan_ready"
    assert report["recommendation"] == "GO_TO_STAGING_CANARY_SIGNOFF"


def test_readiness_checker_fails_when_media_smoke_has_blocker(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, smoke_blocker=True))
    assert report["ok"] is False
    assert any(item["reason"] == "media_smoke_not_pass" for item in report["blockers"])
    assert any(item["reason"] == "media_smoke_has_blockers" for item in report["blockers"])


def test_readiness_checker_fails_when_external_upload_true(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, external_upload=True))
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "external_upload_executed"} in report["blockers"]


def test_readiness_checker_fails_when_rollback_dry_run_missing(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, rollback=False))
    assert report["ok"] is False
    assert {"reason": "rollback_dry_run_missing"} in report["blockers"]


def test_proxy_pseudo_config_contains_pseudo_only_and_no_production_secrets() -> None:
    text = _read_doc("batch_1_media_readonly_proxy_pseudo_config.md")
    assert text.count("PSEUDO ONLY") >= 6
    lowered = text.lower()
    for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
        assert forbidden not in lowered


def test_runbook_contains_rollback_steps() -> None:
    text = _read_doc("batch_1_media_readonly_canary_runbook.md")
    assert "## Rollback" in text
    assert "AICRM_NEXT_ROUTE_MEDIA_READONLY=false" in text
    assert "Route owner returns to old Flask" in text


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_1_media_canary_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
