#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

PLAN = "docs/d9_openclaw_legacy_adapter_retirement_plan.md"
DEPENDENCY_INVENTORY = "docs/d9_openclaw_legacy_dependency_inventory.md"
COMPATIBILITY_MATRIX = "docs/d9_openclaw_mcp_compatibility_matrix.md"

FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
ALLOWED_COMPATIBILITY_STATUSES = {
    "fake_contract_ready",
    "staging_validation_required",
    "production_validation_required",
    "deprecated",
    "blocked",
}
REQUIRED_CAPABILITIES = [
    "MCP list tools",
    "MCP invoke tool",
    "resolve_customer",
    "get_customer_context",
    "get_recent_messages",
    "automation member context",
    "automation execution records context",
    "OpenClaw member context push",
    "OpenClaw workflow context push",
    "legacy skill request mapping",
    "plugin / skill compatibility docs",
    "bearer token / auth boundary",
    "webhook replay / retry handling",
]
DOCS_TO_SCAN = [
    PLAN,
    DEPENDENCY_INVENTORY,
    COMPATIBILITY_MATRIX,
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
    "docs/d7_capability_readiness_matrix.md",
]
D7_7_REQUIRED = [
    "docs/d7_7_mcp_openclaw_legacy_adapter_contract.md",
    "docs/d7_7_mcp_openclaw_legacy_retirement_report.md",
    "tools/check_d7_7_mcp_openclaw_adapter_contract.py",
    "tests/test_d7_7_mcp_openclaw_adapter_contract.py",
    "aicrm_next/integration_gateway/mcp_openclaw_adapters.py",
    "aicrm_next/integration_gateway/mcp_openclaw_contracts.py",
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
        "plan_exists": _path(PLAN).exists(),
        "dependency_inventory_exists": _path(DEPENDENCY_INVENTORY).exists(),
        "compatibility_matrix_exists": _path(COMPATIBILITY_MATRIX).exists(),
    }
    for field, exists in files.items():
        if not exists:
            blockers.append({"reason": "missing_required_d9_file", "field": field})
    return files


def _check_openclaw_retained(blockers: list[Json]) -> Json:
    service_exists = _path("openclaw_service").is_dir()
    frozen_exists = _path("openclaw_service/LEGACY_FROZEN.md").exists()
    legacy_archive_move_present = _path("legacy_flask/openclaw_legacy").exists()
    moved_or_deleted = [
        path
        for path in _changed_paths()
        if path.startswith("openclaw_service") or path.startswith("legacy_flask/openclaw_legacy")
    ]
    if not service_exists:
        blockers.append({"reason": "openclaw_service_missing"})
    if not frozen_exists:
        blockers.append({"reason": "openclaw_legacy_frozen_missing"})
    if legacy_archive_move_present:
        blockers.append({"reason": "openclaw_service_physical_move_detected", "path": "legacy_flask/openclaw_legacy"})
    for path in moved_or_deleted:
        if path.startswith("legacy_flask/openclaw_legacy"):
            blockers.append({"reason": "openclaw_service_physical_move_detected", "path": path})
    return {
        "openclaw_service_exists": service_exists,
        "legacy_frozen_exists": frozen_exists,
        "openclaw_service_moved": legacy_archive_move_present,
        "openclaw_changed_paths": moved_or_deleted,
    }


def _check_default_next_imports_openclaw_service(blockers: list[Json]) -> Json:
    findings: list[Json] = []
    for path in _path("aicrm_next").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if re.search(r"(^|\n)\s*(from\s+openclaw_service\b|import\s+openclaw_service\b)", source):
            finding = {"path": str(path.relative_to(PROJECT_ROOT))}
            findings.append(finding)
            blockers.append({"reason": "default_next_imports_openclaw_service", **finding})
    return {"default_next_imports_openclaw_service": bool(findings), "findings": findings}


def _check_d7_7_replacement_status(blockers: list[Json]) -> Json:
    missing = [relpath for relpath in D7_7_REQUIRED if not _path(relpath).exists()]
    for relpath in missing:
        blockers.append({"reason": "missing_d7_7_replacement_artifact", "path": relpath})
    return {"status": "present" if not missing else "missing", "missing": missing}


def _check_compatibility_matrix(blockers: list[Json]) -> Json:
    if not _path(COMPATIBILITY_MATRIX).exists():
        return {"rows": 0, "missing_capabilities": REQUIRED_CAPABILITIES, "invalid_statuses": []}
    rows = _parse_markdown_table(COMPATIBILITY_MATRIX)
    covered = {row.get("capability", "").strip("`") for row in rows}
    missing = [capability for capability in REQUIRED_CAPABILITIES if capability not in covered]
    invalid_statuses: list[Json] = []
    for row in rows:
        status = row.get("compatibility_status", "")
        if status not in ALLOWED_COMPATIBILITY_STATUSES:
            finding = {"capability": row.get("capability", ""), "compatibility_status": status}
            invalid_statuses.append(finding)
            blockers.append({"reason": "invalid_compatibility_status", **finding})
    for capability in missing:
        blockers.append({"reason": "compatibility_matrix_missing_capability", "capability": capability})
    if not rows:
        blockers.append({"reason": "compatibility_matrix_table_missing"})
    return {"rows": len(rows), "missing_capabilities": missing, "invalid_statuses": invalid_statuses}


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
    retained = _check_openclaw_retained(blockers)
    default_imports = _check_default_next_imports_openclaw_service(blockers)
    d7_7 = _check_d7_7_replacement_status(blockers)
    matrix = _check_compatibility_matrix(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "planning_only",
                "message": "D9.0 plans OpenClaw legacy retirement; it does not move or delete openclaw_service.",
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
        "openclaw_changed_paths": retained["openclaw_changed_paths"],
        "default_next_imports_openclaw_service": default_imports["default_next_imports_openclaw_service"],
        "default_next_import_findings": default_imports["findings"],
        "d7_7_replacement_status": d7_7,
        "compatibility_matrix": matrix,
        "forbidden_status_markers": forbidden,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "recommendation": (
            "READY_FOR_D9_OPENCLAW_RETIREMENT_PLANNING_ACCEPTANCE_NOT_DELETED"
            if not blockers
            else "BLOCKED_D9_OPENCLAW_RETIREMENT_PLANNING"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9 OpenClaw Legacy Retirement Readiness",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- plan_exists: {str(result['plan_exists']).lower()}",
        f"- dependency_inventory_exists: {str(result['dependency_inventory_exists']).lower()}",
        f"- compatibility_matrix_exists: {str(result['compatibility_matrix_exists']).lower()}",
        f"- openclaw_service_exists: {str(result['openclaw_service_exists']).lower()}",
        f"- legacy_frozen_exists: {str(result['legacy_frozen_exists']).lower()}",
        f"- default_next_imports_openclaw_service: {str(result['default_next_imports_openclaw_service']).lower()}",
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
    parser = argparse.ArgumentParser(description="Check D9 OpenClaw legacy adapter retirement planning readiness.")
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
