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

DOC = ROOT / "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.yaml"
RUNNER = ROOT / "tools/run_phase5an_questionnaire_external_submit_production_canary_readiness.py"
CLEANUP = ROOT / "tools/run_phase5an_questionnaire_external_submit_production_canary_cleanup.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5an_questionnaire_external_submit_production_canary_readiness.py"
NEXT_BUNDLE = "phase_5ao_questionnaire_external_submit_family_acceptance_bundle"
COMPLETED_STEP = "phase_5an_questionnaire_external_submit_production_canary_readiness_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.md",
    "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5an_questionnaire_external_submit_production_canary_readiness.py",
    "tools/run_phase5an_questionnaire_external_submit_production_canary_cleanup.py",
    "tools/check_phase5an_questionnaire_external_submit_production_canary_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5an_questionnaire_external_submit_production_canary_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}


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
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return imports, calls


def _static(path: Path) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8").lower()
    imports, calls = _imports_calls(path)
    if imports & {"requests", "httpx", "aiohttp", "urllib"}:
        blockers.append(f"{path.name} imports forbidden network modules")
    if calls & {"send", "run_due", "execute_due", "dispatch"}:
        blockers.append(f"{path.name} calls forbidden names")
    for token in ("write_identity_mapping_live(", "write_tag_back_live(", "submit_public_live(", "change_production_compat", "switch_route_owner"):
        if token in text:
            blockers.append(f"{path.name} contains forbidden token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, RUNNER, CLEANUP, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    auth = _dict(data.get("authorizations"))
    if auth.get("production_canary_tooling_authorized") is not True:
        blockers.append("production_canary_tooling_authorized must be true")
    for key, value in auth.items():
        if key != "production_canary_tooling_authorized" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    canary = _dict(data.get("production_canary"))
    if canary.get("default_blocked") is not True or canary.get("single_submit_target_only") is not True:
        blockers.append("production canary must be default blocked and single target")
    for key in ("batch_submit_allowed", "batch_tag_write_allowed", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed"):
        if canary.get(key) is not False:
            blockers.append(f"production_canary.{key} must be false")
    required_args = {"--staging-evidence-json", "--idempotency-key", "--slug", "--submission-id", "--confirm-no-production-owner-switch", "--confirm-no-production-write", "--confirm-no-production-tag-write", "--confirm-no-outbound-send", "--confirm-single-approved-target"}
    if not required_args <= set(_list(canary.get("required_args"))):
        blockers.append("production_canary.required_args incomplete")
    for key, value in _dict(data.get("target_safety")).items():
        if key.endswith("_allowed") and value is not False:
            blockers.append(f"target_safety.{key} must be false")
    cleanup = _dict(data.get("cleanup"))
    for key in ("default_blocked", "cleanup_requires_explicit_approval"):
        if cleanup.get(key) is not True:
            blockers.append(f"cleanup.{key} must be true")
    for key in ("production_submit_delete_allowed", "production_identity_delete_allowed", "production_tag_cleanup_allowed", "automatic_cleanup_allowed", "batch_cleanup_allowed"):
        if cleanup.get(key) is not False:
            blockers.append(f"cleanup.{key} must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#752":
        blockers.append("phase_execution_state.last_merged_pr must be #752")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (RUNNER, CLEANUP):
        blockers.extend(_static(path))
        text = path.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{path.name} missing {arg}")
    for arg in required_args:
        if arg not in RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"production canary runner missing {arg}")
    for arg in ("--canary-evidence-json", "--confirm-cleanup-reviewed", "--confirm-no-production-submit-delete", "--confirm-no-production-identity-delete", "--confirm-no-production-tag-cleanup", "--confirm-no-batch-cleanup"):
        if arg not in CLEANUP.read_text(encoding="utf-8"):
            blockers.append(f"cleanup runner missing {arg}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("production public submit write enabled", "production identity write enabled", "production tag write enabled", "live oauth callback cutover enabled", "outbound send enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AN allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path == "aicrm_next/main.py" or path.startswith(("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AN Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
