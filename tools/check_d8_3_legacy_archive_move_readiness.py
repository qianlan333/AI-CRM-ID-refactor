#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

Json = dict[str, Any]

D8_3_DOCS = [
    "docs/d8_3_legacy_flask_shell_archive_package_plan.md",
    "docs/d8_3_legacy_package_move_map.md",
    "docs/d8_3_legacy_import_rewrite_plan.md",
]

DEPRECATED_WRONG_PLAN_FILENAME = "docs/d8_3_legacy_shell_archive_package_plan.md"

DOCS_TO_SCAN = D8_3_DOCS + [
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]

FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]


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


def _check_required_docs(blockers: list[Json]) -> Json:
    exists = {relpath: _path(relpath).exists() for relpath in D8_3_DOCS}
    for relpath, present in exists.items():
        if not present:
            blockers.append({"reason": "missing_d8_3_doc", "path": relpath})
    deprecated_wrong_plan_filename_present = _path(DEPRECATED_WRONG_PLAN_FILENAME).exists()
    if deprecated_wrong_plan_filename_present:
        blockers.append(
            {
                "reason": "deprecated_wrong_plan_filename_present",
                "path": DEPRECATED_WRONG_PLAN_FILENAME,
            }
        )
    return {
        "plan_exists": exists[D8_3_DOCS[0]],
        "move_map_exists": exists[D8_3_DOCS[1]],
        "import_rewrite_plan_exists": exists[D8_3_DOCS[2]],
        "deprecated_wrong_plan_filename_present": deprecated_wrong_plan_filename_present,
        "files": exists,
    }


def _check_content(blockers: list[Json]) -> Json:
    plan = _read(D8_3_DOCS[0]) if _path(D8_3_DOCS[0]).exists() else ""
    move_map = _read(D8_3_DOCS[1]) if _path(D8_3_DOCS[1]).exists() else ""
    rewrite_plan = _read(D8_3_DOCS[2]) if _path(D8_3_DOCS[2]).exists() else ""
    required_plan_terms = [
        "Target Future Structure",
        "Proposed Mapping",
        "Import Strategy",
        "D8.3.0 planning only",
        "Move Gates",
        "Rollback",
        "legacy_shell_moved",
        "false",
    ]
    required_move_terms = [
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/http/__init__.py",
        "wecom_ability_service/legacy_lockdown.py",
        "openclaw_service/*",
        "default_next_imported",
        "shim_required",
    ]
    required_rewrite_terms = [
        "temporary compatibility shim",
        "from wecom_ability_service",
        "from legacy_flask",
        "aicrm_next",
        "must not import",
        "Rollback Strategy",
    ]
    missing_plan_terms = [term for term in required_plan_terms if term not in plan]
    missing_move_terms = [term for term in required_move_terms if term not in move_map]
    missing_rewrite_terms = [term for term in required_rewrite_terms if term not in rewrite_plan]
    for term in missing_plan_terms:
        blockers.append({"reason": "plan_missing_term", "term": term})
    for term in missing_move_terms:
        blockers.append({"reason": "move_map_missing_term", "term": term})
    for term in missing_rewrite_terms:
        blockers.append({"reason": "import_rewrite_plan_missing_term", "term": term})
    return {
        "plan_complete": not missing_plan_terms,
        "move_map_complete": not missing_move_terms,
        "import_rewrite_plan_complete": not missing_rewrite_terms,
        "missing_plan_terms": missing_plan_terms,
        "missing_move_terms": missing_move_terms,
        "missing_rewrite_terms": missing_rewrite_terms,
    }


def _check_shell_still_in_place(blockers: list[Json]) -> Json:
    exists = {
        "legacy_flask_app.py": _path("legacy_flask_app.py").exists(),
        "wecom_ability_service": _path("wecom_ability_service").exists(),
        "wecom_ability_service/__init__.py": _path("wecom_ability_service/__init__.py").exists(),
        "wecom_ability_service/routes.py": _path("wecom_ability_service/routes.py").exists(),
        "wecom_ability_service/http/__init__.py": _path("wecom_ability_service/http/__init__.py").exists(),
        "openclaw_service": _path("openclaw_service").exists(),
        "wecom_ability_service/legacy_lockdown.py": _path("wecom_ability_service/legacy_lockdown.py").exists(),
    }
    for path, present in exists.items():
        if not present:
            blockers.append({"reason": "legacy_shell_component_missing", "path": path})
    legacy_flask_exists = _path("legacy_flask").exists()
    d8_4_archive_package_present = all(
        _path(relpath).exists()
        for relpath in [
            "legacy_flask/__init__.py",
            "legacy_flask/app_factory.py",
            "legacy_flask/http/__init__.py",
            "legacy_flask/legacy_lockdown.py",
            "docs/d8_4_legacy_flask_archive_package_implementation.md",
            "tools/check_d8_4_legacy_archive_package.py",
        ]
    )
    if legacy_flask_exists and not d8_4_archive_package_present:
        blockers.append({"reason": "unexpected_legacy_flask_package_without_d8_4_gate", "path": "legacy_flask"})
    return {
        "legacy_shell_still_in_place": all(exists.values()),
        "openclaw_service_still_in_place": exists["openclaw_service"],
        "legacy_flask_package_exists": legacy_flask_exists,
        "d8_4_archive_package_present": d8_4_archive_package_present,
        "files": exists,
    }


def _check_default_runtime(blockers: list[Json]) -> str:
    source = _read("app.py") if _path("app.py").exists() else ""
    default_next = 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source and 'command = args.command or "run"' in source and "run_next()" in source
    if not default_next:
        blockers.append({"reason": "app_py_default_not_next"})
    return "ai_crm_next" if default_next else "unknown"


def _check_lockdown_status(blockers: list[Json]) -> Json:
    if not _path("tools/check_d8_2_legacy_lockdown_enforcement.py").exists():
        blockers.append({"reason": "missing_d8_2_checker"})
        return {"checker_exists": False, "ok": False}
    try:
        from tools import check_d8_2_legacy_lockdown_enforcement as d8_2_checker

        result = d8_2_checker.run_check()
    except Exception as exc:
        blockers.append({"reason": "d8_2_checker_failed_to_run", "error": f"{type(exc).__name__}: {exc}"})
        return {"checker_exists": True, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not result.get("ok"):
        blockers.append({"reason": "d8_2_checker_not_ok", "blockers": result.get("blockers", [])})
    return {
        "checker_exists": True,
        "ok": bool(result.get("ok")),
        "lockdown_registered": result.get("lockdown_registered"),
        "retired_routes_blocked": len(result.get("retired_routes_blocked", [])),
        "allowed_fallback_routes_blocked": len(result.get("allowed_fallback_routes_blocked", [])),
    }


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
    docs = _check_required_docs(blockers)
    content = _check_content(blockers)
    shell = _check_shell_still_in_place(blockers)
    default_runtime = _check_default_runtime(blockers)
    lockdown_status = _check_lockdown_status(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_status_markers = _check_forbidden_status_markers(blockers)
    if not blockers and shell["legacy_flask_package_exists"]:
        warnings.append(
            {
                "reason": "superseded_by_d8_4_archive_package",
                "message": "D8.3 planning remains accepted; legacy_flask/ now exists because D8.4 archive package implementation is present.",
            }
        )
    elif not blockers:
        warnings.append(
            {
                "reason": "planning_only_not_moved",
                "message": "D8.3 readiness is planning-only; legacy files stay in place and legacy_flask/ is not created.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "plan_exists": docs["plan_exists"],
        "move_map_exists": docs["move_map_exists"],
        "import_rewrite_plan_exists": docs["import_rewrite_plan_exists"],
        "deprecated_wrong_plan_filename_present": docs["deprecated_wrong_plan_filename_present"],
        "content": content,
        "legacy_shell_still_in_place": shell["legacy_shell_still_in_place"],
        "openclaw_service_still_in_place": shell["openclaw_service_still_in_place"],
        "legacy_flask_package_exists": shell["legacy_flask_package_exists"],
        "d8_4_archive_package_present": shell["d8_4_archive_package_present"],
        "default_runtime": default_runtime,
        "lockdown_status": lockdown_status,
        "production_config_modified": production_config["production_config_modified"],
        "production_config": production_config,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": (
            "READY_FOR_D8_3_ARCHIVE_MOVE_PLANNING_ACCEPTANCE_NOT_MOVED"
            if not blockers
            else "FIX_D8_3_ARCHIVE_MOVE_PLANNING_BLOCKERS_BEFORE_ACCEPTANCE"
        ),
    }


def _write_markdown(path: str, result: Json) -> None:
    lines = [
        "# D8.3 Legacy Archive Move Readiness Check",
        "",
        f"- ok: `{str(result['ok']).lower()}`",
        f"- blockers: `{len(result['blockers'])}`",
        f"- warnings: `{len(result['warnings'])}`",
        f"- plan_exists: `{str(result['plan_exists']).lower()}`",
        f"- move_map_exists: `{str(result['move_map_exists']).lower()}`",
        f"- import_rewrite_plan_exists: `{str(result['import_rewrite_plan_exists']).lower()}`",
        f"- deprecated_wrong_plan_filename_present: `{str(result['deprecated_wrong_plan_filename_present']).lower()}`",
        f"- legacy_shell_still_in_place: `{str(result['legacy_shell_still_in_place']).lower()}`",
        f"- openclaw_service_still_in_place: `{str(result['openclaw_service_still_in_place']).lower()}`",
        f"- legacy_flask_package_exists: `{str(result['legacy_flask_package_exists']).lower()}`",
        f"- default_runtime: `{result['default_runtime']}`",
        f"- lockdown_status_ok: `{str(result['lockdown_status'].get('ok')).lower()}`",
        f"- production_config_modified: `{str(result['production_config_modified']).lower()}`",
        f"- recommendation: `{result['recommendation']}`",
        "",
        "## Blockers",
    ]
    if result["blockers"]:
        lines.extend(f"- `{item}`" for item in result["blockers"])
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.3 legacy archive package move readiness.")
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
