from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import check_batch_2_product_canary_readiness as readiness
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
    checkout_executed: bool = False,
    payment_provider_called: bool = False,
) -> Namespace:
    smoke = tmp_path / "product_smoke.json"
    parity = tmp_path / "commerce_parity.json"
    route_status = tmp_path / "route_status.json"
    _write_json(
        smoke,
        {
            "ok": not smoke_blocker,
            "blockers": [{"reason": "route_returned_5xx"}] if smoke_blocker else [],
            "warnings": [],
            "skipped": [],
            "checkout_endpoints": ["/api/checkout/wechat", "/api/checkout/alipay"],
            "route_results": [{"name": name, "method": "GET", "path": f"/{name}", "ok": True} for name in sorted(readiness.REQUIRED_READ_NAMES)],
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "checkout_executed": checkout_executed,
                "payment_provider_called": payment_provider_called,
                "external_payment_executed": False,
                "default_endpoints_get_only": True,
                "checkout_endpoints_in_default_smoke": False,
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
    return Namespace(
        product_smoke_json=str(smoke),
        commerce_parity_json=str(parity),
        route_status_json=str(route_status),
        output_md=str(tmp_path / "out.md"),
        output_json=str(tmp_path / "out.json"),
    )


def test_canary_plan_includes_only_product_readonly_routes() -> None:
    text = _read_doc("batch_2_product_readonly_canary_plan.md")
    included = text[text.index("## Included Readonly Routes") : text.index("## Excluded Routes")]
    assert "GET /admin/wechat-pay/products" in included
    assert "GET /api/products/{page_slug}" in included
    assert "POST " not in included
    assert "PUT " not in included
    assert "DELETE " not in included


def test_canary_plan_excludes_product_write_routes() -> None:
    text = _read_doc("batch_2_product_readonly_canary_plan.md")
    excluded = text[text.index("## Excluded Routes") : text.index("## Entry Criteria")]
    assert "POST /api/admin/wechat-pay/products" in excluded
    assert "PUT /api/admin/wechat-pay/products/{product_id}" in excluded
    assert "DELETE /api/admin/wechat-pay/products/{product_id}" in excluded


def test_canary_plan_excludes_checkout_and_notify_routes() -> None:
    text = _read_doc("batch_2_product_readonly_canary_plan.md")
    excluded = text[text.index("## Excluded Routes") : text.index("## Entry Criteria")]
    assert "POST /api/checkout/wechat" in excluded
    assert "POST /api/checkout/alipay" in excluded
    assert "POST /api/wechat-pay/notify" in excluded
    assert "POST /api/alipay/notify" in excluded


def test_readiness_checker_passes_with_good_fixture_reports(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["ok"] is True
    assert report["readiness_status"] == "canary_plan_ready"
    assert report["recommendation"] == "GO_TO_STAGING_CANARY_SIGNOFF"


def test_readiness_checker_fails_when_product_smoke_has_blocker(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, smoke_blocker=True))
    assert report["ok"] is False
    assert any(item["reason"] == "product_smoke_not_pass" for item in report["blockers"])
    assert any(item["reason"] == "product_smoke_has_blockers" for item in report["blockers"])


def test_readiness_checker_fails_when_checkout_executed(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, checkout_executed=True))
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "checkout_executed"} in report["blockers"]


def test_readiness_checker_fails_when_payment_provider_called(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path, payment_provider_called=True))
    assert report["ok"] is False
    assert {"reason": "side_effect_safety_violation", "field": "payment_provider_called"} in report["blockers"]


def test_readiness_checker_has_rollback_instruction(tmp_path: Path) -> None:
    report = readiness.build_readiness_report(_fixture_reports(tmp_path))
    assert report["rollback_dry_run"]["route_flag_rollback_instruction"] == "AICRM_NEXT_ROUTE_PRODUCT_READONLY=false"
    assert report["rollback_dry_run"]["expected_owner_after_rollback"] == "old Flask"


def test_proxy_pseudo_config_contains_pseudo_only_and_no_production_secrets() -> None:
    text = _read_doc("batch_2_product_readonly_proxy_pseudo_config.md")
    assert text.count("PSEUDO ONLY") >= 6
    lowered = text.lower()
    for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
        assert forbidden not in lowered


def test_no_old_backend_imports() -> None:
    text = (PROJECT_ROOT / "tools" / "check_batch_2_product_canary_readiness.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
