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

DOC = ROOT / "docs/development/phase_5o_oauth_identity_fake_stub_adapter.md"
PLAN_YAML = ROOT / "docs/development/phase_5o_oauth_identity_fake_stub_adapter.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5o_oauth_identity_fake_stub_staging_smoke.py"
PRODUCTION_RUNNER = ROOT / "tools/run_phase5o_oauth_identity_fake_stub_production_dry_run.py"
TEST = ROOT / "tests/test_phase5o_oauth_identity_fake_stub_adapter.py"
RUNTIME_FILES = [
    ROOT / "aicrm_next/integration_gateway/oauth_identity_adapter.py",
    ROOT / "aicrm_next/integration_gateway/oauth_identity_application.py",
    ROOT / "aicrm_next/integration_gateway/oauth_identity_contract.py",
]
ROUTE_FAMILY = "/api/h5/wechat/oauth*"
NEXT_BUNDLE = "phase_5p_oauth_identity_live_adapter_behind_flag_bundle"
COMPLETED_STEP = "phase_5o_oauth_identity_fake_stub_adapter_completed"
REQUIRED_METHODS = {
    "build_oauth_authorize_url_contract",
    "parse_oauth_callback_contract",
    "normalize_oauth_identity_event",
    "dry_run_record_oauth_identity",
    "dry_run_session_identity_evidence",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/integration_gateway/oauth_identity_adapter.py",
    "aicrm_next/integration_gateway/oauth_identity_application.py",
    "aicrm_next/integration_gateway/oauth_identity_contract.py",
    "docs/development/phase_5o_oauth_identity_fake_stub_adapter.md",
    "docs/development/phase_5o_oauth_identity_fake_stub_adapter.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5o_oauth_identity_fake_stub_staging_smoke.py",
    "tools/run_phase5o_oauth_identity_fake_stub_production_dry_run.py",
    "tools/check_phase5o_oauth_identity_fake_stub_adapter.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5o_oauth_identity_fake_stub_adapter.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {"aicrm_next/main.py", "aicrm_next/questionnaire/oauth.py"}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_IMPORT_ROOTS = {"requests", "httpx", "aiohttp", "wecom_ability_service", "urllib"}
FORBIDDEN_ENV_TOKENS = {"WECHAT_APP_SECRET", "WECHAT_APPID", "WECHAT_ACCESS_TOKEN", "OAUTH_CLIENT_SECRET"}


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


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
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


def _static_file_blockers(path: Path, *, allow_os: bool = False) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8")
    imports, calls = _imports_and_calls(path)
    forbidden_imports = sorted(FORBIDDEN_IMPORT_ROOTS & imports)
    if forbidden_imports:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden live/network modules: {forbidden_imports}")
    if not allow_os and "os" in imports:
        blockers.append(f"{path.relative_to(ROOT)} must not read environment")
    forbidden_calls = sorted({"post", "put", "patch", "delete", "send", "set_cookie"} & calls)
    if forbidden_calls:
        blockers.append(f"{path.relative_to(ROOT)} contains forbidden call names: {forbidden_calls}")
    for token in FORBIDDEN_ENV_TOKENS:
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} references forbidden secret/token env: {token}")
    for token in ("api.weixin.qq.com", "sns/oauth2/access_token", "set_cookie"):
        if token in text.lower():
            blockers.append(f"{path.relative_to(ROOT)} references forbidden live/cutover token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in [DOC, PLAN_YAML, STATE, STAGING_RUNNER, PRODUCTION_RUNNER, TEST, *RUNTIME_FILES]:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("status") != "phase_5o_oauth_identity_fake_stub_adapter_no_live_oauth_callback":
        blockers.append("status must be phase_5o_oauth_identity_fake_stub_adapter_no_live_oauth_callback")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if any(value is not False for value in _dict(data.get("authorizations")).values()):
        blockers.append("authorizations must all be false")
    if set(_list(data.get("implemented_fake_stub_methods"))) != REQUIRED_METHODS:
        blockers.append("implemented_fake_stub_methods incomplete")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if key.endswith("_allowed") and value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    idem = _dict(data.get("idempotency"))
    for key in ("dry_run_record_oauth_identity_requires_key", "dry_run_session_identity_evidence_requires_key", "replay_same_hash", "replay_same_oauth_event_key", "conflict_different_hash"):
        if idem.get(key) is not True:
            blockers.append(f"idempotency.{key} must be true")
    if state.get("last_merged_pr") != "#727":
        blockers.append("phase_execution_state.last_merged_pr must be #727")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in RUNTIME_FILES:
        blockers.extend(_static_file_blockers(path))
    blockers.extend(_static_file_blockers(STAGING_RUNNER, allow_os=True))
    blockers.extend(_static_file_blockers(PRODUCTION_RUNNER, allow_os=True))
    for arg in ("--output-json", "--output-md"):
        if arg not in STAGING_RUNNER.read_text(encoding="utf-8") or arg not in PRODUCTION_RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"readiness runners must support {arg}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5O allowlist: {unexpected}")
    forbidden_exact = sorted(FORBIDDEN_EXACT_CHANGED & changed)
    if forbidden_exact:
        blockers.append(f"changed forbidden exact files: {forbidden_exact}")
    forbidden_prefix = sorted(path for path in changed if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden_prefix:
        blockers.append(f"changed forbidden runtime/deploy files: {forbidden_prefix}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("live oauth callback cutover enabled", "production session write enabled", "production success", "canary approved", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5O Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
