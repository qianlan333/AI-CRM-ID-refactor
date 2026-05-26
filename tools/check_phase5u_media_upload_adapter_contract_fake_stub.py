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


DOC = ROOT / "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.md"
PLAN_YAML = ROOT / "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5u_media_upload_fake_stub_staging_smoke.py"
PROD_RUNNER = ROOT / "tools/run_phase5u_media_upload_fake_stub_production_dry_run.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5u_media_upload_adapter_contract_fake_stub.py"
NEXT_BUNDLE = "phase_5v_media_upload_live_adapter_behind_flag_bundle"
COMPLETED_STEP = "phase_5u_media_upload_adapter_contract_fake_stub_completed"
REQUIRED_METHODS = {
    "validate_media_metadata",
    "dry_run_upload_media",
    "dry_run_lookup_media",
    "dry_run_provider_reference",
    "dry_run_publish_reference_policy",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.md",
    "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5u_media_upload_fake_stub_staging_smoke.py",
    "tools/run_phase5u_media_upload_fake_stub_production_dry_run.py",
    "tools/check_phase5u_media_upload_adapter_contract_fake_stub.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5u_media_upload_adapter_contract_fake_stub.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "deploy/", "nginx/", "systemd/", "migrations/")
FORBIDDEN_EXACT = {"aicrm_next/main.py"}
FORBIDDEN_DOC_CLAIMS = {
    "live provider upload enabled",
    "production media publish enabled",
    "public media url publication enabled",
    "route owner switched",
    "fallback removed",
    "production_compat changed",
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


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


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


def _runner_blockers() -> list[str]:
    blockers: list[str] = []
    for runner in (STAGING_RUNNER, PROD_RUNNER):
        text = runner.read_text(encoding="utf-8")
        imports, calls = _imports_calls(runner)
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{runner.name} missing arg {arg}")
        if runner == PROD_RUNNER:
            for arg in ("--dry-run", "--confirm-no-live-upload", "--confirm-no-public-publish"):
                if arg not in text:
                    blockers.append(f"{runner.name} missing arg {arg}")
        if runner == STAGING_RUNNER and "AICRM_PHASE5U_MEDIA_UPLOAD_STAGING_FAKE_STUB_APPROVED" not in text:
            blockers.append("staging runner missing approval env")
        forbidden_imports = {"requests", "httpx", "aiohttp", "urllib"}
        found_imports = sorted(forbidden_imports & imports)
        if found_imports:
            blockers.append(f"{runner.name} imports forbidden modules: {found_imports}")
        forbidden_calls = {"post", "put", "patch", "delete", "send", "open"}
        found_calls = sorted(forbidden_calls & calls)
        if found_calls:
            blockers.append(f"{runner.name} calls forbidden names: {found_calls}")
        for token in ("provider_secret_used\": true", "token_used\": true", "network_call_executed\": true", "public_media_url_published\": true", "raw_file_exposed\": true", "destructive_delete_executed\": true"):
            if token in text:
                blockers.append(f"{runner.name} contains forbidden true side effect token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, STAGING_RUNNER, PROD_RUNNER, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()
    if data.get("status") != "phase_5u_media_upload_adapter_contract_fake_stub_no_live_upload":
        blockers.append("status mismatch")
    if data.get("route_family") != "/api/admin/image-library*":
        blockers.append("route_family must be /api/admin/image-library*")
    if data.get("capability_owner") != "aicrm_next.media_library":
        blockers.append("capability_owner must be aicrm_next.media_library")
    auth = _dict(data.get("authorizations"))
    for key, value in auth.items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    methods = {str(item.get("name")) for item in _list(_dict(data.get("adapter_contract")).get("methods")) if isinstance(item, dict)}
    if not REQUIRED_METHODS <= methods:
        blockers.append(f"adapter_contract.methods missing: {sorted(REQUIRED_METHODS - methods)}")
    fake = _dict(data.get("fake_stub_runtime"))
    for key in ("provider_secret_required", "token_usage_allowed", "network_call_allowed", "raw_file_dump_allowed", "public_url_publication_allowed", "destructive_delete_allowed", "production_success_claim_allowed"):
        if fake.get(key) is not False:
            blockers.append(f"fake_stub_runtime.{key} must be false")
    if fake.get("deterministic_fake_metadata_required") is not True:
        blockers.append("fake_stub_runtime.deterministic_fake_metadata_required must be true")
    metadata = _dict(data.get("metadata_policy"))
    if metadata.get("raw_file_output_forbidden") is not True or metadata.get("public_url_redaction_required") is not True:
        blockers.append("metadata redaction policy incomplete")
    if not _list(metadata.get("allowed_mime_types")) or not _list(metadata.get("allowed_extensions")):
        blockers.append("metadata allowed MIME/extensions incomplete")
    for key, value in _dict(data.get("idempotency_policy")).items():
        if value is not True:
            blockers.append(f"idempotency_policy.{key} must be true")
    runners = _dict(data.get("readiness_runners"))
    if _dict(runners.get("staging")).get("default_blocked") is not True:
        blockers.append("staging runner must be default_blocked")
    if _dict(runners.get("staging")).get("live_upload_allowed") is not False:
        blockers.append("staging live_upload_allowed must be false")
    if _dict(runners.get("production_dry_run")).get("live_upload_allowed") is not False:
        blockers.append("production dry-run live_upload_allowed must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")

    if state.get("last_merged_pr") != "#733":
        blockers.append("phase_execution_state.last_merged_pr must be #733")
    if state.get("last_attempted_action") != "phase_5u_media_upload_adapter_contract_fake_stub_bundle":
        blockers.append("last_attempted_action must be Phase 5U")
    if state.get("active_candidate") != "/api/admin/image-library*":
        blockers.append("active_candidate must remain /api/admin/image-library*")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")

    blockers.extend(_runner_blockers())
    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc must not claim forbidden state: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5U allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"forbidden changed files: {forbidden}")

    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5U Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
