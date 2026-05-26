from __future__ import annotations

import argparse
from pathlib import Path

import tools.check_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub as checker
import tools.run_phase5af_openclaw_mcp_ai_assist_fake_stub_production_dry_run as prod_runner
import tools.run_phase5af_openclaw_mcp_ai_assist_fake_stub_staging_smoke as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.md"
PLAN_YAML = ROOT / "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_staging_fake_stub_evidence_has_no_live_calls() -> None:
    report = staging_runner.build_report(argparse.Namespace(mode="fake_stub_contract"))
    assert report["ok"] is True
    assert report["real_mcp_call_executed"] is False
    assert report["real_openclaw_call_executed"] is False
    assert report["real_llm_call_executed"] is False
    assert report["deepseek_call_executed"] is False
    assert report["outbound_send_executed"] is False
    assert report["prompt_redacted"] is True
    assert report["credential_redacted"] is True


def test_production_fake_stub_dry_run_default_blocked_and_confirmed_ready() -> None:
    blocked = prod_runner.build_report(argparse.Namespace(confirm_no_live_call=False))
    assert blocked["ok"] is False
    assert blocked["result_status"] == "not_executed_missing_confirm_no_live_call"
    ready = prod_runner.build_report(argparse.Namespace(confirm_no_live_call=True))
    assert ready["ok"] is True
    assert ready["real_mcp_call_executed"] is False
    assert ready["real_openclaw_call_executed"] is False
    assert ready["real_llm_call_executed"] is False
    assert ready["deepseek_call_executed"] is False


def test_yaml_authorizations_and_side_effect_safety_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert all(value is False for value in data["side_effect_safety"].values())


def test_contract_and_fake_stub_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    methods = {item["name"] for item in data["adapter_contract"]["methods"]}
    assert checker.REQUIRED_METHODS <= methods
    fake = data["fake_stub_contract"]
    assert fake["network_call_allowed"] is False
    assert fake["real_mcp_call_allowed"] is False
    assert fake["real_openclaw_call_allowed"] is False
    assert fake["real_llm_call_allowed"] is False
    assert fake["deepseek_call_allowed"] is False
    assert fake["prompt_raw_output_allowed"] is False


def test_error_mapping_and_idempotency_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_ERRORS <= set(data["error_mapping"]["required_error_codes"])
    assert all(value is True for value in data["idempotency_policy"].values())


def test_runners_do_not_import_live_provider_modules() -> None:
    for path in (checker.STAGING_RUNNER, checker.PROD_RUNNER):
        imports = checker._imports(path)
        assert not (imports & {"requests", "httpx", "aiohttp", "urllib", "openai", "anthropic"})
        blockers = checker._runner_static_blockers(path)
        assert blockers == []


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "real mcp call enabled",
        "real openclaw call enabled",
        "real llm call enabled",
        "deepseek call enabled",
        "outbound send enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
