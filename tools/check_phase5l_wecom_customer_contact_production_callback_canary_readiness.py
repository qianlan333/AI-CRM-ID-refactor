#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.yaml"
RUNNER = ROOT / "tools/run_phase5l_wecom_customer_contact_production_callback_canary_readiness.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5l_wecom_customer_contact_production_callback_canary_readiness.py"
NEXT_BUNDLE = "phase_5m_wecom_customer_contact_callback_family_acceptance_bundle"
COMPLETED_STEP = "phase_5l_wecom_customer_contact_production_callback_canary_readiness_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.md",
    "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
    "tools/check_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "deploy/", "nginx/", "systemd/", "migrations/")


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> set[str]:
    changed: set[str] = set()
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"], ["ls-files", "--others", "--exclude-standard"]):
        ok, stdout, _ = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, RUNNER, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    auth = _dict(data.get("authorizations"))
    for key, value in auth.items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    runner = _dict(data.get("readiness_runner"))
    if runner.get("default_blocked") is not True:
        blockers.append("readiness_runner.default_blocked must be true")
    for key in ("production_live_callback_processed", "production_contact_write_executed", "production_identity_mapping_write_executed"):
        if runner.get(key) is not False:
            blockers.append(f"readiness_runner.{key} must be false")
    for section in ("production_target_policy", "rollback_policy", "business_continuity"):
        if not isinstance(data.get(section), dict):
            blockers.append(f"{section} must be present")
    text = RUNNER.read_text(encoding="utf-8")
    for arg in ("--staging-evidence-json", "--confirm-no-production-live-callback", "--confirm-no-production-write", "--output-json", "--output-md"):
        if arg not in text:
            blockers.append(f"runner missing {arg}")
    for token in ("build_live_wecom_contact_callback_adapter", "process_external_contact_callback_live", "wecom_ability_service", "requests", "httpx", "aiohttp"):
        if token in text:
            blockers.append(f"runner must not call/import live callback token: {token}")
    if state.get("last_merged_pr") != "#724":
        blockers.append("phase_execution_state.last_merged_pr must be #724")
    if state.get("last_attempted_action") != "phase_5l_wecom_customer_contact_production_callback_canary_readiness_bundle":
        blockers.append("last_attempted_action must be Phase 5L")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5L allowlist: {unexpected}")
    for path in sorted(changed):
        if path == "aicrm_next/main.py" or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            blockers.append(f"forbidden changed file: {path}")
    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5L Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
