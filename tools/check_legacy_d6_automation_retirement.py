#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RETIRED_READONLY_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/admin/automation-conversion"),
    ("GET", "/api/admin/automation-conversion/overview"),
    ("GET", "/api/admin/automation-conversion/pools"),
    ("GET", "/api/admin/automation-conversion/members"),
    ("GET", "/api/admin/automation-conversion/members/<member_id>"),
    ("GET", "/api/admin/automation-conversion/execution-records"),
)

RETIRED_ALIAS_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/admin/automation-conversion/programs/<int:program_id>/overview"),
    ("GET", "/admin/automation-conversion/programs/<int:program_id>/executions"),
    ("GET", "/admin/automation-conversion/programs/<int:program_id>/member-ops"),
    ("GET", "/api/admin/automation-conversion/dashboard"),
    ("GET", "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search"),
    ("GET", "/api/admin/automation-conversion/member"),
    ("GET", "/api/admin/automation-conversion/executions"),
    ("GET", "/api/admin/automation-conversion/executions/<int:execution_id>"),
    ("GET", "/api/admin/automation-conversion/executions/<int:execution_id>/items"),
    ("GET", "/api/admin/automation-conversion/execution-items/<int:execution_item_id>"),
)

RETAINED_FALLBACK_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/admin/automation-conversion/member/push-openclaw"),
    ("POST", "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview"),
    ("POST", "/api/admin/automation-conversion/stage/<stage_key>/manual-send"),
    ("POST", "/api/admin/automation-conversion/member/put-in-pool"),
    ("POST", "/api/admin/automation-conversion/member/mark-won"),
    ("POST", "/api/admin/automation-conversion/focus-send-batches/run-due"),
    ("POST", "/api/admin/automation-conversion/sop/run-due"),
    ("POST", "/api/admin/automation-conversion/tasks/run-due"),
    ("POST", "/api/admin/automation-conversion/jobs/run-due"),
    ("POST", "/api/admin/automation-conversion/message-activity-sync/run"),
    ("POST", "/api/admin/automation-conversion/reply-monitor/run-due"),
    ("POST", "/api/admin/automation-conversion/router-pending-callback-check"),
    ("POST", "/api/internal/automation-conversion/lobster-results"),
    ("POST", "/api/internal/automation-conversion/laohuang-chat-results"),
    ("POST", "/api/internal/automation-conversion/router-test-dispatch"),
    ("POST", "/api/customers/automation/activation-webhook"),
    ("POST", "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook"),
    ("POST", "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom"),
)

RETAINED_FALLBACK_FILES: tuple[str, ...] = (
    "wecom_ability_service/http/automation_conversion.py",
    "wecom_ability_service/http/customer_automation.py",
    "wecom_ability_service/http/automation_conversion_member_api.py",
    "wecom_ability_service/http/automation_conversion_delivery.py",
    "wecom_ability_service/http/automation_conversion_runtime_api.py",
    "wecom_ability_service/http/automation_conversion_router_callback_api.py",
    "wecom_ability_service/http/automation_conversion_agent_api.py",
    "wecom_ability_service/http/automation_conversion_operation_tasks.py",
    "wecom_ability_service/http/automation_conversion_workflows.py",
    "wecom_ability_service/http/automation_conversion_review.py",
    "wecom_ability_service/domains/automation_conversion/service.py",
)

NEXT_AUTOMATION_ROUTE_TOKENS: tuple[str, ...] = (
    '@router.get("/api/admin/automation-conversion/overview")',
    '@router.get("/api/admin/automation-conversion/pools")',
    '@router.get("/api/admin/automation-conversion/members")',
    '@router.get("/api/admin/automation-conversion/members/{member_id}")',
    '@router.get("/api/admin/automation-conversion/execution-records")',
)


def _route_methods() -> tuple[dict[str, set[str]], str | None]:
    try:
        from wecom_ability_service import create_app

        app = create_app({"TESTING": True})
    except Exception as exc:  # pragma: no cover - environment diagnostic
        return {}, repr(exc)
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(set(rule.methods) - {"HEAD", "OPTIONS"})
    return routes, None


def _method_absent(routes: dict[str, set[str]], method: str, path: str) -> bool:
    return method.upper() not in routes.get(path, set())


def _method_present(routes: dict[str, set[str]], method: str, path: str) -> bool:
    return method.upper() in routes.get(path, set())


def _changed_files() -> list[str]:
    working_tree_files: set[str] = set()
    for command in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
        result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        if result.returncode == 0:
            working_tree_files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    for base in ("origin/codex/legacy-d5-questionnaire-retirement...HEAD", "origin/main...HEAD"):
        result = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            working_tree_files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
            return sorted(working_tree_files)
    return sorted(working_tree_files)


def _production_config_modified(changed: list[str]) -> bool:
    forbidden_prefixes = ("deploy/", ".github/")
    forbidden_tokens = ("nginx", "systemd", "supervisor", "docker-compose", "production")
    for path in changed:
        lower = path.lower()
        if path.startswith(forbidden_prefixes):
            return True
        if not path.startswith(("docs/", "tests/", "tools/")) and any(token in lower for token in forbidden_tokens):
            return True
    return False


def _source_route_lines(path: str) -> list[str]:
    source_path = REPO_ROOT / path
    if not source_path.exists():
        return []
    lines = []
    for line in source_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "bp.route(" in stripped:
            lines.append(stripped)
    return lines


def build_report() -> dict[str, Any]:
    routes, import_error = _route_methods()
    changed = _changed_files()

    retired_readonly_routes = {
        f"{method} {path}": _method_absent(routes, method, path)
        for method, path in RETIRED_READONLY_ROUTES
    }
    retired_alias_routes = {
        f"{method} {path}": _method_absent(routes, method, path)
        for method, path in RETIRED_ALIAS_ROUTES
    }
    retained_fallbacks = {
        f"{method} {path}": _method_present(routes, method, path)
        for method, path in RETAINED_FALLBACK_ROUTES
    }
    retained_files = {path: (REPO_ROOT / path).exists() for path in RETAINED_FALLBACK_FILES}

    next_api = (REPO_ROOT / "aicrm_next" / "automation_engine" / "api.py").read_text(encoding="utf-8")
    next_routes = {token: token in next_api for token in NEXT_AUTOMATION_ROUTE_TOKENS}
    frontend_routes = (REPO_ROOT / "aicrm_next" / "frontend_compat" / "legacy_routes.py").read_text(encoding="utf-8")
    next_routes["GET /admin/automation-conversion page"] = "/admin/automation-conversion" in frontend_routes

    docs = {
        "legacy_delete_batches": (REPO_ROOT / "docs" / "legacy_delete_batches.md").read_text(encoding="utf-8"),
        "legacy_retirement_plan": (REPO_ROOT / "docs" / "legacy_retirement_plan.md").read_text(encoding="utf-8"),
        "legacy_route_owner_cutover_matrix": (REPO_ROOT / "docs" / "legacy_route_owner_cutover_matrix.md").read_text(encoding="utf-8"),
    }
    docs_record_d6 = all("D6" in content and "Automation" in content and "retired" in content for content in docs.values())
    d7_to_d9_not_retired = (
        "| D7 | Write/external adapters |" in docs["legacy_route_owner_cutover_matrix"]
        and "no deletion until replacement evidence" in docs["legacy_route_owner_cutover_matrix"]
        and "No row is approved for production." in docs["legacy_route_owner_cutover_matrix"]
    )

    stale_readonly_routes = [
        route for route, retired in {**retired_readonly_routes, **retired_alias_routes}.items() if not retired
    ]
    missing_fallbacks = [
        route for route, present in retained_fallbacks.items() if not present
    ] + [path for path, present in retained_files.items() if not present]

    blockers: list[str] = []
    if import_error:
        blockers.append(f"legacy_create_app_import_failed: {import_error}")
    if stale_readonly_routes:
        blockers.append("stale automation readonly routes remain registered")
    if missing_fallbacks:
        blockers.append("write/external/runtime fallback missing")
    if not all(next_routes.values()):
        blockers.append("AI-CRM Next automation readonly route source missing")
    if _production_config_modified(changed):
        blockers.append("production/deploy config modified")
    if not docs_record_d6:
        blockers.append("D6 retirement docs incomplete")
    if not d7_to_d9_not_retired:
        blockers.append("D7-D9 retirement status not clearly blocked")

    report = {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": [],
        "retired_readonly_routes": retired_readonly_routes,
        "retired_alias_routes": retired_alias_routes,
        "retained_write_external_runtime_fallbacks": retained_fallbacks,
        "retained_fallback_files": retained_files,
        "stale_readonly_routes": stale_readonly_routes,
        "source_route_lines": {
            "automation_conversion.py": _source_route_lines("wecom_ability_service/http/automation_conversion.py"),
            "customer_automation.py": _source_route_lines("wecom_ability_service/http/customer_automation.py"),
        },
        "next_automation_routes": next_routes,
        "legacy_fallback_status": {
            "app_py_default_next": 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in (REPO_ROOT / "app.py").read_text(encoding="utf-8"),
            "legacy_flask_app_exists": (REPO_ROOT / "legacy_flask_app.py").exists(),
            "legacy_create_app_import_failed": import_error is not None,
        },
        "production_config_modified": _production_config_modified(changed),
        "changed_files": changed,
        "recommendation": "READY_FOR_D6_AUTOMATION_RETIREMENT_ACCEPTANCE" if not blockers else "FIX_BLOCKERS_BEFORE_D6_ACCEPTANCE",
    }
    return report


def write_json(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Legacy D6 Automation Retirement Check",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- recommendation: {report['recommendation']}",
        f"- production_config_modified: {str(report['production_config_modified']).lower()}",
        "",
        "## Blockers",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Stale Readonly Routes"])
    lines.extend([f"- {item}" for item in report["stale_readonly_routes"]] or ["- none"])
    lines.extend(["", "## Retained Fallbacks"])
    lines.extend(
        f"- {route}: {str(present).lower()}"
        for route, present in report["retained_write_external_runtime_fallbacks"].items()
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check D6 Automation legacy readonly route retirement readiness.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    write_markdown(report, Path(args.output_md))
    write_json(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
