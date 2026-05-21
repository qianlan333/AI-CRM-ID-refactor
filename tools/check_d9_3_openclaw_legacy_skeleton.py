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

SKELETON_DIR = "legacy_flask/openclaw_legacy"
SKELETON_FILES = [
    "legacy_flask/openclaw_legacy/__init__.py",
    "legacy_flask/openclaw_legacy/README.md",
    "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
    "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
]
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
DOCS_TO_SCAN = [
    "docs/d9_4_openclaw_legacy_move_implementation_report.md",
    "docs/d9_3_openclaw_legacy_skeleton_implementation_report.md",
    "docs/d9_2_openclaw_legacy_move_plan.md",
    "docs/d9_2_openclaw_legacy_move_map.md",
    "docs/d9_2_openclaw_import_rewrite_plan.md",
    "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
    "docs/d9_openclaw_legacy_dependency_inventory.md",
    "docs/d9_openclaw_mcp_compatibility_matrix.md",
    "docs/d9_1_openclaw_legacy_import_freeze_plan.md",
    "docs/d9_1_openclaw_import_allowlist.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
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


def _check_skeleton(blockers: list[Json]) -> Json:
    skeleton_exists = _path(SKELETON_DIR).is_dir()
    files = {relpath: _path(relpath).exists() for relpath in SKELETON_FILES}
    if not skeleton_exists:
        blockers.append({"reason": "skeleton_missing", "path": SKELETON_DIR})
    for relpath, exists in files.items():
        if not exists:
            blockers.append({"reason": "skeleton_file_missing", "path": relpath})
    return {"skeleton_exists": skeleton_exists, "skeleton_files": files}


def _check_skeleton_imports(blockers: list[Json]) -> Json:
    init_path = _path("legacy_flask/openclaw_legacy/__init__.py")
    imports: list[Json] = []
    if init_path.exists():
        imports = _detect_openclaw_imports(init_path)
    for item in imports:
        blockers.append({"reason": "skeleton_imports_openclaw_service", **item})
    return {"skeleton_imports_openclaw_service": bool(imports), "imports": imports}


def _check_openclaw_service_retained(blockers: list[Json]) -> Json:
    service_exists = _path("openclaw_service").is_dir()
    frozen_exists = _path("openclaw_service/LEGACY_FROZEN.md").exists()
    if not service_exists:
        blockers.append({"reason": "openclaw_service_missing"})
    if not frozen_exists:
        blockers.append({"reason": "openclaw_legacy_frozen_missing"})
    moved = not service_exists or not frozen_exists
    return {"openclaw_service_still_in_place": service_exists and frozen_exists, "openclaw_service_moved": moved}


def _check_no_compatibility_shim(blockers: list[Json]) -> Json:
    shim_path = _path("openclaw_service/__init__.py")
    created = shim_path.exists()
    d9_4_shim = created and "LEGACY_COMPATIBILITY_SHIM" in shim_path.read_text(encoding="utf-8")
    if created and not d9_4_shim:
        blockers.append({"reason": "openclaw_service_compatibility_shim_created", "path": "openclaw_service/__init__.py"})
    return {"compatibility_shim_created": created, "d9_4_compatibility_shim": d9_4_shim}


def _check_aicrm_next_imports(blockers: list[Json]) -> Json:
    findings: list[Json] = []
    for root in ["aicrm_next", "experiments/ai_crm_next/src/aicrm_next"]:
        root_path = _path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"(^|\n)\s*(from\s+openclaw_service\b|import\s+openclaw_service\b)", source):
                finding = {"path": str(path.relative_to(PROJECT_ROOT))}
                findings.append(finding)
                blockers.append({"reason": "aicrm_next_imports_openclaw_service", **finding})
    return {"aicrm_next_imports_openclaw_service": bool(findings), "findings": findings}


def _check_import_freeze_status(blockers: list[Json]) -> Json:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
        result = checker.run_check()
    except Exception as exc:  # pragma: no cover - defensive checker path
        blockers.append({"reason": "d9_1_import_freeze_check_failed", "error": str(exc)})
        return {"ok": False, "error": str(exc)}
    if not result.get("ok"):
        blockers.append({"reason": "d9_1_import_freeze_not_pass", "blockers": result.get("blockers", [])})
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
    skeleton = _check_skeleton(blockers)
    skeleton_imports = _check_skeleton_imports(blockers)
    retained = _check_openclaw_service_retained(blockers)
    shim = _check_no_compatibility_shim(blockers)
    aicrm_imports = _check_aicrm_next_imports(blockers)
    import_freeze = _check_import_freeze_status(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "skeleton_only",
                "message": "D9.3 creates only the archive package skeleton; openclaw_service remains in place.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "skeleton_exists": skeleton["skeleton_exists"],
        "skeleton_files": skeleton["skeleton_files"],
        "skeleton_imports_openclaw_service": skeleton_imports["skeleton_imports_openclaw_service"],
        "openclaw_service_still_in_place": retained["openclaw_service_still_in_place"],
        "openclaw_service_moved": retained["openclaw_service_moved"],
        "compatibility_shim_created": shim["compatibility_shim_created"],
        "aicrm_next_imports_openclaw_service": aicrm_imports["aicrm_next_imports_openclaw_service"],
        "aicrm_next_import_findings": aicrm_imports["findings"],
        "import_freeze_status": import_freeze,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_FOR_D9_3_OPENCLAW_SKELETON_ACCEPTANCE_NOT_MOVED"
            if not blockers
            else "BLOCKED_D9_3_OPENCLAW_SKELETON"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.3 OpenClaw Legacy Skeleton Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- skeleton_exists: {str(result['skeleton_exists']).lower()}",
        f"- skeleton_imports_openclaw_service: {str(result['skeleton_imports_openclaw_service']).lower()}",
        f"- openclaw_service_still_in_place: {str(result['openclaw_service_still_in_place']).lower()}",
        f"- openclaw_service_moved: {str(result['openclaw_service_moved']).lower()}",
        f"- compatibility_shim_created: {str(result['compatibility_shim_created']).lower()}",
        f"- aicrm_next_imports_openclaw_service: {str(result['aicrm_next_imports_openclaw_service']).lower()}",
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
    parser = argparse.ArgumentParser(description="Check D9.3 OpenClaw legacy skeleton readiness.")
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
