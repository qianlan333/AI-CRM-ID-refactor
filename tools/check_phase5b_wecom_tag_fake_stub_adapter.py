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


DOC = ROOT / "docs/development/phase_5b_wecom_tag_fake_stub_adapter.md"
PLAN_YAML = ROOT / "docs/development/phase_5b_wecom_tag_fake_stub_adapter.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py"
PROD_RUNNER = ROOT / "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py"
TEST = ROOT / "tests/test_phase5b_wecom_tag_fake_stub_adapter.py"
ADAPTER_SOURCES = [
    ROOT / "aicrm_next/customer_tags/wecom_tag_adapter.py",
    ROOT / "aicrm_next/customer_tags/wecom_tag_contract.py",
    ROOT / "aicrm_next/customer_tags/application.py",
    ROOT / "aicrm_next/customer_tags/api.py",
    ROOT / "aicrm_next/customer_tags/dto.py",
]
ROUTE_FAMILY = "/api/admin/wecom/tags*"
CAPABILITY_OWNER = "aicrm_next.customer_tags"
BUNDLE_TYPE = "phase_5_external_adapter_fake_stub_runtime_and_readiness_bundle"
NEXT_BUNDLE = "phase_5c_wecom_tag_live_adapter_behind_flag_bundle"
COMPLETED_STEP = "phase_5b_wecom_tag_fake_stub_adapter_completed"
REQUIRED_METHODS = {
    "list_wecom_tags",
    "validate_tag_ids",
    "dry_run_mark_tags",
    "dry_run_unmark_tags",
}
REQUIRED_IDEMPOTENCY = {
    "dry_run_mark_tags_requires_key",
    "dry_run_unmark_tags_requires_key",
    "replay_same_hash",
    "conflict_different_hash",
}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "wecom_ability_service", "wecom_client"}
FORBIDDEN_ENV_TOKENS = {
    "WECOM_SECRET",
    "WECHAT_WORK_SECRET",
    "WECOM_CORP_SECRET",
    "CORPSECRET",
    "WECOM_CORP_ID",
    "WECHAT_WORK_CORP_ID",
    "CORPID",
}
FORBIDDEN_DOC_CLAIMS = {
    "live wecom call enabled",
    "production tag write enabled",
    "production success",
    "canary approved",
    "delete_ready true",
    "delete_ready: true",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/customer_tags/api.py",
    "aicrm_next/customer_tags/application.py",
    "aicrm_next/customer_tags/dto.py",
    "aicrm_next/customer_tags/wecom_tag_adapter.py",
    "aicrm_next/customer_tags/wecom_tag_contract.py",
    "docs/development/phase_5b_wecom_tag_fake_stub_adapter.md",
    "docs/development/phase_5b_wecom_tag_fake_stub_adapter.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py",
    "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py",
    "tools/check_phase5b_wecom_tag_fake_stub_adapter.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5b_wecom_tag_fake_stub_adapter.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {"aicrm_next/main.py"}
FORBIDDEN_CHANGED_PREFIXES = (
    "aicrm_next/production_compat/",
    "wecom_ability_service/",
    "deploy/",
    "nginx/",
    "systemd/",
    "migrations/",
    "wecom_ability_service/db/migrations/",
)


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, stderr = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    else:
        warnings.append(f"git ls-files --others unavailable: {(stderr or stdout).strip()}")
    return changed, warnings


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


def _source_static_blockers(path: Path) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports: set[str] = set()
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                call_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                call_names.add(func.attr)

    forbidden_imports = sorted(FORBIDDEN_IMPORTS & imports)
    if forbidden_imports:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden live/network modules: {forbidden_imports}")
    forbidden_calls = sorted({"mark_tag", "unmark_tag", "send"} & call_names)
    if forbidden_calls:
        blockers.append(f"{path.relative_to(ROOT)} contains forbidden live call names: {forbidden_calls}")
    for token in ("externalcontact/get_corp_tag_list", "/cgi-bin/externalcontact/get_corp_tag_list"):
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} references live get corp tag list endpoint")
    for token in FORBIDDEN_ENV_TOKENS:
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} reads or references forbidden WeCom secret/CorpID token: {token}")
    return blockers


def _runner_blockers(path: Path) -> list[str]:
    blockers = _source_static_blockers(path)
    text = path.read_text(encoding="utf-8")
    for arg in ("--output-json", "--output-md"):
        if arg not in text:
            blockers.append(f"{path.relative_to(ROOT)} must support {arg}")
    for token in ("live_call_executed", "token_used", "network_call_executed"):
        if token not in text:
            blockers.append(f"{path.relative_to(ROOT)} must emit {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    required = [DOC, PLAN_YAML, STATE, STAGING_RUNNER, PROD_RUNNER, TEST, *ADAPTER_SOURCES]
    for path in required:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_5b_wecom_tag_fake_stub_adapter_no_live_call":
        blockers.append("status must be phase_5b_wecom_tag_fake_stub_adapter_no_live_call")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")
    if data.get("integration_boundary") != "aicrm_next.integration_gateway":
        blockers.append("integration_boundary must be aicrm_next.integration_gateway")

    authorizations = _dict(data.get("authorizations"))
    if not authorizations:
        blockers.append("authorizations must be present")
    for key, value in sorted(authorizations.items()):
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    methods = _strings(data.get("implemented_fake_stub_methods"))
    if REQUIRED_METHODS != methods:
        blockers.append(f"implemented_fake_stub_methods must be exactly {sorted(REQUIRED_METHODS)}")

    side_effect_safety = _dict(data.get("side_effect_safety"))
    if not side_effect_safety:
        blockers.append("side_effect_safety must be present")
    for key, value in sorted(side_effect_safety.items()):
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")

    idempotency = _dict(data.get("idempotency"))
    for field in sorted(REQUIRED_IDEMPOTENCY):
        if idempotency.get(field) is not True:
            blockers.append(f"idempotency.{field} must be true")

    readiness = _dict(data.get("readiness_runners"))
    staging = _dict(readiness.get("staging"))
    production = _dict(readiness.get("production_dry_run"))
    if staging.get("path") != "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py" or staging.get("live_call_allowed") is not False:
        blockers.append("staging readiness runner path/live_call_allowed invalid")
    if "AICRM_PHASE5B_WECOM_TAG_STAGING_SMOKE_APPROVED" not in _strings(staging.get("required_env")):
        blockers.append("staging required_env missing approval flag")
    if production.get("path") != "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py" or production.get("live_call_allowed") is not False:
        blockers.append("production dry-run runner path/live_call_allowed invalid")
    for env_name in ("AICRM_PHASE5B_WECOM_TAG_PRODUCTION_DRY_RUN_APPROVED", "AICRM_PHASE5B_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED"):
        if env_name not in _strings(production.get("required_env")):
            blockers.append(f"production dry-run required_env missing {env_name}")
    if {"--dry-run", "--confirm-no-live-call"} - _strings(production.get("required_args")):
        blockers.append("production dry-run required_args incomplete")

    continuity = _dict(data.get("business_continuity"))
    for field in ("production_behavior_unchanged", "legacy_fallback_retained", "no_external_side_effect_enabled", "fake_stub_only"):
        if continuity.get(field) is not True:
            blockers.append(f"business_continuity.{field} must be true")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE or next_bundle.get("route_family") != ROUTE_FAMILY:
        blockers.append("next_bundle must recommend Phase 5C for /api/admin/wecom/tags*")

    if state.get("last_merged_pr") != "#712":
        blockers.append("phase state last_merged_pr must record #712")
    if state.get("last_attempted_action") != "phase_5b_wecom_tag_fake_stub_adapter_bundle":
        blockers.append("phase state last_attempted_action must be Phase 5B")
    if state.get("recommended_next_pr") != NEXT_BUNDLE or set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next action must advance to Phase 5C")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append(f"completed_steps must include {COMPLETED_STEP}")

    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    for source in ADAPTER_SOURCES:
        blockers.extend(_source_static_blockers(source))
    for runner in (STAGING_RUNNER, PROD_RUNNER):
        blockers.extend(_runner_blockers(runner))

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5B allowed set: {unexpected}")
    forbidden_changed = sorted(
        path
        for path in changed
        if path in FORBIDDEN_EXACT_CHANGED or any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES)
    )
    if forbidden_changed:
        blockers.append(f"forbidden runtime/protected files changed: {forbidden_changed}")

    details["changed_files"] = sorted(changed)
    details["implemented_fake_stub_methods"] = sorted(methods)
    details["next_bundle"] = next_bundle
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "autopilot_deliverable": not blockers, "blockers": blockers, "warnings": warnings, "details": details}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 5B WeCom Tag Fake/Stub Adapter Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Changed Files",
            *(f"- {item}" for item in report["details"].get("changed_files", [])),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
