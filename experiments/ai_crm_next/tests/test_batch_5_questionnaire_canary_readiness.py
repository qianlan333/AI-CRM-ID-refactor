from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_5_questionnaire_canary_readiness as readiness
from tools.doc_paths import read_experiment_doc

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_doc(name: str) -> str:
    return read_experiment_doc(name)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_reports(
    tmp_path: Path,
    *,
    smoke_blocker: bool = False,
    submit_executed: bool = False,
    oauth_executed: bool = False,
    wecom_tag_executed: bool = False,
    external_webhook_executed: bool = False,
    missing_rollback: bool = False,
) -> Namespace:
    smoke = tmp_path / "questionnaire_smoke.json"
    parity = tmp_path / "questionnaire_parity.json"
    route_status = tmp_path / "route_status.json"
    real_pg = tmp_path / "real_pg.md"
    flags = tmp_path / "route_flags.md"

    route_results = [
        {
            "name": name,
            "method": "GET",
            "path": f"/{name}",
            "next_path": f"/{name}",
            "old_path": f"/{name}",
            "status": "PASS",
            "ok": True,
            "issues": [],
            "legacy_drift": [],
        }
        for name in sorted(readiness.REQUIRED_SMOKE_ROUTE_NAMES)
    ]
    if smoke_blocker:
        route_results[0]["status"] = "FAIL"
        route_results[0]["ok"] = False
        route_results[0]["issues"] = [{"reason": "next_status_5xx"}]
    legacy_drift = [
        {
            "endpoint": "/api/h5/questionnaires/{slug}",
            "field": "wechat_browser_gate",
            "rule": "legacy_wechat_browser_gate",
            "reason": "legacy_wechat_browser_gate",
            "next_satisfies_contract": True,
        },
        {
            "endpoint": "/api/h5/questionnaires/{slug}/result/{submission_id}",
            "field": "public_result_api_route",
            "rule": "legacy_missing_public_result_api",
            "reason": "legacy_missing_public_result_api",
            "next_satisfies_contract": True,
        },
    ]
    _write_json(
        smoke,
        {
            "ok": not smoke_blocker,
            "blockers": [{"reason": "route_returned_5xx"}] if smoke_blocker else [],
            "warnings": [],
            "skipped": [{"reason": "fake_submit_not_requested"}],
            "route_results": route_results,
            "legacy_drift": legacy_drift,
            "sample_questionnaire_id": "1",
            "sample_slug": "questionnaire_slug_masked_001",
            "sample_submission_id": "submission_masked_001",
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "old_submit_executed": submit_executed,
                "real_oauth_executed": oauth_executed,
                "wecom_tag_executed": wecom_tag_executed,
                "external_webhook_executed": external_webhook_executed,
                "next_fake_submit_executed": False,
                "default_endpoints_get_only": True,
            },
        },
    )
    _write_json(parity, {"ok": True, "overall": "PASS", "blockers": [], "warnings": [], "skipped": []})
    _write_json(
        route_status,
        {
            "ok": True,
            "summary": {"routes": 14, "passed": 14, "screenshots_generated": 14},
            "route_results": [{"route": route, "ok": True} for route in sorted(readiness.REQUIRED_SCREENSHOT_ROUTES)],
        },
    )
    real_pg.write_text("Local real PostgreSQL integration passed.\n", encoding="utf-8")
    flags_text = "\n".join(
        [
            "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true",
            "AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false",
            "AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false",
            "AICRM_NEXT_QUESTIONNAIRE_OAUTH=false",
            "AICRM_NEXT_EXTERNAL_WECOM_TAG=false",
            "AICRM_NEXT_EXTERNAL_WEBHOOK=false",
        ]
    )
    if not missing_rollback:
        flags_text += "\nAICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false\n"
    flags.write_text(flags_text, encoding="utf-8")
    return Namespace(
        questionnaire_smoke_json=str(smoke),
        questionnaire_parity_json=str(parity),
        route_status_json=str(route_status),
        real_pg_evidence=str(real_pg),
        route_flags_doc=str(flags),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_canary_plan_includes_only_questionnaire_readonly_routes() -> None:
    text = _read_doc("batch_5_questionnaire_readonly_canary_plan.md")
    included = text[text.index("## Included Readonly Routes") : text.index("## Excluded Operations")]
    assert "GET /admin/questionnaires" in included
    assert "GET /api/h5/questionnaires/{slug}/result/{submission_id}" in included
    assert "POST " not in included
    assert "PUT " not in included
    assert "DELETE " not in included


def test_canary_plan_excludes_writes_submit_oauth_tag_and_webhook() -> None:
    text = _read_doc("batch_5_questionnaire_readonly_canary_plan.md")
    excluded = text[text.index("## Excluded Operations") : text.index("## Entry Criteria")]
    for expected in ("admin create/update/delete/enable/disable", "H5 submit", "OAuth start/callback", "WeCom tag", "webhook"):
        assert expected in excluded


def test_readiness_checker_passes_with_good_fixture_reports(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert report["readiness_status"] == "canary_plan_ready"
    assert report["recommendation"] == "GO_TO_STAGING_CANARY_SIGNOFF"


def test_readiness_checker_fails_when_questionnaire_smoke_has_blocker(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, smoke_blocker=True))
    assert report["ok"] is False
    assert any(item["reason"] == "questionnaire_smoke_not_pass" for item in report["blockers"])
    assert any(item["reason"] == "questionnaire_smoke_has_blockers" for item in report["blockers"])


def test_readiness_checker_accepts_legacy_wechat_gate_and_result_route_drift(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    reasons = {item["reason"] for item in report["legacy_drift"]}
    assert "legacy_wechat_browser_gate" in reasons
    assert "legacy_missing_public_result_api" in reasons


def test_readiness_checker_fails_when_submit_or_external_side_effects_true(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(
        _fixture_reports(
            tmp_path,
            submit_executed=True,
            oauth_executed=True,
            wecom_tag_executed=True,
            external_webhook_executed=True,
        )
    )
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "old_submit_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "real_oauth_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "wecom_tag_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "external_webhook_executed"} in report["blockers"]


def test_readiness_checker_fails_when_rollback_instruction_missing(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, missing_rollback=True))
    assert report["ok"] is False
    assert any(item["reason"] == "route_flags_not_ready" for item in report["blockers"])


def test_proxy_pseudo_config_contains_pseudo_only_and_no_production_secrets() -> None:
    text = _read_doc("batch_5_questionnaire_readonly_proxy_pseudo_config.md")
    assert text.count("PSEUDO ONLY") >= 6
    lowered = text.lower()
    for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
        assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_5_questionnaire_canary_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
