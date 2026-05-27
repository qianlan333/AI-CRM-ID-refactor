#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml as _load_yaml


PLAN_YAML = ROOT / "docs/development/post_820_batch_exact_route_cleanup.yaml"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
NATIVE_API = ROOT / "aicrm_next/automation_engine/api.py"

SELECTED_EXACT_ROUTES = (
    "/api/admin/automation-conversion/action-templates",
    "/api/admin/automation-conversion/workflows",
    "/api/admin/automation-conversion/tasks",
    "/api/admin/automation-conversion/agents",
    "/api/admin/automation-conversion/profile-segment-templates",
)
RETAINED_WILDCARD_ROUTES = tuple(f"{route}/{{path:path}}" for route in SELECTED_EXACT_ROUTES)

NEXT_NATIVE_EXACT_PATTERNS = {
    route: (
        rf'@router\.get\("{re.escape(route)}"\)',
        rf'@router\.post\("{re.escape(route)}"\)',
    )
    for route in SELECTED_EXACT_ROUTES
}

UNRELATED_PRODUCTION_COMPAT_ROUTES = (
    "/wecom/external-contact/callback",
    "/api/wecom/events",
    "/api/admin/automation-conversion/reply-monitor/run-due",
    "/api/admin/automation-conversion/jobs/run-due",
    "/api/admin/cloud-orchestrator/campaigns/run-due",
    "/api/h5/wechat/oauth/start",
    "/api/h5/wechat/oauth/callback",
    "/api/h5/questionnaires/{slug}/submit",
    "/api/admin/wecom/tags",
    "/api/admin/wechat-pay/{path:path}",
    "/api/h5/wechat-pay/{path:path}",
    "/api/products/{path:path}",
    "/p/{path:path}",
    "/api/admin/image-library/upload",
    "/api/admin/automation-conversion/agent-outputs/{path:path}",
    "/api/admin/automation-conversion/agent-runs/{path:path}",
    "/api/admin/automation-conversion/executions",
    "/api/admin/automation-conversion/executions/{path:path}",
)

EXPECTED_REMOVED_COMPAT_LINES = {
    f'@router.api_route("{route}", methods=_ALL_METHODS)' for route in SELECTED_EXACT_ROUTES
}

ALLOWED_CHANGED_FILES = {
    "aicrm_next/production_compat/api.py",
    "docs/development/post_820_batch_exact_route_cleanup.yaml",
    "tools/check_post_820_batch_exact_route_cleanup.py",
    "tests/test_post_820_batch_exact_route_cleanup.py",
}
FORBIDDEN_EXACT_CHANGED_FILES = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_CHANGED_PREFIXES = ("wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalise_route_list(value: Any) -> list[Any]:
    items: list[Any] = []
    for item in _list(value):
        if isinstance(item, dict) and len(item) == 1:
            key, val = next(iter(item.items()))
            items.append(f"{str(key).strip(chr(34))}:{str(val).strip(chr(34))}")
        else:
            items.append(item)
    return items


def load_yaml(path: Path) -> dict[str, Any]:
    data = _load_yaml(path)
    if path == PLAN_YAML:
        data["retained_wildcard_routes"] = _normalise_route_list(data.get("retained_wildcard_routes"))
    return data


def _git_text(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def _changed_files() -> set[str]:
    files: set[str] = set()
    for args in (
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        files.update(line.strip() for line in _git_text(args).splitlines() if line.strip())
    return files


def _deleted_or_renamed_files() -> list[str]:
    entries: list[str] = []
    for args in (
        ["diff", "--name-status", "origin/main...HEAD"],
        ["diff", "--name-status"],
        ["diff", "--name-status", "--cached"],
    ):
        entries.extend(
            line.strip()
            for line in _git_text(args).splitlines()
            if line.startswith(("D", "R"))
        )
    return sorted(set(entries))


def _contains_route(text: str, route: str) -> bool:
    return f'"{route}"' in text or f"'{route}'" in text


def _production_compat_diff_is_exact_batch() -> bool:
    diff = "\n".join(
        part
        for part in (
            _git_text(["diff", "origin/main...HEAD", "--", "aicrm_next/production_compat/api.py"]),
            _git_text(["diff", "--", "aicrm_next/production_compat/api.py"]),
            _git_text(["diff", "--cached", "--", "aicrm_next/production_compat/api.py"]),
        )
        if part
    )
    changed_lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            changed_lines.append(line)
    return set(changed_lines) == {f"-{line}" for line in EXPECTED_REMOVED_COMPAT_LINES}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}

    for path in (PLAN_YAML, PRODUCTION_COMPAT, NATIVE_API):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    compat_text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    native_text = NATIVE_API.read_text(encoding="utf-8")

    if data.get("status") != "post_820_batch_exact_route_cleanup":
        blockers.append("cleanup status is incorrect")
    if data.get("bundle_type") != "post_820_batch_exact_route_cleanup_bundle":
        blockers.append("bundle_type is incorrect")
    if data.get("cleanup_family") != "automation_exact_route_batch_cleanup":
        blockers.append("cleanup_family is incorrect")
    if data.get("source_prs", {}).get("prerequisite_agent_outputs_cleanup") != 820:
        blockers.append("source_prs.prerequisite_agent_outputs_cleanup must be 820")

    selected = tuple(_list(data.get("selected_exact_routes")))
    retained = tuple(_list(data.get("retained_wildcard_routes")))
    if selected != SELECTED_EXACT_ROUTES:
        blockers.append("selected_exact_routes must match the requested batch")
    if retained != RETAINED_WILDCARD_ROUTES:
        blockers.append("retained_wildcard_routes must match the requested wildcard batch")

    auth = _dict(data.get("authorizations"))
    if auth.get("selected_exact_route_batch_cleanup_authorized") is not True:
        blockers.append("selected batch cleanup must be authorized")
    for key in (
        "broad_fallback_removal_authorized",
        "wildcard_production_compat_cleanup_authorized",
        "runtime_deletion_authorized",
        "payment_oauth_wecom_callback_public_submit_timer_outbound_affected",
        "delete_ready",
    ):
        if auth.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    for route in SELECTED_EXACT_ROUTES:
        if f'@router.api_route("{route}", methods=_ALL_METHODS)' in compat_text:
            blockers.append(f"selected exact production_compat decorator must be absent: {route}")
    for route in RETAINED_WILDCARD_ROUTES:
        if f'@router.api_route("{route}", methods=_ALL_METHODS)' not in compat_text:
            blockers.append(f"retained wildcard production_compat decorator must remain: {route}")
    if "wildcard_router = APIRouter()" not in compat_text or "@wildcard_router.api_route" not in compat_text:
        blockers.append("wildcard_router must remain")

    for route, patterns in NEXT_NATIVE_EXACT_PATTERNS.items():
        if not any(re.search(pattern, native_text) for pattern in patterns):
            blockers.append(f"Next-native exact route must exist: {route}")

    for route in UNRELATED_PRODUCTION_COMPAT_ROUTES:
        if not _contains_route(compat_text, route):
            blockers.append(f"unrelated production_compat route must remain: {route}")

    result = _dict(data.get("cleanup_result"))
    if result.get("status") != "cleanup_succeeded":
        blockers.append("cleanup_result.status must be cleanup_succeeded")
    if result.get("expected_deletion_count") != 5:
        blockers.append("cleanup_result.expected_deletion_count must be 5")
    if tuple(_list(result.get("production_compat_cleanups_executed"))) != SELECTED_EXACT_ROUTES:
        blockers.append("cleanup_result.production_compat_cleanups_executed must record the five exact routes")
    if result.get("wildcard_cleanup_executed") is not False:
        blockers.append("wildcard_cleanup_executed must remain false")
    if _list(result.get("runtime_deletions_executed")):
        blockers.append("runtime_deletions_executed must remain []")
    if result.get("delete_ready") is not False:
        blockers.append("delete_ready must remain false")

    continuity = _dict(data.get("business_continuity"))
    if continuity.get("legacy_runtime_retained") is not True:
        blockers.append("legacy runtime must be retained")
    if continuity.get("wildcard_router_retained") is not True:
        blockers.append("wildcard router retention must be recorded")
    if continuity.get("unrelated_production_compat_routes_retained") is not True:
        blockers.append("unrelated production_compat route retention must be recorded")
    for key in (
        "timer_execution_triggered",
        "outbound_send_triggered",
        "external_live_call_triggered",
        "payment_oauth_wecom_callback_public_submit_affected",
    ):
        if continuity.get(key) is not False:
            blockers.append(f"business_continuity.{key} must be false")

    if not _production_compat_diff_is_exact_batch():
        blockers.append("production_compat diff must only remove the five selected exact decorators")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside batch cleanup allowlist: {unexpected}")

    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT_CHANGED_FILES or path.startswith(FORBIDDEN_CHANGED_PREFIXES))
    if forbidden:
        blockers.append(f"forbidden protected/runtime files changed: {forbidden}")

    deleted_or_renamed = _deleted_or_renamed_files()
    details["deleted_or_renamed_files"] = deleted_or_renamed
    if deleted_or_renamed:
        blockers.append(f"runtime file deletion/rename is not allowed: {deleted_or_renamed}")

    changed_text = PLAN_YAML.read_text(encoding="utf-8").lower()
    for claim in ("delete_ready: true", "delete_ready true", "wildcard_cleanup_executed: true", "runtime deletion executed: true"):
        if claim in changed_text:
            blockers.append(f"forbidden cleanup claim found: {claim}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-820 Batch Exact-Route Cleanup Check", "", f"- overall: {report['overall']}", "- blockers:"]
    lines.extend(f"  - {item}" for item in report.get("blockers", []) or ["none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


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
