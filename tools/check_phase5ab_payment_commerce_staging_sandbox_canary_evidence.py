#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml


DOC = ROOT / "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py"
PROD_REVIEW_RUNNER = ROOT / "tools/run_phase5ab_payment_commerce_production_readiness_review.py"
TEST = ROOT / "tests/test_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py"
NEXT_BUNDLE = "phase_5ac_payment_commerce_production_canary_readiness_bundle"
COMPLETED_STEP = "phase_5ab_payment_commerce_staging_sandbox_canary_evidence_completed"
REQUIRED_ENV = {
    "AICRM_PAYMENT_COMMERCE_LIVE_ADAPTER_ENABLED",
    "AICRM_PAYMENT_COMMERCE_LIVE_CALL_APPROVED",
    "AICRM_PAYMENT_COMMERCE_PROVIDER_CONFIG_REVIEWED",
    "AICRM_PAYMENT_COMMERCE_SANDBOX_MODE_APPROVED",
    "AICRM_PAYMENT_COMMERCE_NO_MONEY_MOVEMENT_CONFIRMED",
    "AICRM_PHASE5AB_PAYMENT_COMMERCE_STAGING_SANDBOX_APPROVED",
    "AICRM_PHASE5AB_PAYMENT_COMMERCE_TARGET_APPROVED",
}
REQUIRED_ARGS = {
    "--execute-staging-sandbox-canary",
    "--synthetic-order-id",
    "--idempotency-key",
    "--confirm-no-real-money-movement",
    "--confirm-sandbox-only",
    "--confirm-no-production-order-mutation",
    "--confirm-no-webhook-cutover",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.md",
    "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
    "tools/run_phase5ab_payment_commerce_production_readiness_review.py",
    "tools/check_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "stripe", "alipay", "wechatpay"}
FORBIDDEN_CALLS = {"post", "put", "patch", "delete", "send", "capture", "settle", "charge", "refund"}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"aicrm_next/main.py"}


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {line.strip() for line in proc.stdout.splitlines() if proc.returncode == 0 and line.strip()}


def _changed_files() -> set[str]:
    return set().union(_run_git(["diff", "--name-only", "origin/main...HEAD"]), _run_git(["diff", "--name-only"]), _run_git(["diff", "--name-only", "--cached"]), _run_git(["ls-files", "--others", "--exclude-standard"]))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _imports_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
    return imports, calls


def _static_blockers(path: Path) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8").lower()
    imports, calls = _imports_calls(path)
    if FORBIDDEN_IMPORTS & imports:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden modules: {sorted(FORBIDDEN_IMPORTS & imports)}")
    if FORBIDDEN_CALLS & calls:
        blockers.append(f"{path.relative_to(ROOT)} calls forbidden names: {sorted(FORBIDDEN_CALLS & calls)}")
    for token in ("api.mch.weixin.qq.com", "stripe.com", "alipay.com", "real_money_movement_executed\": true", "production_order_state_mutation_executed\": true", "production_payment_webhook_cutover_executed\": true"):
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} contains forbidden token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, STAGING_RUNNER, PROD_REVIEW_RUNNER, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    auth = _dict(data.get("authorizations"))
    if auth.get("staging_sandbox_canary_possible_with_approval") is not True:
        blockers.append("staging sandbox canary must be possible with approval")
    for key, value in auth.items():
        if key != "staging_sandbox_canary_possible_with_approval" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    canary = _dict(data.get("staging_sandbox_canary"))
    if canary.get("default_blocked") is not True or canary.get("single_synthetic_order_only") is not True:
        blockers.append("staging_sandbox_canary must default blocked and single-order")
    if canary.get("batch_replay_allowed") is not False or canary.get("no_real_money_movement_required") is not True:
        blockers.append("staging_sandbox_canary safety flags invalid")
    if not REQUIRED_ENV <= {str(item) for item in _list(canary.get("required_env"))}:
        blockers.append("staging_sandbox_canary.required_env incomplete")
    if not REQUIRED_ARGS <= {str(item) for item in _list(canary.get("required_args"))}:
        blockers.append("staging_sandbox_canary.required_args incomplete")
    for key, value in _dict(data.get("target_safety")).items():
        if key.endswith("_allowed") and value is not False:
            blockers.append(f"target_safety.{key} must be false")
    review = _dict(data.get("production_readiness_review"))
    for key in ("production_provider_call_executed", "real_money_movement_executed", "production_order_state_mutation_executed", "production_payment_webhook_cutover_executed"):
        if review.get(key) is not False:
            blockers.append(f"production_readiness_review.{key} must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#740":
        blockers.append("phase_execution_state.last_merged_pr must be #740")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (STAGING_RUNNER, PROD_REVIEW_RUNNER):
        blockers.extend(_static_blockers(path))
        text = path.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{path.name} missing {arg}")
    for arg in REQUIRED_ARGS:
        if arg not in STAGING_RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"staging runner missing {arg}")
    for arg in ("--staging-evidence-json", "--confirm-no-production-provider-call", "--confirm-no-money-movement", "--confirm-no-order-mutation", "--confirm-no-webhook-cutover"):
        if arg not in PROD_REVIEW_RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"production review runner missing {arg}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("real payment capture enabled", "real refund enabled", "real settlement enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AB allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AB Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
