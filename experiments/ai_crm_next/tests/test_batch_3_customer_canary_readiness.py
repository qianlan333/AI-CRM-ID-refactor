from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_3_customer_canary_readiness as readiness

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
    missing_sample: bool = False,
    external_wecom: bool = False,
    archive_sync: bool = False,
    tag_refresh: bool = False,
    missing_rollback: bool = False,
) -> Namespace:
    smoke = tmp_path / "customer_smoke.json"
    parity = tmp_path / "customer_parity.json"
    dual = tmp_path / "readonly_dual.json"
    route_status = tmp_path / "route_status.json"
    real_pg = tmp_path / "real_pg.md"
    flags = tmp_path / "route_flags.md"

    smoke_routes = [
        {"name": name, "method": "GET", "path": f"/{name}", "status": "PASS", "ok": True}
        for name in sorted(readiness.REQUIRED_SMOKE_ROUTE_NAMES)
    ]
    dual_results = []
    for endpoint in sorted(readiness.REQUIRED_DUAL_ENDPOINTS):
        status = "SKIPPED" if missing_sample and endpoint in readiness.REQUIRED_SAMPLE_ENDPOINTS else "PASS"
        dual_results.append(
            {
                "scope": "customer",
                "endpoint": endpoint,
                "method": "GET",
                "path": "/api/customers/external_user_masked_001" if endpoint in readiness.REQUIRED_SAMPLE_ENDPOINTS else f"/{endpoint}",
                "old_status": None if status == "SKIPPED" else 200,
                "next_status": None if status == "SKIPPED" else 200,
                "status": status,
                "reason": "no_customer_sample" if status == "SKIPPED" else "",
                "issues": [],
            }
        )
    _write_json(
        smoke,
        {
            "ok": not smoke_blocker,
            "blockers": [{"reason": "route_returned_5xx"}] if smoke_blocker else [],
            "warnings": [],
            "skipped": [],
            "sample_external_userid": "" if missing_sample else "external_user_masked_001",
            "route_results": smoke_routes,
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "external_wecom_call_executed": external_wecom,
                "archive_sync_executed": archive_sync,
                "tag_refresh_executed": tag_refresh,
                "openclaw_webhook_executed": False,
                "default_endpoints_get_only": True,
            },
        },
    )
    _write_json(parity, {"ok": True, "overall": "PASS", "blockers": [], "warnings": [], "skipped": []})
    _write_json(
        dual,
        {
            "ok": True,
            "blockers": [],
            "warnings": [],
            "skipped": [item for item in dual_results if item["status"] == "SKIPPED"],
            "endpoint_results": dual_results,
            "side_effect_safety": {"old_service_write_endpoints_executed": False},
        },
    )
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
            "AICRM_NEXT_ROUTE_CUSTOMER_READONLY=true",
            "AICRM_NEXT_ROUTE_CUSTOMER_WRITES=false",
            "AICRM_NEXT_EXTERNAL_WECOM_SYNC=false",
            "AICRM_NEXT_EXTERNAL_ARCHIVE_SYNC=false",
            "AICRM_NEXT_EXTERNAL_TAG_REFRESH=false",
            "AICRM_NEXT_EXTERNAL_OPENCLAW=false",
        ]
    )
    if not missing_rollback:
        flags_text += "\nAICRM_NEXT_ROUTE_CUSTOMER_READONLY=false\n"
    flags.write_text(flags_text, encoding="utf-8")
    return Namespace(
        customer_smoke_json=str(smoke),
        customer_parity_json=str(parity),
        readonly_dual_json=str(dual),
        route_status_json=str(route_status),
        real_pg_evidence=str(real_pg),
        route_flags_doc=str(flags),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_canary_plan_includes_only_customer_readonly_routes() -> None:
    text = _read_doc("batch_3_customer_readonly_canary_plan.md")
    included = text[text.index("## Included Readonly Routes") : text.index("## Excluded Routes And Operations")]
    assert "GET /admin/customers" in included
    assert "GET /api/messages/{external_userid}/recent?limit=5" in included
    assert "POST " not in included
    assert "PUT " not in included
    assert "DELETE " not in included


def test_canary_plan_excludes_write_and_external_operations() -> None:
    text = _read_doc("batch_3_customer_readonly_canary_plan.md")
    excluded = text[text.index("## Excluded Routes And Operations") : text.index("## Entry Criteria")]
    for expected in ("WeCom contact sync", "archive sync", "tag refresh", "OpenClaw push", "any customer write route"):
        assert expected in excluded


def test_readiness_checker_passes_with_good_fixture_reports(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert report["readiness_status"] == "canary_plan_ready"
    assert report["recommendation"] == "GO_TO_STAGING_CANARY_SIGNOFF"


def test_readiness_checker_fails_when_customer_smoke_has_blocker(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, smoke_blocker=True))
    assert report["ok"] is False
    assert any(item["reason"] == "customer_smoke_not_pass" for item in report["blockers"])
    assert any(item["reason"] == "customer_smoke_has_blockers" for item in report["blockers"])


def test_readiness_checker_fails_when_readonly_dual_run_missing_sample_evidence(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, missing_sample=True))
    assert report["ok"] is False
    assert any(item["reason"] == "sample_external_userid_missing" for item in report["blockers"])
    assert any(item["reason"] == "sample_dependent_endpoint_skipped" for item in report["blockers"])


def test_readiness_checker_fails_when_external_side_effect_flags_true(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, external_wecom=True, archive_sync=True, tag_refresh=True))
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "external_wecom_call_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "archive_sync_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "tag_refresh_executed"} in report["blockers"]


def test_readiness_checker_fails_when_rollback_instruction_missing(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, missing_rollback=True))
    assert report["ok"] is False
    assert any(item["reason"] == "route_flags_not_ready" for item in report["blockers"])


def test_proxy_pseudo_config_contains_pseudo_only_and_no_production_secrets() -> None:
    text = _read_doc("batch_3_customer_readonly_proxy_pseudo_config.md")
    assert text.count("PSEUDO ONLY") >= 6
    lowered = text.lower()
    for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
        assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_3_customer_canary_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
