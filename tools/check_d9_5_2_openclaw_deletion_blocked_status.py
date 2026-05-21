#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

SUMMARY = "docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md"
RUNBOOK = "docs/d9_5_2_openclaw_observation_collection_runbook.md"
PREFLIGHT = "docs/d9_5_2_openclaw_deletion_pr_preflight_checklist.md"
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
DOCS_TO_SCAN = [
    SUMMARY,
    RUNBOOK,
    PREFLIGHT,
    "docs/d9_5_openclaw_service_shim_removal_plan.md",
    "docs/d9_5_1_openclaw_shim_deletion_readiness_evidence_matrix.md",
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
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
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


def _scan_aicrm_next_imports() -> list[Json]:
    findings: list[Json] = []
    root = _path("aicrm_next")
    if not root.exists():
        return findings
    for path in root.rglob("*.py"):
        for item in _detect_openclaw_imports(path):
            findings.append({"path": str(path.relative_to(PROJECT_ROOT)), **item})
    return findings


def _check_required_files(blockers: list[Json]) -> Json:
    checks = {
        "summary_exists": _path(SUMMARY).exists(),
        "runbook_exists": _path(RUNBOOK).exists(),
        "preflight_checklist_exists": _path(PREFLIGHT).exists(),
    }
    for field, exists in checks.items():
        if not exists:
            blockers.append({"reason": "missing_d9_5_2_file", "field": field})
    return checks


def _check_retained_paths(blockers: list[Json]) -> Json:
    service_exists = _path("openclaw_service").is_dir()
    shim_exists = _path("openclaw_service/__init__.py").exists()
    archive_exists = _path("legacy_flask/openclaw_legacy").is_dir()
    if not service_exists:
        blockers.append({"reason": "openclaw_service_missing"})
    if not shim_exists:
        blockers.append({"reason": "openclaw_service_shim_missing", "path": "openclaw_service/__init__.py"})
    if not archive_exists:
        blockers.append({"reason": "legacy_flask_openclaw_legacy_missing"})
    return {
        "openclaw_service_still_exists": service_exists,
        "shim_still_exists": shim_exists,
        "legacy_flask_openclaw_legacy_exists": archive_exists,
    }


def _check_summary_state(blockers: list[Json]) -> Json:
    path = _path(SUMMARY)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    deletion_candidate = "Deletion candidate: false" in text
    observation_pending = "missing real observation window and production evidence" in text
    if not deletion_candidate:
        blockers.append({"reason": "summary_does_not_state_deletion_candidate_false"})
    if not observation_pending:
        blockers.append({"reason": "summary_does_not_state_observation_pending"})
    return {
        "deletion_candidate": False if deletion_candidate else None,
        "observation_status": "pending_observation_evidence" if observation_pending else "missing",
    }


def _check_aicrm_next_imports(blockers: list[Json]) -> Json:
    findings = _scan_aicrm_next_imports()
    for finding in findings:
        blockers.append({"reason": "aicrm_next_imports_openclaw_service", **finding})
    return {
        "aicrm_next_imports_openclaw_service": bool(findings),
        "aicrm_next_import_findings": findings,
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
    summary_state = _check_summary_state(blockers)
    imports = _check_aicrm_next_imports(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "deletion_blocked_by_observation_evidence",
                "message": "Repository gates are green, but deletion remains blocked until real observation evidence and signoff exist.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        **required,
        **retained,
        **summary_state,
        **imports,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_TO_PAUSE_FOR_OBSERVATION_EVIDENCE_NOT_DELETE"
            if not blockers
            else "BLOCKED_D9_5_2_DELETION_BLOCKED_STATUS"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.5.2 OpenClaw Deletion Blocked Status",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- summary_exists: {str(result['summary_exists']).lower()}",
        f"- runbook_exists: {str(result['runbook_exists']).lower()}",
        f"- preflight_checklist_exists: {str(result['preflight_checklist_exists']).lower()}",
        f"- openclaw_service_still_exists: {str(result['openclaw_service_still_exists']).lower()}",
        f"- shim_still_exists: {str(result['shim_still_exists']).lower()}",
        f"- legacy_flask_openclaw_legacy_exists: {str(result['legacy_flask_openclaw_legacy_exists']).lower()}",
        f"- deletion_candidate: {str(result['deletion_candidate']).lower()}",
        f"- observation_status: {result['observation_status']}",
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_check()
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        _write_markdown(Path(args.output_md), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
