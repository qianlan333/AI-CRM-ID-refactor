from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_4_user_ops_canary_readiness as readiness
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
    next_missing_activation: bool = False,
    wecom_dispatch: bool = False,
    media_upload: bool = False,
    deferred_jobs: bool = False,
    missing_rollback: bool = False,
) -> Namespace:
    smoke = tmp_path / "user_ops_smoke.json"
    parity = tmp_path / "user_ops_parity.json"
    dual = tmp_path / "readonly_dual.json"
    route_status = tmp_path / "route_status.json"
    real_pg = tmp_path / "real_pg.md"
    flags = tmp_path / "route_flags.md"

    smoke_routes = [
        {"name": name, "method": "GET", "path": f"/{name}", "status": "PASS", "ok": True, "issues": [], "legacy_drift": []}
        for name in sorted(readiness.REQUIRED_SMOKE_ROUTE_NAMES)
    ]
    if next_missing_activation:
        for route in smoke_routes:
            if route["name"] == "overview.default":
                route["status"] = "FAIL"
                route["ok"] = False
                route["issues"] = [
                    {"path": "/api/admin/user-ops/overview", "side": "next", "rule": "card_label", "label": "激活待录入"}
                ]
    else:
        for route in smoke_routes:
            if route["name"] == "overview.default":
                route["status"] = "WARN"
                route["legacy_drift"] = [
                    {
                        "endpoint": "/api/admin/user-ops/overview",
                        "field": "激活待录入",
                        "rule": "card_label",
                        "reason": "legacy_missing_required_card_label",
                        "next_satisfies_contract": True,
                    }
                ]
    dual_results = [
        {
            "scope": "user_ops",
            "endpoint": endpoint,
            "method": "GET",
            "path": f"/{endpoint}",
            "old_status": 200,
            "next_status": 200,
            "status": "PASS",
            "issues": [],
            "legacy_drift": [],
        }
        for endpoint in sorted(readiness.REQUIRED_DUAL_ENDPOINTS)
    ]
    for item in dual_results:
        if item["endpoint"] == "overview.default":
            item["status"] = "WARN"
            item["issues"] = [
                {
                    "side": "old",
                    "severity": "warning",
                    "reason": "legacy_missing_required_card_label",
                    "field": "激活待录入",
                    "next_satisfies_contract": True,
                }
            ]
            item["legacy_drift"] = [
                {
                    "endpoint": "overview.default",
                    "field": "激活待录入",
                    "rule": "card_label",
                    "reason": "legacy_missing_required_card_label",
                    "next_satisfies_contract": True,
                    }
                ]
    overview_dual = next(item for item in dual_results if item["endpoint"] == "overview.default")
    overview_smoke = next(item for item in smoke_routes if item["name"] == "overview.default")
    _write_json(
        smoke,
        {
            "ok": not smoke_blocker and not next_missing_activation,
            "blockers": [{"reason": "route_returned_5xx"}] if smoke_blocker else [],
            "warnings": [{"reason": "legacy_missing_required_card_label"}],
            "skipped": [],
            "route_results": smoke_routes,
            "legacy_drift": overview_smoke.get("legacy_drift", []),
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "wecom_dispatch_executed": wecom_dispatch,
                "media_upload_executed": media_upload,
                "deferred_jobs_executed": deferred_jobs,
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
            "warnings": [{"endpoint": "overview.default", "path": "/api/admin/user-ops/overview", "issues": overview_dual["issues"]}],
            "skipped": [],
            "legacy_drift": overview_dual["legacy_drift"],
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
            "AICRM_NEXT_ROUTE_USER_OPS_READONLY=true",
            "AICRM_NEXT_ROUTE_USER_OPS_WRITES=false",
            "AICRM_NEXT_USER_OPS_DND=false",
            "AICRM_NEXT_USER_OPS_BATCH_SEND=false",
            "AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false",
            "AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false",
            "AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false",
        ]
    )
    if not missing_rollback:
        flags_text += "\nAICRM_NEXT_ROUTE_USER_OPS_READONLY=false\n"
    flags.write_text(flags_text, encoding="utf-8")
    return Namespace(
        user_ops_smoke_json=str(smoke),
        user_ops_parity_json=str(parity),
        readonly_dual_json=str(dual),
        route_status_json=str(route_status),
        real_pg_evidence=str(real_pg),
        route_flags_doc=str(flags),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_canary_plan_includes_only_user_ops_readonly_routes() -> None:
    text = _read_doc("batch_4_user_ops_readonly_canary_plan.md")
    included = text[text.index("## Included Readonly Routes") : text.index("## Excluded Operations")]
    assert "GET /admin/user-ops/ui" in included
    assert "GET /api/admin/user-ops/send-records" in included
    assert "POST " not in included
    assert "PUT " not in included
    assert "DELETE " not in included


def test_canary_plan_excludes_dnd_batch_send_and_deferred_jobs() -> None:
    text = _read_doc("batch_4_user_ops_readonly_canary_plan.md")
    excluded = text[text.index("## Excluded Operations") : text.index("## Entry Criteria")]
    for expected in ("DND write", "batch-send preview", "batch-send execute", "deferred jobs", "WeCom dispatch"):
        assert expected in excluded


def test_readiness_checker_passes_with_good_fixture_reports(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert report["readiness_status"] == "canary_plan_ready"
    assert report["recommendation"] == "GO_TO_STAGING_CANARY_SIGNOFF"


def test_readiness_checker_fails_when_user_ops_smoke_has_blocker(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, smoke_blocker=True))
    assert report["ok"] is False
    assert any(item["reason"] == "user_ops_smoke_not_pass" for item in report["blockers"])
    assert any(item["reason"] == "user_ops_smoke_has_blockers" for item in report["blockers"])


def test_readiness_checker_fails_when_next_missing_activation_pending(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, next_missing_activation=True))
    assert report["ok"] is False
    assert any(item["reason"] == "next_missing_activation_pending_card" for item in report["blockers"])


def test_readiness_checker_accepts_old_missing_activation_pending_as_legacy_drift(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert any(item.get("field") == "激活待录入" and item.get("next_satisfies_contract") is True for item in report["legacy_drift"])


def test_readiness_checker_fails_when_side_effect_flags_true(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, wecom_dispatch=True, media_upload=True, deferred_jobs=True))
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "wecom_dispatch_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "media_upload_executed"} in report["blockers"]
    assert {"reason": "side_effect_safety_violation", "field": "deferred_jobs_executed"} in report["blockers"]


def test_readiness_checker_fails_when_rollback_instruction_missing(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, missing_rollback=True))
    assert report["ok"] is False
    assert any(item["reason"] == "route_flags_not_ready" for item in report["blockers"])


def test_proxy_pseudo_config_contains_pseudo_only_and_no_production_secrets() -> None:
    text = _read_doc("batch_4_user_ops_readonly_proxy_pseudo_config.md")
    assert text.count("PSEUDO ONLY") >= 6
    lowered = text.lower()
    for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
        assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_4_user_ops_canary_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
