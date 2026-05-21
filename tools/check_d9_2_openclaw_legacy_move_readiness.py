#!/usr/bin/env python
from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

MOVE_PLAN = "docs/d9_2_openclaw_legacy_move_plan.md"
MOVE_MAP = "docs/d9_2_openclaw_legacy_move_map.md"
IMPORT_REWRITE_PLAN = "docs/d9_2_openclaw_import_rewrite_plan.md"
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
DOCS_TO_SCAN = [
    MOVE_PLAN,
    MOVE_MAP,
    IMPORT_REWRITE_PLAN,
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
    checks = {
        "move_plan_exists": _path(MOVE_PLAN).exists(),
        "move_map_exists": _path(MOVE_MAP).exists(),
        "import_rewrite_plan_exists": _path(IMPORT_REWRITE_PLAN).exists(),
    }
    for field, exists in checks.items():
        if not exists:
            blockers.append({"reason": "missing_required_d9_2_file", "field": field})
    return checks


def _check_openclaw_still_in_place(blockers: list[Json]) -> Json:
    service_exists = _path("openclaw_service").is_dir()
    frozen_exists = _path("openclaw_service/LEGACY_FROZEN.md").exists()
    if not service_exists:
        blockers.append({"reason": "openclaw_service_missing"})
    if not frozen_exists:
        blockers.append({"reason": "openclaw_legacy_frozen_missing"})
    moved_paths = [
        path
        for path in _changed_paths()
        if path.startswith("legacy_flask/openclaw_legacy")
        and not _is_allowed_d9_3_skeleton_path(path)
        and not _is_allowed_d9_4_archive_path(path)
    ]
    for path in moved_paths:
        blockers.append({"reason": "openclaw_physical_move_detected", "path": path})
    return {"openclaw_service_still_in_place": service_exists and frozen_exists, "service_exists": service_exists, "legacy_frozen_exists": frozen_exists, "moved_paths": moved_paths}


def _is_allowed_d9_3_skeleton_path(path: str) -> bool:
    return path in {
        "legacy_flask/openclaw_legacy/__init__.py",
        "legacy_flask/openclaw_legacy/README.md",
        "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
        "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
    }


def _is_allowed_d9_4_archive_path(path: str) -> bool:
    return path in {
        "legacy_flask/openclaw_legacy/__init__.py",
        "legacy_flask/openclaw_legacy/README.md",
        "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
        "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
    }


def _skeleton_init_imports_openclaw_service(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    return bool(re.search(r"(^|\n)\s*(from\s+openclaw_service\b|import\s+openclaw_service\b)", source))


def _check_legacy_flask_openclaw_legacy(blockers: list[Json]) -> Json:
    archive_path = _path("legacy_flask/openclaw_legacy")
    if not archive_path.exists():
        return {"status": "absent", "paths": []}
    paths = [path for path in archive_path.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    relpaths = [str(path.relative_to(PROJECT_ROOT)) for path in paths]
    docs_only = all(path.suffix.lower() in {".md", ".txt"} for path in paths)
    expected_skeleton = {
        "legacy_flask/openclaw_legacy/__init__.py",
        "legacy_flask/openclaw_legacy/README.md",
        "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
        "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
    }
    if set(relpaths) == expected_skeleton:
        init_path = _path("legacy_flask/openclaw_legacy/__init__.py")
        if _skeleton_init_imports_openclaw_service(init_path):
            blockers.append({"reason": "openclaw_skeleton_imports_old_package", "path": str(init_path.relative_to(PROJECT_ROOT))})
            return {"status": "skeleton_invalid", "paths": relpaths}
        shim_path = _path("openclaw_service/__init__.py")
        if shim_path.exists() and "LEGACY_COMPATIBILITY_SHIM" in shim_path.read_text(encoding="utf-8"):
            return {"status": "moved_with_shim", "paths": relpaths}
        return {"status": "skeleton_created", "paths": relpaths}
    if not docs_only:
        blockers.append({"reason": "legacy_flask_openclaw_legacy_runtime_package_created", "paths": relpaths})
        return {"status": "runtime_package_present", "paths": relpaths}
    return {"status": "docs_placeholder", "paths": relpaths}


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


def _check_move_map(blockers: list[Json]) -> Json:
    if not _path(MOVE_MAP).exists():
        return {"rows": 0, "missing": ["openclaw_service/", "openclaw_service/LEGACY_FROZEN.md"], "bad_default_next": []}
    rows = _parse_markdown_table(MOVE_MAP)
    covered = {row.get("current_path", "").strip("`") for row in rows}
    required = ["openclaw_service/", "openclaw_service/LEGACY_FROZEN.md"]
    missing = [item for item in required if item not in covered]
    for item in missing:
        blockers.append({"reason": "move_map_missing_required_path", "path": item})
    bad_default_next = [row for row in rows if row.get("default_next_imported", "").lower() != "false"]
    for row in bad_default_next:
        blockers.append({"reason": "move_map_default_next_imported_not_false", "current_path": row.get("current_path", "")})
    return {"rows": len(rows), "missing": missing, "bad_default_next": bad_default_next}


def _check_import_rewrite_plan(blockers: list[Json]) -> Json:
    if not _path(IMPORT_REWRITE_PLAN).exists():
        return {"mentions_temporary_shim": False, "mentions_d7_7_boundary": False}
    text = _read(IMPORT_REWRITE_PLAN)
    mentions_temporary_shim = "temporary compatibility shim" in text or "Temporary Shim Strategy" in text
    mentions_d7_7_boundary = "D7.7" in text and "adapter boundary" in text
    if not mentions_temporary_shim:
        blockers.append({"reason": "import_rewrite_plan_missing_temporary_shim"})
    if not mentions_d7_7_boundary:
        blockers.append({"reason": "import_rewrite_plan_missing_d7_7_boundary"})
    return {"mentions_temporary_shim": mentions_temporary_shim, "mentions_d7_7_boundary": mentions_d7_7_boundary}


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
    required = _check_required_files(blockers)
    retained = _check_openclaw_still_in_place(blockers)
    archive_status = _check_legacy_flask_openclaw_legacy(blockers)
    aicrm_imports = _check_aicrm_next_imports(blockers)
    move_map = _check_move_map(blockers)
    rewrite_plan = _check_import_rewrite_plan(blockers)
    import_freeze = _check_import_freeze_status(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "planning_only",
                "message": "D9.2 plans a future OpenClaw move; it does not move openclaw_service.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        **required,
        "openclaw_service_still_in_place": retained["openclaw_service_still_in_place"],
        "openclaw_service_exists": retained["service_exists"],
        "legacy_frozen_exists": retained["legacy_frozen_exists"],
        "legacy_flask_openclaw_legacy_status": archive_status,
        "aicrm_next_imports_openclaw_service": aicrm_imports["aicrm_next_imports_openclaw_service"],
        "aicrm_next_import_findings": aicrm_imports["findings"],
        "move_map": move_map,
        "import_rewrite_plan": rewrite_plan,
        "import_freeze_status": import_freeze,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_FOR_D9_2_OPENCLAW_MOVE_PLANNING_ACCEPTANCE_NOT_MOVED"
            if not blockers
            else "BLOCKED_D9_2_OPENCLAW_MOVE_PLANNING"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.2 OpenClaw Legacy Move Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- move_plan_exists: {str(result['move_plan_exists']).lower()}",
        f"- move_map_exists: {str(result['move_map_exists']).lower()}",
        f"- import_rewrite_plan_exists: {str(result['import_rewrite_plan_exists']).lower()}",
        f"- openclaw_service_still_in_place: {str(result['openclaw_service_still_in_place']).lower()}",
        f"- legacy_flask_openclaw_legacy_status: {result['legacy_flask_openclaw_legacy_status']['status']}",
        f"- aicrm_next_imports_openclaw_service: {str(result['aicrm_next_imports_openclaw_service']).lower()}",
        f"- import_freeze_status: {str(result['import_freeze_status'].get('ok')).lower()}",
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
    parser = argparse.ArgumentParser(description="Check D9.2 OpenClaw legacy move planning readiness.")
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
