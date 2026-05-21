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

REFERENCE_SCAN_EVIDENCE = "docs/d9_5_1_openclaw_final_reference_scan_evidence.md"
OBSERVATION_EVIDENCE = "docs/d9_5_1_openclaw_observation_evidence_report.md"
DELETION_READINESS_MATRIX = "docs/d9_5_1_openclaw_shim_deletion_readiness_evidence_matrix.md"
FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]
DOCS_TO_SCAN = [
    REFERENCE_SCAN_EVIDENCE,
    OBSERVATION_EVIDENCE,
    DELETION_READINESS_MATRIX,
    "docs/d9_5_openclaw_service_shim_removal_plan.md",
    "docs/d9_5_openclaw_final_reference_scan_plan.md",
    "docs/d9_5_openclaw_shim_removal_readiness_checklist.md",
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


def _scan_runtime_imports(root: str) -> list[Json]:
    root_path = _path(root)
    findings: list[Json] = []
    if not root_path.exists():
        return findings
    for path in root_path.rglob("*.py"):
        for item in _detect_openclaw_imports(path):
            findings.append({"path": str(path.relative_to(PROJECT_ROOT)), **item})
    return findings


def _run_rg(paths: list[str]) -> list[str]:
    existing = [path for path in paths if _path(path).exists()]
    if not existing:
        return []
    completed = subprocess.run(
        ["rg", "-n", "openclaw_service", *existing],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _check_required_files(blockers: list[Json]) -> Json:
    checks = {
        "reference_scan_evidence_exists": _path(REFERENCE_SCAN_EVIDENCE).exists(),
        "observation_evidence_exists": _path(OBSERVATION_EVIDENCE).exists(),
        "deletion_readiness_matrix_exists": _path(DELETION_READINESS_MATRIX).exists(),
    }
    for field, exists in checks.items():
        if not exists:
            blockers.append({"reason": "missing_d9_5_1_evidence_file", "field": field})
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


def _check_runtime_imports(blockers: list[Json]) -> Json:
    next_findings = _scan_runtime_imports("aicrm_next")
    experiments_findings = _scan_runtime_imports("experiments/ai_crm_next/src/aicrm_next")
    for finding in next_findings:
        blockers.append({"reason": "aicrm_next_imports_openclaw_service", **finding})
    for finding in experiments_findings:
        blockers.append({"reason": "experiments_next_imports_openclaw_service", **finding})
    return {
        "aicrm_next_imports_openclaw_service": bool(next_findings),
        "aicrm_next_import_findings": next_findings,
        "experiments_next_imports_openclaw_service": bool(experiments_findings),
        "experiments_next_import_findings": experiments_findings,
    }


def _check_deploy_or_production_dependency(blockers: list[Json]) -> Json:
    hits = _run_rg(["deploy", ".github", "scripts"])
    if hits:
        blockers.append({"reason": "deploy_or_production_dependency", "hits": hits})
    return {"deploy_or_production_dependency": bool(hits), "deploy_or_production_hits": hits}


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


def _observation_status() -> str:
    path = _path(OBSERVATION_EVIDENCE)
    if not path.exists():
        return "missing"
    text = path.read_text(encoding="utf-8")
    if "pending_observation_evidence" in text and "not_available_in_this_environment" in text:
        return "pending_observation_evidence"
    return "available"


def _deletion_candidate() -> bool:
    path = _path(DELETION_READINESS_MATRIX)
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return "Deletion PR candidate: true" in text


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    required = _check_required_files(blockers)
    retained = _check_retained_paths(blockers)
    runtime_imports = _check_runtime_imports(blockers)
    deploy_dependency = _check_deploy_or_production_dependency(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_markers = _check_forbidden_status_markers(blockers)
    observation_status = _observation_status()
    deletion_candidate = _deletion_candidate()
    if observation_status == "pending_observation_evidence":
        warnings.append(
            {
                "reason": "pending_observation_evidence",
                "message": "Reference scan is complete, but operational observation evidence is not available in this environment.",
            }
        )
    if deletion_candidate:
        blockers.append({"reason": "deletion_candidate_claimed_without_operational_evidence"})
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        **required,
        **retained,
        **runtime_imports,
        "deploy_or_production_dependency": deploy_dependency["deploy_or_production_dependency"],
        "deploy_or_production_hits": deploy_dependency["deploy_or_production_hits"],
        "observation_status": observation_status,
        "deletion_candidate": deletion_candidate,
        "production_config_modified": production_config["production_config_modified"],
        "production_config_modified_paths": production_config["modified_paths"],
        "forbidden_status_markers": forbidden_markers,
        "recommendation": (
            "READY_FOR_D9_5_1_REFERENCE_SCAN_ACCEPTANCE_PENDING_OBSERVATION"
            if not blockers and observation_status == "pending_observation_evidence"
            else (
                "READY_FOR_D9_5_1_DELETION_PR_PREP_ACCEPTANCE_NOT_DELETED"
                if not blockers
                else "BLOCKED_D9_5_1_OPENCLAW_REFERENCE_SCAN"
            )
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.5.1 OpenClaw Reference Scan",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- reference_scan_evidence_exists: {str(result['reference_scan_evidence_exists']).lower()}",
        f"- observation_evidence_exists: {str(result['observation_evidence_exists']).lower()}",
        f"- deletion_readiness_matrix_exists: {str(result['deletion_readiness_matrix_exists']).lower()}",
        f"- openclaw_service_still_exists: {str(result['openclaw_service_still_exists']).lower()}",
        f"- shim_still_exists: {str(result['shim_still_exists']).lower()}",
        f"- legacy_flask_openclaw_legacy_exists: {str(result['legacy_flask_openclaw_legacy_exists']).lower()}",
        f"- aicrm_next_imports_openclaw_service: {str(result['aicrm_next_imports_openclaw_service']).lower()}",
        f"- experiments_next_imports_openclaw_service: {str(result['experiments_next_imports_openclaw_service']).lower()}",
        f"- deploy_or_production_dependency: {str(result['deploy_or_production_dependency']).lower()}",
        f"- observation_status: {result['observation_status']}",
        f"- deletion_candidate: {str(result['deletion_candidate']).lower()}",
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
