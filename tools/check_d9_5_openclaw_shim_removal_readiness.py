#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

PLAN = "docs/d9_5_openclaw_service_shim_removal_plan.md"
REFERENCE_SCAN_PLAN = "docs/d9_5_openclaw_final_reference_scan_plan.md"
READINESS_CHECKLIST = "docs/d9_5_openclaw_shim_removal_readiness_checklist.md"
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
DOCS_TO_SCAN = [
    PLAN,
    REFERENCE_SCAN_PLAN,
    READINESS_CHECKLIST,
    "docs/d9_4_openclaw_legacy_move_implementation_report.md",
    "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
    "docs/d9_openclaw_legacy_dependency_inventory.md",
    "docs/d9_openclaw_mcp_compatibility_matrix.md",
    "docs/d9_1_openclaw_import_allowlist.md",
    "docs/d9_2_openclaw_legacy_move_map.md",
    "docs/d9_2_openclaw_import_rewrite_plan.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


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


def _detect_openclaw_imports(path: Path) -> list[Json]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imports: list[Json] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "openclaw_service" or alias.name.startswith("openclaw_service."):
                    imports.append({"line": node.lineno, "pattern": "import", "module": alias.name})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "openclaw_service" or module.startswith("openclaw_service."):
                imports.append({"line": node.lineno, "pattern": "from", "module": module})
    return imports


def _check_required_files(blockers: list[Json]) -> Json:
    checks = {
        "plan_exists": _path(PLAN).exists(),
        "reference_scan_plan_exists": _path(REFERENCE_SCAN_PLAN).exists(),
        "readiness_checklist_exists": _path(READINESS_CHECKLIST).exists(),
    }
    for field, exists in checks.items():
        if not exists:
            blockers.append({"reason": "missing_required_d9_5_file", "field": field})
    return checks


def _check_retained_paths(blockers: list[Json]) -> Json:
    service_exists = _path("openclaw_service").is_dir()
    shim_exists = _path("openclaw_service/__init__.py").exists()
    frozen_exists = _path("openclaw_service/LEGACY_FROZEN.md").exists()
    archive_exists = _path("legacy_flask/openclaw_legacy").is_dir()
    if not service_exists:
        blockers.append({"reason": "openclaw_service_missing"})
    if not shim_exists:
        blockers.append({"reason": "openclaw_service_shim_missing", "path": "openclaw_service/__init__.py"})
    if not frozen_exists:
        blockers.append({"reason": "openclaw_service_frozen_missing"})
    if not archive_exists:
        blockers.append({"reason": "legacy_flask_openclaw_legacy_missing"})
    return {
        "openclaw_service_still_exists": service_exists,
        "shim_still_exists": shim_exists,
        "legacy_frozen_exists": frozen_exists,
        "legacy_flask_openclaw_legacy_exists": archive_exists,
    }


def _check_aicrm_next_imports(blockers: list[Json]) -> Json:
    findings: list[Json] = []
    for root in ["aicrm_next", "experiments/ai_crm_next/src/aicrm_next"]:
        root_path = _path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            for item in _detect_openclaw_imports(path):
                finding = {"path": str(path.relative_to(PROJECT_ROOT)), **item}
                findings.append(finding)
                blockers.append({"reason": "aicrm_next_imports_openclaw_service", **finding})
    return {"aicrm_next_imports_openclaw_service": bool(findings), "findings": findings}


def _run_nested_checker(module_name: str, blockers: list[Json], reason: str) -> Json:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        checker = importlib.import_module(module_name)
        result = checker.run_check()
    except Exception as exc:  # pragma: no cover
        blockers.append({"reason": reason, "error": str(exc)})
        return {"ok": False, "error": str(exc)}
    if not result.get("ok"):
        blockers.append({"reason": reason, "blockers": result.get("blockers", [])})
    return {"ok": bool(result.get("ok")), "blockers": result.get("blockers", [])}


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
    required = _check_required_files(blockers)
    retained = _check_retained_paths(blockers)
    aicrm_imports = _check_aicrm_next_imports(blockers)
    import_freeze = _run_nested_checker("tools.check_d9_1_openclaw_import_freeze", blockers, "d9_1_import_freeze_not_pass")
    move_status = _run_nested_checker("tools.check_d9_4_openclaw_legacy_move", blockers, "d9_4_move_check_not_pass")
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "planning_only",
                "message": "D9.5 plans future shim removal; openclaw_service remains in place.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        **required,
        **retained,
        "aicrm_next_imports_openclaw_service": aicrm_imports["aicrm_next_imports_openclaw_service"],
        "aicrm_next_import_findings": aicrm_imports["findings"],
        "import_freeze_status": import_freeze,
        "move_status": move_status,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_FOR_D9_5_SHIM_REMOVAL_PLANNING_ACCEPTANCE_NOT_DELETED"
            if not blockers
            else "BLOCKED_D9_5_SHIM_REMOVAL_PLANNING"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.5 OpenClaw Shim Removal Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- plan_exists: {str(result['plan_exists']).lower()}",
        f"- reference_scan_plan_exists: {str(result['reference_scan_plan_exists']).lower()}",
        f"- readiness_checklist_exists: {str(result['readiness_checklist_exists']).lower()}",
        f"- openclaw_service_still_exists: {str(result['openclaw_service_still_exists']).lower()}",
        f"- shim_still_exists: {str(result['shim_still_exists']).lower()}",
        f"- legacy_flask_openclaw_legacy_exists: {str(result['legacy_flask_openclaw_legacy_exists']).lower()}",
        f"- aicrm_next_imports_openclaw_service: {str(result['aicrm_next_imports_openclaw_service']).lower()}",
        f"- import_freeze_status: {str(result['import_freeze_status'].get('ok')).lower()}",
        f"- move_status: {str(result['move_status'].get('ok')).lower()}",
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
    parser = argparse.ArgumentParser(description="Check D9.5 OpenClaw shim removal planning readiness.")
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
