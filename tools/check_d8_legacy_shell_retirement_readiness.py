#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

Json = dict[str, Any]

D8_DOCS = [
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_legacy_shell_dependency_inventory.md",
    "docs/d8_legacy_shell_allowed_fallback_matrix.md",
]

D7_DOCS = [
    "docs/d7_1_media_storage_wecom_media_adapter_contract.md",
    "docs/d7_1_media_adapter_implementation_report.md",
    "docs/d7_2_questionnaire_submit_oauth_wecom_tag_adapter_contract.md",
    "docs/d7_2_questionnaire_adapter_implementation_report.md",
    "docs/d7_3_user_ops_dnd_batch_send_wecom_dispatch_adapter_contract.md",
    "docs/d7_3_user_ops_adapter_implementation_report.md",
    "docs/d7_4_product_payment_adapter_contract.md",
    "docs/d7_4_product_payment_adapter_implementation_report.md",
    "docs/d7_5_automation_openclaw_runtime_adapter_contract.md",
    "docs/d7_5_automation_adapter_implementation_report.md",
    "docs/d7_6_archive_contacts_identity_adapter_contract.md",
    "docs/d7_6_archive_contacts_identity_adapter_implementation_report.md",
    "docs/d7_7_mcp_openclaw_legacy_adapter_contract.md",
    "docs/d7_7_mcp_openclaw_legacy_retirement_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
]

LEGACY_SHELL_CORE = [
    "legacy_flask_app.py",
    "wecom_ability_service/__init__.py",
    "wecom_ability_service/routes.py",
    "wecom_ability_service/http/__init__.py",
    "openclaw_service",
]

D8_UPDATE_DOCS = [
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]

FORBIDDEN_STATUS_MARKERS = ["production_ready", "delete_ready", "production_approved"]


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


def _missing_files(relpaths: list[str]) -> list[str]:
    return [relpath for relpath in relpaths if not _path(relpath).exists()]


def _check_required_docs(blockers: list[Json]) -> Json:
    d8_missing = _missing_files(D8_DOCS)
    d7_missing = _missing_files(D7_DOCS)
    update_missing = _missing_files(D8_UPDATE_DOCS)
    for relpath in d8_missing:
        blockers.append({"reason": "missing_d8_doc", "path": relpath})
    for relpath in d7_missing:
        blockers.append({"reason": "missing_d7_doc", "path": relpath})
    for relpath in update_missing:
        blockers.append({"reason": "missing_status_doc", "path": relpath})
    return {
        "d8_docs": {relpath: _path(relpath).exists() for relpath in D8_DOCS},
        "d7_docs_present": not d7_missing,
        "missing_d7_docs": d7_missing,
        "status_docs_present": not update_missing,
        "missing_status_docs": update_missing,
    }


def _check_default_runtime(blockers: list[Json]) -> Json:
    app_path = _path("app.py")
    if not app_path.exists():
        blockers.append({"reason": "missing_app_py"})
        return {"default_runtime": "missing", "app_py_exists": False}
    source = app_path.read_text(encoding="utf-8")
    default_next = (
        'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source
        and 'command = args.command or "run"' in source
        and "if command == \"run\":" in source
        and "run_next()" in source
    )
    if not default_next:
        blockers.append({"reason": "app_py_default_not_next"})
    return {
        "default_runtime": "ai_crm_next" if default_next else "unknown",
        "app_py_exists": True,
        "next_app_import": "aicrm_next.main:app" if 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source else "",
    }


def _check_legacy_shell_core(blockers: list[Json]) -> Json:
    exists = {relpath: _path(relpath).exists() for relpath in LEGACY_SHELL_CORE}
    for relpath, present in exists.items():
        if not present:
            blockers.append({"reason": "missing_legacy_shell_core", "path": relpath})
    return {
        "legacy_fallback_exists": exists["legacy_flask_app.py"],
        "shell_core_exists": all(exists.values()),
        "files": exists,
    }


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def _check_forbidden_imports(blockers: list[Json]) -> list[Json]:
    forbidden: list[Json] = []
    app_path = _path("app.py")
    if app_path.exists():
        imports = _top_level_imports(app_path)
        for name in ["wecom_ability_service", "openclaw_service"]:
            if name in imports:
                forbidden.append({"path": "app.py", "import": name, "scope": "top_level"})
    next_root = _path("aicrm_next")
    if next_root.exists():
        for path in sorted(next_root.rglob("*.py")):
            relpath = path.relative_to(PROJECT_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for name in ["wecom_ability_service", "openclaw_service"]:
                if name in text:
                    forbidden.append({"path": relpath, "import": name, "scope": "next_runtime_source"})
    for item in forbidden:
        blockers.append({"reason": "forbidden_default_next_import", **item})
    return forbidden


def _check_forbidden_status_markers(blockers: list[Json]) -> list[Json]:
    findings: list[Json] = []
    docs_to_scan = D8_DOCS + ["docs/d7_capability_readiness_matrix.md"]
    for relpath in docs_to_scan:
        path = _path(relpath)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                findings.append({"path": relpath, "marker": marker})
                blockers.append({"reason": "forbidden_status_marker", "path": relpath, "marker": marker})
    return findings


def _changed_paths() -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return []
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
        or "/nginx" in lowered
        or "nginx/" in lowered
        or "/systemd" in lowered
        or "systemd/" in lowered
        or lowered.endswith(".service")
        or lowered.endswith(".timer")
    )


def _check_production_config_modified(blockers: list[Json]) -> Json:
    changed = _changed_paths()
    modified = [path for path in changed if _is_production_config_path(path)]
    if modified:
        blockers.append({"reason": "production_config_modified", "paths": modified})
    return {
        "production_config_modified": bool(modified),
        "modified_paths": modified,
    }


def _check_d8_content(blockers: list[Json]) -> Json:
    plan = _read("docs/d8_legacy_flask_shell_retirement_plan.md") if _path("docs/d8_legacy_flask_shell_retirement_plan.md").exists() else ""
    inventory = _read("docs/d8_legacy_shell_dependency_inventory.md") if _path("docs/d8_legacy_shell_dependency_inventory.md").exists() else ""
    fallback = _read("docs/d8_legacy_shell_allowed_fallback_matrix.md") if _path("docs/d8_legacy_shell_allowed_fallback_matrix.md").exists() else ""
    required_plan_terms = [
        "Current State",
        "Why Not Delete The Shell Immediately",
        "D8 Retirement Phases",
        "Delete Gate",
        "Rollback",
        "D8.0 only",
    ]
    missing_plan_terms = [term for term in required_plan_terms if term not in plan]
    required_inventory_columns = [
        "file_or_directory",
        "runtime_imported_by_default_next",
        "runtime_imported_by_legacy_fallback",
        "delete_blocker",
        "future_retirement_phase",
    ]
    missing_inventory_columns = [term for term in required_inventory_columns if term not in inventory]
    required_fallback_columns = ["fallback_area", "allowed", "reason", "next_replacement_status", "retirement_condition", "risk"]
    missing_fallback_columns = [term for term in required_fallback_columns if term not in fallback]
    for term in missing_plan_terms:
        blockers.append({"reason": "d8_plan_missing_required_section", "term": term})
    for term in missing_inventory_columns:
        blockers.append({"reason": "dependency_inventory_missing_column", "term": term})
    for term in missing_fallback_columns:
        blockers.append({"reason": "allowed_fallback_matrix_missing_column", "term": term})
    return {
        "plan_sections_present": not missing_plan_terms,
        "missing_plan_terms": missing_plan_terms,
        "inventory_columns_present": not missing_inventory_columns,
        "missing_inventory_columns": missing_inventory_columns,
        "fallback_columns_present": not missing_fallback_columns,
        "missing_fallback_columns": missing_fallback_columns,
    }


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    required_docs = _check_required_docs(blockers)
    default_runtime = _check_default_runtime(blockers)
    legacy_shell = _check_legacy_shell_core(blockers)
    forbidden_imports = _check_forbidden_imports(blockers)
    forbidden_status_markers = _check_forbidden_status_markers(blockers)
    production_config = _check_production_config_modified(blockers)
    d8_content = _check_d8_content(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "planning_only",
                "message": "D8.0 is a planning/readiness gate only; no legacy shell deletion or production cutover is approved.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "default_runtime": default_runtime["default_runtime"],
        "default_runtime_check": default_runtime,
        "legacy_fallback_exists": legacy_shell["legacy_fallback_exists"],
        "shell_core_exists": legacy_shell["shell_core_exists"],
        "legacy_shell_core": legacy_shell,
        "forbidden_imports": forbidden_imports,
        "forbidden_status_markers": forbidden_status_markers,
        "production_config_modified": production_config["production_config_modified"],
        "production_config": production_config,
        "required_docs": required_docs,
        "d8_content": d8_content,
        "real_external_adapters_enabled": False,
        "production_cutover_executed": False,
        "recommendation": (
            "READY_FOR_D8_PLANNING_ACCEPTANCE_NOT_DELETE"
            if not blockers
            else "FIX_D8_PLANNING_BLOCKERS_BEFORE_ACCEPTANCE"
        ),
    }


def _write_markdown(path: str, result: Json) -> None:
    lines = [
        "# D8 Legacy Shell Retirement Readiness Check",
        "",
        f"- ok: `{str(result['ok']).lower()}`",
        f"- blockers: `{len(result['blockers'])}`",
        f"- warnings: `{len(result['warnings'])}`",
        f"- default_runtime: `{result['default_runtime']}`",
        f"- legacy_fallback_exists: `{str(result['legacy_fallback_exists']).lower()}`",
        f"- shell_core_exists: `{str(result['shell_core_exists']).lower()}`",
        f"- production_config_modified: `{str(result['production_config_modified']).lower()}`",
        f"- recommendation: `{result['recommendation']}`",
        "",
        "## Blockers",
    ]
    if result["blockers"]:
        lines.extend(f"- `{item}`" for item in result["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Required D8 Docs"])
    for relpath, exists in result["required_docs"]["d8_docs"].items():
        lines.append(f"- `{relpath}`: `{str(exists).lower()}`")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8 legacy Flask shell retirement readiness.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    result = run_check()
    if args.output_md:
        _write_markdown(args.output_md, result)
        print(f"wrote markdown report: {args.output_md}")
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote json report: {args.output_json}")
    print(f"overall: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
