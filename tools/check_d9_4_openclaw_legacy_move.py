#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

ARCHIVE_DIR = "legacy_flask/openclaw_legacy"
MOVED_FILES = [
    "legacy_flask/openclaw_legacy/__init__.py",
    "legacy_flask/openclaw_legacy/README.md",
    "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
    "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
]
SHIM_FILES = [
    "openclaw_service/__init__.py",
    "openclaw_service/README.md",
    "openclaw_service/LEGACY_FROZEN.md",
]
D7_7_ADAPTER_FILES = [
    "aicrm_next/integration_gateway/mcp_openclaw_adapters.py",
    "aicrm_next/integration_gateway/mcp_openclaw_contracts.py",
]
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
DOCS_TO_SCAN = [
    "docs/d9_5_openclaw_service_shim_removal_plan.md",
    "docs/d9_5_openclaw_final_reference_scan_plan.md",
    "docs/d9_5_openclaw_shim_removal_readiness_checklist.md",
    "docs/d9_4_openclaw_legacy_move_implementation_report.md",
    "docs/d9_3_openclaw_legacy_skeleton_implementation_report.md",
    "docs/d9_2_openclaw_legacy_move_plan.md",
    "docs/d9_2_openclaw_legacy_move_map.md",
    "docs/d9_2_openclaw_import_rewrite_plan.md",
    "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
    "docs/d9_openclaw_legacy_dependency_inventory.md",
    "docs/d9_openclaw_mcp_compatibility_matrix.md",
    "docs/d9_1_openclaw_import_allowlist.md",
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


def _check_archive(blockers: list[Json]) -> Json:
    archive_exists = _path(ARCHIVE_DIR).is_dir()
    moved = {relpath: _path(relpath).exists() for relpath in MOVED_FILES}
    if not archive_exists:
        blockers.append({"reason": "legacy_flask_openclaw_legacy_missing", "path": ARCHIVE_DIR})
    for relpath, exists in moved.items():
        if not exists:
            blockers.append({"reason": "moved_file_missing", "path": relpath})
    init_path = _path("legacy_flask/openclaw_legacy/__init__.py")
    imports_old = _detect_openclaw_imports(init_path) if init_path.exists() else []
    for item in imports_old:
        blockers.append({"reason": "archive_imports_openclaw_service", **item})
    return {
        "legacy_flask_openclaw_legacy_exists": archive_exists,
        "moved_files": moved,
        "archive_imports_openclaw_service": bool(imports_old),
    }


def _check_shim(blockers: list[Json]) -> Json:
    shim_files = {relpath: _path(relpath).exists() for relpath in SHIM_FILES}
    for relpath, exists in shim_files.items():
        if not exists:
            blockers.append({"reason": "shim_file_missing", "path": relpath})
    init_path = _path("openclaw_service/__init__.py")
    source = init_path.read_text(encoding="utf-8") if init_path.exists() else ""
    is_shim = (
        "LEGACY_COMPATIBILITY_SHIM" in source
        and "legacy_flask.openclaw_legacy" in source
        and "aicrm_next.integration_gateway" in source
    )
    if not is_shim:
        blockers.append({"reason": "openclaw_service_not_compatibility_shim", "path": "openclaw_service/__init__.py"})
    return {"shim_files": shim_files, "openclaw_service_is_shim": is_shim}


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


def _check_d9_1_import_freeze(blockers: list[Json]) -> Json:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
        result = checker.run_check()
    except Exception as exc:  # pragma: no cover
        blockers.append({"reason": "d9_1_import_freeze_check_failed", "error": str(exc)})
        return {"ok": False, "error": str(exc), "forbidden_runtime_imports": []}
    if not result.get("ok"):
        blockers.append({"reason": "d9_1_import_freeze_not_pass", "blockers": result.get("blockers", [])})
    return {
        "ok": bool(result.get("ok")),
        "forbidden_runtime_imports": result.get("forbidden_runtime_imports", []),
        "blockers": result.get("blockers", []),
    }


def _check_d7_7_adapters(blockers: list[Json]) -> Json:
    missing = [relpath for relpath in D7_7_ADAPTER_FILES if not _path(relpath).exists()]
    for relpath in missing:
        blockers.append({"reason": "missing_d7_7_adapter_file", "path": relpath})
    return {"present": not missing, "missing": missing}


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
    archive = _check_archive(blockers)
    shim = _check_shim(blockers)
    aicrm_imports = _check_aicrm_next_imports(blockers)
    import_freeze = _check_d9_1_import_freeze(blockers)
    d7_7 = _check_d7_7_adapters(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "metadata_only_move",
                "message": "The source openclaw_service tree only contained the frozen marker before D9.4; no runtime owner was created.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "legacy_flask_openclaw_legacy_exists": archive["legacy_flask_openclaw_legacy_exists"],
        "moved_files": archive["moved_files"],
        "shim_files": shim["shim_files"],
        "openclaw_service_is_shim": shim["openclaw_service_is_shim"],
        "aicrm_next_imports_openclaw_service": aicrm_imports["aicrm_next_imports_openclaw_service"],
        "aicrm_next_import_findings": aicrm_imports["findings"],
        "forbidden_runtime_imports": import_freeze["forbidden_runtime_imports"],
        "import_freeze_status": import_freeze,
        "d7_7_adapter_files": d7_7,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_FOR_D9_4_OPENCLAW_MOVE_ACCEPTANCE_WITH_SHIM"
            if not blockers
            else "BLOCKED_D9_4_OPENCLAW_MOVE"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.4 OpenClaw Legacy Move Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- legacy_flask_openclaw_legacy_exists: {str(result['legacy_flask_openclaw_legacy_exists']).lower()}",
        f"- openclaw_service_is_shim: {str(result['openclaw_service_is_shim']).lower()}",
        f"- aicrm_next_imports_openclaw_service: {str(result['aicrm_next_imports_openclaw_service']).lower()}",
        f"- forbidden_runtime_imports: {len(result['forbidden_runtime_imports'])}",
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
    parser = argparse.ArgumentParser(description="Check D9.4 OpenClaw legacy move with compatibility shim.")
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
