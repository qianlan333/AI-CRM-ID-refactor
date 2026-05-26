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


DOC = ROOT / "docs/development/phase_5v_media_upload_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5v_media_upload_live_adapter_behind_flag.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5v_media_upload_live_staging_evidence.py"
PROD_RUNNER = ROOT / "tools/run_phase5v_media_upload_live_production_dry_run_gate.py"
TEST = ROOT / "tests/test_phase5v_media_upload_live_adapter_behind_flag.py"
RUNTIME_FILES = [
    ROOT / "aicrm_next/integration_gateway/media_live_adapter.py",
    ROOT / "aicrm_next/integration_gateway/media_live_gateway.py",
]
ROUTE_FAMILY = "/api/admin/image-library*"
CAPABILITY_OWNER = "aicrm_next.media_library"
NEXT_BUNDLE = "phase_5w_media_upload_staging_live_canary_evidence_bundle"
COMPLETED_STEP = "phase_5v_media_upload_live_adapter_behind_flag_completed"
REQUIRED_FLAGS = {
    "AICRM_MEDIA_UPLOAD_LIVE_ADAPTER_ENABLED",
    "AICRM_MEDIA_UPLOAD_LIVE_UPLOAD_APPROVED",
    "AICRM_MEDIA_UPLOAD_CONFIG_REVIEWED",
    "AICRM_MEDIA_UPLOAD_PROVIDER_NAME",
    "AICRM_MEDIA_UPLOAD_PROVIDER_SECRET",
}
REQUIRED_METHODS = {"upload_media_live", "lookup_media_live"}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/integration_gateway/media_live_adapter.py",
    "aicrm_next/integration_gateway/media_live_gateway.py",
    "docs/development/phase_5v_media_upload_live_adapter_behind_flag.md",
    "docs/development/phase_5v_media_upload_live_adapter_behind_flag.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5v_media_upload_live_staging_evidence.py",
    "tools/run_phase5v_media_upload_live_production_dry_run_gate.py",
    "tools/check_phase5v_media_upload_live_adapter_behind_flag.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5v_media_upload_live_adapter_behind_flag.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"aicrm_next/main.py"}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "boto3", "wecom_ability_service"}
FORBIDDEN_CALLS = {"send", "payment", "capture", "refund", "oauth", "wecom", "openclaw", "mcp", "run_due", "remove", "unlink"}
FORBIDDEN_DOC_CLAIMS = {
    "production live upload enabled",
    "public media url publication enabled",
    "destructive delete enabled",
    "raw file exposure enabled",
    "route owner switched",
    "fallback removed",
    "production_compat changed",
    "canary approved",
    "delete_ready true",
    "delete_ready: true",
}


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {line.strip() for line in proc.stdout.splitlines() if proc.returncode == 0 and line.strip()}


def _changed_files() -> set[str]:
    return set().union(
        _run_git(["diff", "--name-only", "origin/main...HEAD"]),
        _run_git(["diff", "--name-only"]),
        _run_git(["diff", "--name-only", "--cached"]),
        _run_git(["ls-files", "--others", "--exclude-standard"]),
    )


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
    found_imports = sorted(FORBIDDEN_IMPORTS & imports)
    if found_imports:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden modules: {found_imports}")
    found_calls = sorted(FORBIDDEN_CALLS & calls)
    if found_calls:
        blockers.append(f"{path.relative_to(ROOT)} calls forbidden names: {found_calls}")
    for token in ("api.", "amazonaws.com", "aliyuncs.com", "qcloud", "public_url_published\": true", "destructive_delete_executed\": true", "raw_file_exposed\": true"):
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} contains forbidden live/provider token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in [DOC, PLAN_YAML, STATE, STAGING_RUNNER, PROD_RUNNER, TEST, *RUNTIME_FILES]:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("status") != "phase_5v_media_upload_live_adapter_behind_explicit_flag":
        blockers.append("status mismatch")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")

    auth = _dict(data.get("authorizations"))
    if auth.get("live_media_adapter_code_authorized") is not True:
        blockers.append("live_media_adapter_code_authorized must be true")
    for key, value in auth.items():
        if key != "live_media_adapter_code_authorized" and value is not False:
            blockers.append(f"authorizations.{key} must be false")

    live = _dict(data.get("live_adapter"))
    if live.get("default_enabled") is not False:
        blockers.append("live_adapter.default_enabled must be false")
    if not REQUIRED_FLAGS <= {str(item) for item in _list(live.get("required_env"))}:
        blockers.append("live_adapter.required_env incomplete")
    if not REQUIRED_METHODS <= {str(item) for item in _list(live.get("methods"))}:
        blockers.append("live_adapter.methods incomplete")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")

    staging = _dict(data.get("staging_evidence"))
    prod = _dict(data.get("production_dry_run_gate"))
    if staging.get("default_blocked") is not True or staging.get("execute_live_staging_requires_approval") is not True:
        blockers.append("staging_evidence must default blocked and require approval")
    if prod.get("live_provider_upload_executed") is not False or prod.get("public_media_url_published") is not False:
        blockers.append("production dry-run gate must never execute upload or publish")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")

    if state.get("last_merged_pr") != "#734":
        blockers.append("phase_execution_state.last_merged_pr must be #734")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")

    combined_runtime = "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME_FILES)
    for flag in REQUIRED_FLAGS:
        if flag not in combined_runtime:
            blockers.append(f"runtime must reference {flag}")
    if "idempotency_key" not in combined_runtime or "side_effect_safety" not in combined_runtime:
        blockers.append("runtime must require idempotency key and expose side_effect_safety")
    for path in [*RUNTIME_FILES, STAGING_RUNNER, PROD_RUNNER]:
        blockers.extend(_static_blockers(path))
    for runner in (STAGING_RUNNER, PROD_RUNNER):
        text = runner.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{runner.name} missing {arg}")
    for arg in ("--dry-run-live-gate", "--execute-live-staging", "--confirm-live-media-upload", "--confirm-staging-only", "--confirm-no-public-publish"):
        if arg not in STAGING_RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"staging runner missing {arg}")
    for arg in ("--dry-run", "--confirm-no-live-upload", "--confirm-no-public-publish", "--confirm-no-delete"):
        if arg not in PROD_RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"production runner missing {arg}")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5V allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5V Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
