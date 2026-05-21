#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

INVENTORY = "docs/d8_5_legacy_db_maintenance_command_inventory.md"
RETIREMENT_PLAN = "docs/d8_5_legacy_db_maintenance_command_retirement_plan.md"
REPLACEMENT_MATRIX = "docs/d8_5_maintenance_command_replacement_matrix.md"

FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
ALLOWED_REPLACEMENT_STATUSES = {"available", "planned", "needs_manual_review", "blocked"}

DOCS_TO_SCAN = [
    INVENTORY,
    RETIREMENT_PLAN,
    REPLACEMENT_MATRIX,
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
    "docs/production_replacement_route.md",
]


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


def _changed_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        paths.append(path)
    return paths


def _is_production_config_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("deploy/")
        or lowered == ".github/workflows/deploy.yml"
        or "nginx" in lowered
        or "systemd" in lowered
        or lowered.endswith(".service")
        or lowered.endswith(".timer")
    )


def _parse_markdown_table(relpath: str) -> list[dict[str, str]]:
    rows: list[str] = []
    for line in _read(relpath).splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            rows.append(stripped)
    if len(rows) < 2:
        return []
    header = [item.strip() for item in rows[0].strip("|").split("|")]
    data_rows: list[dict[str, str]] = []
    for row in rows[2:]:
        cells = [item.strip() for item in row.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        data_rows.append(dict(zip(header, cells)))
    return data_rows


def _check_required_files(blockers: list[Json]) -> Json:
    files = {
        "inventory_exists": _path(INVENTORY).exists(),
        "retirement_plan_exists": _path(RETIREMENT_PLAN).exists(),
        "replacement_matrix_exists": _path(REPLACEMENT_MATRIX).exists(),
    }
    for field, exists in files.items():
        if not exists:
            blockers.append({"reason": "missing_required_d8_5_file", "field": field})
    return files


def _check_inventory_coverage(blockers: list[Json]) -> Json:
    if not _path(INVENTORY).exists():
        return {"covered": [], "missing": []}
    text = _read(INVENTORY)
    required = [
        "python3 app.py init-db-legacy",
        "python3 legacy_flask_app.py init-db",
        "delete-questionnaire-submissions",
        "wecom_ability_service.db.init_db()",
        "wecom_ability_service/schema_postgres.sql",
        "migrations/env.py",
        "scripts/run_build.py",
        "scripts/seed_automation_conversion_demo.py --init-db",
        "scripts/run_marketing_automation_backfill.py",
    ]
    missing = [item for item in required if item not in text]
    for item in missing:
        blockers.append({"reason": "inventory_missing_required_command", "command": item})
    return {"covered": [item for item in required if item not in missing], "missing": missing}


def _check_legacy_commands_retained(blockers: list[Json]) -> Json:
    checks = {
        "app_py_init_db_legacy": _path("app.py").exists() and "init-db-legacy" in _read("app.py"),
        "app_py_init_db_alias": _path("app.py").exists() and 'subparsers.add_parser("init-db"' in _read("app.py"),
        "app_py_cleanup_legacy": _path("app.py").exists()
        and "delete-questionnaire-submissions-legacy" in _read("app.py"),
        "legacy_flask_app_init_db": _path("legacy_flask_app.py").exists()
        and 'subparsers.add_parser("init-db"' in _read("legacy_flask_app.py"),
        "legacy_flask_app_cleanup": _path("legacy_flask_app.py").exists()
        and "delete-questionnaire-submissions" in _read("legacy_flask_app.py"),
        "db_init_helper": _path("wecom_ability_service/db/__init__.py").exists()
        and "def init_db()" in _read("wecom_ability_service/db/__init__.py"),
        "legacy_http_api_init_db": _path("wecom_ability_service/http/ops.py").exists()
        and "/api/init-db" in _read("wecom_ability_service/http/ops.py"),
    }
    for name, retained in checks.items():
        if not retained:
            blockers.append({"reason": "legacy_command_missing", "command_check": name})
    return {"retained": all(checks.values()), "checks": checks}


def _is_destructive_row(row: dict[str, str]) -> bool:
    haystack = " ".join(row.values()).lower()
    return any(word in haystack for word in ["delete", "cleanup", "destructive", "backfill", "seed"])


def _check_replacement_matrix(blockers: list[Json]) -> Json:
    if not _path(REPLACEMENT_MATRIX).exists():
        return {
            "rows": 0,
            "invalid_replacement_statuses": [],
            "destructive_without_signoff": [],
            "production_auto_run_enabled": [],
        }
    rows = _parse_markdown_table(REPLACEMENT_MATRIX)
    invalid_statuses: list[Json] = []
    destructive_without_signoff: list[Json] = []
    production_auto_run_enabled: list[Json] = []
    for row in rows:
        command = row.get("legacy_command", "")
        status = row.get("replacement_status", "")
        if status not in ALLOWED_REPLACEMENT_STATUSES:
            finding = {"legacy_command": command, "replacement_status": status}
            invalid_statuses.append(finding)
            blockers.append({"reason": "invalid_replacement_status", **finding})
        production = row.get("can_run_in_production", "").lower()
        signoff = row.get("requires_human_signoff", "").lower()
        if production != "false":
            finding = {"legacy_command": command, "can_run_in_production": row.get("can_run_in_production", "")}
            production_auto_run_enabled.append(finding)
            blockers.append({"reason": "production_auto_run_not_disabled", **finding})
        if _is_destructive_row(row) and signoff != "true":
            finding = {"legacy_command": command, "requires_human_signoff": row.get("requires_human_signoff", "")}
            destructive_without_signoff.append(finding)
            blockers.append({"reason": "destructive_command_without_human_signoff", **finding})
    if not rows:
        blockers.append({"reason": "replacement_matrix_table_missing"})
    return {
        "rows": len(rows),
        "invalid_replacement_statuses": invalid_statuses,
        "destructive_without_signoff": destructive_without_signoff,
        "production_auto_run_enabled": production_auto_run_enabled,
    }


def _check_default_runtime(blockers: list[Json]) -> Json:
    source = _read("app.py") if _path("app.py").exists() else ""
    default_next = 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source and 'command = args.command or "run"' in source and "run_next()" in source
    if not default_next:
        blockers.append({"reason": "app_py_default_not_next"})
    return {"default_runtime": "ai_crm_next" if default_next else "unknown"}


def _check_fallback_exists(blockers: list[Json]) -> Json:
    checks = {
        "legacy_flask_app.py": _path("legacy_flask_app.py").exists(),
        "legacy_flask/": _path("legacy_flask").is_dir(),
        "wecom_ability_service/": _path("wecom_ability_service").is_dir(),
        "wecom_ability_service/__init__.py": _path("wecom_ability_service/__init__.py").exists(),
        "openclaw_service/": _path("openclaw_service").is_dir(),
    }
    for path, exists in checks.items():
        if not exists:
            blockers.append({"reason": "legacy_fallback_missing", "path": path})
    return {"exists": all(checks.values()), "checks": checks}


def _check_production_config_modified(blockers: list[Json]) -> Json:
    modified = [path for path in _changed_paths() if _is_production_config_path(path)]
    if modified:
        blockers.append({"reason": "production_config_modified", "paths": modified})
    return {"production_config_modified": bool(modified), "modified_paths": modified}


def _check_forbidden_status_markers(blockers: list[Json]) -> list[Json]:
    findings: list[Json] = []
    for relpath in DOCS_TO_SCAN:
        path = _path(relpath)
        if not path.exists():
            blockers.append({"reason": "missing_doc_for_status_scan", "path": relpath})
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                finding = {"path": relpath, "marker": marker}
                findings.append(finding)
                blockers.append({"reason": "forbidden_status_marker", **finding})
    return findings


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    required_files = _check_required_files(blockers)
    inventory_coverage = _check_inventory_coverage(blockers)
    legacy_commands = _check_legacy_commands_retained(blockers)
    matrix = _check_replacement_matrix(blockers)
    default_runtime = _check_default_runtime(blockers)
    fallback = _check_fallback_exists(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_status_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "planning_only",
                "message": "D8.5 inventories legacy maintenance commands; it does not delete commands or run production migrations.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        **required_files,
        "inventory_coverage": inventory_coverage,
        "legacy_commands_retained": legacy_commands["retained"],
        "legacy_command_checks": legacy_commands["checks"],
        "destructive_commands_guarded": not matrix["destructive_without_signoff"],
        "production_auto_run_disabled": not matrix["production_auto_run_enabled"],
        "replacement_matrix": matrix,
        "default_runtime": default_runtime["default_runtime"],
        "legacy_fallback_exists": fallback["exists"],
        "legacy_fallback_checks": fallback["checks"],
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": (
            "READY_FOR_D8_5_MAINTENANCE_COMMAND_PLANNING_ACCEPTANCE_NOT_DELETED"
            if not blockers
            else "BLOCKED_D8_5_MAINTENANCE_COMMAND_PLANNING"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D8.5 Legacy Maintenance Command Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- inventory_exists: {str(result['inventory_exists']).lower()}",
        f"- retirement_plan_exists: {str(result['retirement_plan_exists']).lower()}",
        f"- replacement_matrix_exists: {str(result['replacement_matrix_exists']).lower()}",
        f"- legacy_commands_retained: {str(result['legacy_commands_retained']).lower()}",
        f"- destructive_commands_guarded: {str(result['destructive_commands_guarded']).lower()}",
        f"- production_auto_run_disabled: {str(result['production_auto_run_disabled']).lower()}",
        f"- default_runtime: {result['default_runtime']}",
        f"- legacy_fallback_exists: {str(result['legacy_fallback_exists']).lower()}",
        f"- production_config_modified: {str(result['production_config_modified']).lower()}",
        "",
        "## Blockers",
    ]
    if result["blockers"]:
        lines.extend(f"- `{json.dumps(item, ensure_ascii=False)}`" for item in result["blockers"])
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Warnings")
    if result["warnings"]:
        lines.extend(f"- `{json.dumps(item, ensure_ascii=False)}`" for item in result["warnings"])
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.5 legacy maintenance command retirement planning readiness.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    result = run_check()
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(md_path, result)
    print(f"wrote markdown report: {md_path}")
    print(f"wrote json report: {json_path}")
    print(f"overall: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
