#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

PLAN = "docs/d9_1_openclaw_legacy_import_freeze_plan.md"
DEFAULT_ALLOWLIST = "docs/d9_1_openclaw_import_allowlist.md"
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
D7_7_ADAPTER_FILES = [
    "aicrm_next/integration_gateway/mcp_openclaw_adapters.py",
    "aicrm_next/integration_gateway/mcp_openclaw_contracts.py",
]
DOCS_TO_SCAN = [
    PLAN,
    DEFAULT_ALLOWLIST,
    "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
    "docs/d9_openclaw_legacy_dependency_inventory.md",
    "docs/d9_openclaw_mcp_compatibility_matrix.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]
PYTHON_SCAN_ROOTS = [
    "aicrm_next",
    "experiments/ai_crm_next/src/aicrm_next",
    "legacy_flask",
    "wecom_ability_service",
    "tools",
    "scripts",
    "tests",
    "experiments/ai_crm_next/tests",
]
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}


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


def _path_is_skipped(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in PYTHON_SCAN_ROOTS:
        root_path = _path(root)
        if not root_path.exists():
            continue
        if root_path.is_file() and root_path.suffix == ".py":
            files.append(root_path)
            continue
        for path in root_path.rglob("*.py"):
            if not _path_is_skipped(path):
                files.append(path)
    return sorted(set(files))


def _detect_openclaw_imports(path: Path) -> list[Json]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [{"line": exc.lineno or 0, "pattern": "syntax_error", "module": "", "error": str(exc)}]
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


def _entry_allowed(entry: Json, rows: list[dict[str, str]]) -> bool:
    relpath = entry["path"]
    for row in rows:
        if row.get("allowed", "").lower() != "true":
            continue
        pattern = row.get("path", "").strip("`")
        if fnmatch.fnmatch(relpath, pattern):
            return True
    return False


def _is_aicrm_next_path(relpath: str) -> bool:
    return relpath.startswith("aicrm_next/") or relpath.startswith("experiments/ai_crm_next/src/aicrm_next/")


def _check_required_files(blockers: list[Json], allowlist: str) -> Json:
    checks = {
        "plan_exists": _path(PLAN).exists(),
        "allowlist_exists": _path(allowlist).exists(),
        "checker_exists": _path("tools/check_d9_1_openclaw_import_freeze.py").exists(),
    }
    for field, exists in checks.items():
        if not exists:
            blockers.append({"reason": "missing_required_d9_1_file", "field": field})
    return checks


def _check_openclaw_retained(blockers: list[Json]) -> Json:
    service_exists = _path("openclaw_service").is_dir()
    frozen_exists = _path("openclaw_service/LEGACY_FROZEN.md").exists()
    archive_path = _path("legacy_flask/openclaw_legacy")
    moved = archive_path.exists() and not (_is_d9_3_skeleton_only(archive_path) or _is_d9_4_archived_with_shim(archive_path))
    if not service_exists:
        blockers.append({"reason": "openclaw_service_missing"})
    if not frozen_exists:
        blockers.append({"reason": "openclaw_legacy_frozen_missing"})
    if moved:
        blockers.append({"reason": "openclaw_service_moved", "path": "legacy_flask/openclaw_legacy"})
    return {"openclaw_service_exists": service_exists, "legacy_frozen_exists": frozen_exists, "openclaw_service_moved": moved}


def _is_d9_3_skeleton_only(path: Path) -> bool:
    if not path.exists():
        return False
    expected = {
        "legacy_flask/openclaw_legacy/__init__.py",
        "legacy_flask/openclaw_legacy/README.md",
        "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
        "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
    }
    files = {str(item.relative_to(PROJECT_ROOT)) for item in path.rglob("*") if item.is_file()}
    if files != expected:
        return False
    source = _path("legacy_flask/openclaw_legacy/__init__.py").read_text(encoding="utf-8")
    return not re.search(r"(^|\n)\s*(from\s+openclaw_service\b|import\s+openclaw_service\b)", source)


def _is_d9_4_archived_with_shim(path: Path) -> bool:
    if not path.exists():
        return False
    required = {
        "legacy_flask/openclaw_legacy/__init__.py",
        "legacy_flask/openclaw_legacy/README.md",
        "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
        "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
    }
    files = {str(item.relative_to(PROJECT_ROOT)) for item in path.rglob("*") if item.is_file()}
    if not required.issubset(files):
        return False
    shim_path = _path("openclaw_service/__init__.py")
    if not shim_path.exists():
        return False
    shim_source = shim_path.read_text(encoding="utf-8")
    archive_source = _path("legacy_flask/openclaw_legacy/__init__.py").read_text(encoding="utf-8")
    return (
        "LEGACY_COMPATIBILITY_SHIM" in shim_source
        and "legacy_flask.openclaw_legacy" in shim_source
        and not re.search(r"(^|\n)\s*(from\s+openclaw_service\b|import\s+openclaw_service\b)", archive_source)
    )


def _check_allowlist(blockers: list[Json], allowlist: str) -> Json:
    if not _path(allowlist).exists():
        return {"rows": 0, "aicrm_next_allowed": False, "entries": []}
    rows = _parse_markdown_table(allowlist)
    aicrm_next_allowed = [
        row
        for row in rows
        if row.get("allowed", "").lower() == "true"
        and ("aicrm_next" in row.get("path", "") or "experiments/ai_crm_next/src/aicrm_next" in row.get("path", ""))
    ]
    for row in aicrm_next_allowed:
        blockers.append({"reason": "allowlist_allows_aicrm_next_runtime_import", "path": row.get("path", "")})
    if not rows:
        blockers.append({"reason": "allowlist_table_missing"})
    return {"rows": len(rows), "aicrm_next_allowed": bool(aicrm_next_allowed), "entries": rows}


def _check_import_freeze(blockers: list[Json], allowlist_rows: list[dict[str, str]]) -> Json:
    all_imports: list[Json] = []
    forbidden: list[Json] = []
    aicrm_next_imports: list[Json] = []
    for path in _python_files():
        relpath = str(path.relative_to(PROJECT_ROOT))
        for item in _detect_openclaw_imports(path):
            entry = {"path": relpath, **item}
            all_imports.append(entry)
            if _is_aicrm_next_path(relpath):
                aicrm_next_imports.append(entry)
                blockers.append({"reason": "aicrm_next_imports_openclaw_service", **entry})
                continue
            if not _entry_allowed(entry, allowlist_rows):
                forbidden.append(entry)
                blockers.append({"reason": "forbidden_runtime_import", **entry})
    return {
        "all_imports": all_imports,
        "forbidden_runtime_imports": forbidden,
        "aicrm_next_imports_openclaw_service": aicrm_next_imports,
    }


def _check_d7_7_adapter_files(blockers: list[Json]) -> Json:
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


def run_check(allowlist: str = DEFAULT_ALLOWLIST) -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    required = _check_required_files(blockers, allowlist)
    retained = _check_openclaw_retained(blockers)
    allowlist_result = _check_allowlist(blockers, allowlist)
    import_freeze = _check_import_freeze(blockers, allowlist_result["entries"])
    d7_7 = _check_d7_7_adapter_files(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    allowed_references = [row for row in allowlist_result["entries"] if row.get("allowed", "").lower() == "true"]
    if not blockers:
        warnings.append(
            {
                "reason": "import_freeze_only",
                "message": "D9.1 freezes new openclaw_service runtime imports; it does not move or delete the package.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        **required,
        "openclaw_service_exists": retained["openclaw_service_exists"],
        "legacy_frozen_exists": retained["legacy_frozen_exists"],
        "openclaw_service_moved": retained["openclaw_service_moved"],
        "forbidden_runtime_imports": import_freeze["forbidden_runtime_imports"],
        "allowed_references": allowed_references,
        "aicrm_next_imports_openclaw_service": import_freeze["aicrm_next_imports_openclaw_service"],
        "all_openclaw_imports": import_freeze["all_imports"],
        "allowlist_entries": allowlist_result["entries"],
        "d7_7_adapter_files": d7_7,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_FOR_D9_1_IMPORT_FREEZE_ACCEPTANCE_NOT_DELETED"
            if not blockers
            else "BLOCKED_D9_1_IMPORT_FREEZE"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.1 OpenClaw Import Freeze Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- openclaw_service_exists: {str(result['openclaw_service_exists']).lower()}",
        f"- legacy_frozen_exists: {str(result['legacy_frozen_exists']).lower()}",
        f"- forbidden_runtime_imports: {len(result['forbidden_runtime_imports'])}",
        f"- aicrm_next_imports_openclaw_service: {len(result['aicrm_next_imports_openclaw_service'])}",
        f"- allowlist_entries: {len(result['allowlist_entries'])}",
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
    parser = argparse.ArgumentParser(description="Check D9.1 OpenClaw legacy import freeze readiness.")
    parser.add_argument("--allowlist", default=DEFAULT_ALLOWLIST)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    result = run_check(args.allowlist)
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
