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


DOC = ROOT / "docs/development/phase_5x_media_upload_production_canary_readiness_execution.md"
PLAN_YAML = ROOT / "docs/development/phase_5x_media_upload_production_canary_readiness_execution.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
CANARY = ROOT / "tools/run_phase5x_media_upload_production_canary_readiness_execution.py"
CLEANUP = ROOT / "tools/run_phase5x_media_upload_production_canary_cleanup.py"
TEST = ROOT / "tests/test_phase5x_media_upload_production_canary_readiness_execution.py"
NEXT_BUNDLE = "phase_5y_media_upload_family_acceptance_bundle"
COMPLETED_STEP = "phase_5x_media_upload_production_canary_readiness_execution_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5x_media_upload_production_canary_readiness_execution.md",
    "docs/development/phase_5x_media_upload_production_canary_readiness_execution.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5x_media_upload_production_canary_readiness_execution.py",
    "tools/run_phase5x_media_upload_production_canary_cleanup.py",
    "tools/check_phase5x_media_upload_production_canary_readiness_execution.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5x_media_upload_production_canary_readiness_execution.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"aicrm_next/main.py"}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "boto3", "wecom_ability_service"}
FORBIDDEN_CALLS = {"send", "payment", "capture", "refund", "oauth", "wecom", "openclaw", "mcp", "run_due", "remove", "unlink"}


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
    for token in ("public_media_url_published\": true", "destructive_delete_executed\": true", "raw_file_exposed\": true", "batch_upload_executed\": true"):
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} contains forbidden true token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, CANARY, CLEANUP, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    auth = _dict(data.get("authorizations"))
    if auth.get("production_live_canary_tooling_authorized") is not True:
        blockers.append("production_live_canary_tooling_authorized must be true")
    for key, value in auth.items():
        if key != "production_live_canary_tooling_authorized" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    canary = _dict(data.get("production_canary"))
    for key, expected in {
        "default_blocked": True,
        "single_file_only": True,
        "batch_upload_allowed": False,
        "public_media_url_publication_allowed": False,
        "destructive_delete_allowed": False,
        "requires_staging_evidence_json": True,
    }.items():
        if canary.get(key) is not expected:
            blockers.append(f"production_canary.{key} must be {expected}")
    cleanup = _dict(data.get("cleanup"))
    for key, expected in {
        "default_blocked": True,
        "same_file_only": True,
        "destructive_delete_allowed": False,
        "batch_cleanup_allowed": False,
        "automatic_cleanup_allowed": False,
    }.items():
        if cleanup.get(key) is not expected:
            blockers.append(f"cleanup.{key} must be {expected}")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#736":
        blockers.append("phase_execution_state.last_merged_pr must be #736")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (CANARY, CLEANUP):
        text = path.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{path.name} missing {arg}")
        blockers.extend(_static_blockers(path))
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("route owner switched", "fallback removed", "production_compat changed", "public media url publication enabled", "destructive delete enabled", "batch upload enabled", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5X allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5X Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
