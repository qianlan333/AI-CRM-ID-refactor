from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_6_automation_canary_readiness as readiness

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_doc(name: str) -> str:
    return (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_reports(
    tmp_path: Path,
    *,
    smoke_blocker: bool = False,
    activation_webhook_executed: bool = False,
    openclaw_push_executed: bool = False,
    workflow_runtime_executed: bool = False,
    missing_rollback: bool = False,
) -> Namespace:
    smoke = tmp_path / "automation_smoke.json"
    parity = tmp_path / "automation_parity.json"
    route_status = tmp_path / "route_status.json"
    real_pg = tmp_path / "real_pg.md"
    flags = tmp_path / "route_flags.md"

    route_results = []
    for name in sorted(readiness.REQUIRED_SMOKE_ROUTE_NAMES):
        path = {
            "admin_automation_page": "/admin/automation-conversion",
            "overview.default": "/api/admin/automation-conversion/overview",
            "pools.default": "/api/admin/automation-conversion/pools",
            "members.default": "/api/admin/automation-conversion/members",
            "member_detail.sample": "/api/admin/automation-conversion/members/{member_id}",
            "execution_records.default": "/api/admin/automation-conversion/execution-records",
        }[name]
        old_path = path
        if name == "overview.default":
            old_path = "/api/admin/automation-conversion/dashboard"
        elif name == "pools.default":
            old_path = "/api/admin/automation-conversion/dashboard"
        elif name == "members.default":
            old_path = "/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50"
        elif name == "member_detail.sample":
            old_path = "/api/admin/automation-conversion/member?external_contact_id=external_user_masked_automation_001"
        elif name == "execution_records.default":
            old_path = "/api/admin/automation-conversion/executions"
        route_results.append(
            {
                "name": name,
                "method": "GET",
                "path": path,
                "next_path": path,
                "old_path": old_path,
                "status": "PASS",
                "ok": True,
                "old_status": 200,
                "next_status": 200,
                "issues": [],
                "legacy_drift": [],
            }
        )
    if smoke_blocker:
        route_results[0]["status"] = "FAIL"
        route_results[0]["ok"] = False
        route_results[0]["issues"] = [{"reason": "next_status_5xx"}]
    legacy_drift = [
        {
            "endpoint": "/admin/automation-conversion",
            "field": "admin_auth_redirect",
            "rule": "legacy_admin_auth_redirect",
            "reason": "legacy_admin_auth_redirect",
            "next_satisfies_contract": True,
        },
        {
            "endpoint": "/api/admin/automation-conversion/overview",
            "field": "automation_readonly_route",
            "rule": "legacy_missing_read_route",
            "reason": "legacy_missing_read_route",
            "next_satisfies_contract": True,
        },
    ]
    _write_json(
        smoke,
        {
            "ok": not smoke_blocker,
            "mode": "dual-run",
            "blockers": [{"reason": "route_returned_5xx"}] if smoke_blocker else [],
            "warnings": [],
            "skipped": [{"reason": "fake_writes_not_requested"}],
            "route_results": route_results,
            "legacy_drift": legacy_drift,
            "sample_member_id": "automation_member_masked_001",
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "openclaw_push_executed": openclaw_push_executed,
                "wecom_dispatch_executed": False,
                "external_webhook_executed": False,
                "activation_webhook_executed": activation_webhook_executed,
                "workflow_runtime_executed": workflow_runtime_executed,
                "next_fake_writes_executed": False,
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
            "AICRM_NEXT_ROUTE_AUTOMATION_READONLY=true",
            "AICRM_NEXT_ROUTE_AUTOMATION_WRITES=false",
            "AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK=false",
            "AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME=false",
            "AICRM_NEXT_AUTOMATION_AGENT_RUNTIME=false",
            "AICRM_NEXT_EXTERNAL_OPENCLAW=false",
            "AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false",
            "AICRM_NEXT_EXTERNAL_WEBHOOK=false",
        ]
    )
    if not missing_rollback:
        flags_text += "\nAICRM_NEXT_ROUTE_AUTOMATION_READONLY=false\n"
    flags.write_text(flags_text, encoding="utf-8")
    return Namespace(
        automation_smoke_json=str(smoke),
        automation_parity_json=str(parity),
        route_status_json=str(route_status),
        real_pg_evidence=str(real_pg),
        route_flags_doc=str(flags),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_canary_plan_includes_only_automation_readonly_routes() -> None:
    text = _read_doc("batch_6_automation_readonly_canary_plan.md")
    included = text[text.index("## Included Readonly Routes") : text.index("## Excluded Operations")]
    assert "GET /admin/automation-conversion" in included
    assert "GET /api/admin/automation-conversion/members/{member_id}" in included
    assert "POST " not in included
    assert "PUT " not in included
    assert "DELETE " not in included


def test_canary_plan_excludes_write_external_and_runtime_operations() -> None:
    text = _read_doc("batch_6_automation_readonly_canary_plan.md")
    excluded = text[text.index("## Excluded Operations") : text.index("## Entry Criteria")]
    for expected in (
        "manual override",
        "confirm conversion",
        "activation webhook",
        "OpenClaw push",
        "workflow runtime",
        "agent runtime",
        "WeCom dispatch",
        "external webhook",
    ):
        assert expected in excluded


def test_readiness_checker_passes_with_good_fixture_reports(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert report["readiness_status"] == "canary_plan_ready"
    assert report["recommendation"] == "GO_TO_STAGING_CANARY_SIGNOFF"


def test_readiness_checker_fails_when_automation_smoke_has_blocker(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, smoke_blocker=True))
    assert report["ok"] is False
    assert any(item["reason"] == "automation_smoke_not_pass" for item in report["blockers"])
    assert any(item["reason"] == "automation_smoke_has_blockers" for item in report["blockers"])


def test_readiness_checker_accepts_legacy_missing_read_route_if_documented(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    reasons = {item["reason"] for item in report["legacy_drift"]}
    assert "legacy_admin_auth_redirect" in reasons
    assert "legacy_missing_read_route" in reasons


def test_readiness_checker_fails_when_external_or_runtime_side_effects_true(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(
        _fixture_reports(
            tmp_path,
            activation_webhook_executed=True,
            openclaw_push_executed=True,
            workflow_runtime_executed=True,
        )
    )
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "activation_webhook_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "openclaw_push_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "workflow_runtime_executed"} in report["blockers"]


def test_readiness_checker_fails_when_rollback_instruction_missing(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, missing_rollback=True))
    assert report["ok"] is False
    assert any(item["reason"] == "route_flags_not_ready" for item in report["blockers"])


def test_proxy_pseudo_config_contains_pseudo_only_and_no_production_secrets() -> None:
    text = _read_doc("batch_6_automation_readonly_proxy_pseudo_config.md")
    assert text.count("PSEUDO ONLY") >= 6
    lowered = text.lower()
    for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
        assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_6_automation_canary_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
