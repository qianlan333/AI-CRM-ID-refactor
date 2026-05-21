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

REPORT = "docs/d9_6_openclaw_physical_deletion_report.md"


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


def _is_forbidden_local_prod_config_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("deploy/")
        or lowered == ".github/workflows/deploy.yml"
        or "nginx" in lowered
        or lowered.endswith(".service")
        or lowered.endswith(".timer")
    )


def _detect_openclaw_imports(path: Path) -> list[Json]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    findings: list[Json] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "openclaw_service" or alias.name.startswith("openclaw_service."):
                    findings.append({"line": node.lineno, "pattern": "import", "module": alias.name})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "openclaw_service" or module.startswith("openclaw_service."):
                findings.append({"line": node.lineno, "pattern": "from", "module": module})
    return findings


def _scan_next_imports() -> list[Json]:
    findings: list[Json] = []
    for root in ["aicrm_next", "experiments/ai_crm_next/src/aicrm_next"]:
        root_path = _path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            for item in _detect_openclaw_imports(path):
                findings.append({"path": str(path.relative_to(PROJECT_ROOT)), **item})
    return findings


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    report_exists = _path(REPORT).exists()
    openclaw_service_exists = _path("openclaw_service").exists()
    archive_exists = _path("legacy_flask/openclaw_legacy").exists()
    next_imports = _scan_next_imports()
    prod_config_modified = [
        path for path in _changed_paths() if _is_forbidden_local_prod_config_path(path)
    ]

    if not report_exists:
        blockers.append({"reason": "missing_deletion_report", "path": REPORT})
    if openclaw_service_exists:
        blockers.append({"reason": "openclaw_service_still_exists"})
    if archive_exists:
        blockers.append({"reason": "legacy_flask_openclaw_legacy_still_exists"})
    for finding in next_imports:
        blockers.append({"reason": "next_imports_deleted_openclaw_service", **finding})
    if prod_config_modified:
        blockers.append({"reason": "local_production_config_modified", "paths": prod_config_modified})
    if not blockers:
        warnings.append(
            {
                "reason": "server_changes_outside_git",
                "message": "Server-side cron/systemd removals are recorded in the report and backed up on the server.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "report_exists": report_exists,
        "openclaw_service_exists": openclaw_service_exists,
        "legacy_flask_openclaw_legacy_exists": archive_exists,
        "aicrm_next_imports_openclaw_service": bool(next_imports),
        "aicrm_next_import_findings": next_imports,
        "local_production_config_modified": bool(prod_config_modified),
        "local_production_config_modified_paths": prod_config_modified,
        "recommendation": (
            "OPENCLAW_SHIM_PHYSICAL_DELETION_RECORDED"
            if not blockers
            else "BLOCKED_OPENCLAW_SHIM_PHYSICAL_DELETION"
        ),
    }


def _write_markdown(path: Path, result: Json) -> None:
    lines = [
        "# D9.6 OpenClaw Physical Deletion Check",
        "",
        f"- ok: {str(result['ok']).lower()}",
        f"- recommendation: {result['recommendation']}",
        f"- report_exists: {str(result['report_exists']).lower()}",
        f"- openclaw_service_exists: {str(result['openclaw_service_exists']).lower()}",
        f"- legacy_flask_openclaw_legacy_exists: {str(result['legacy_flask_openclaw_legacy_exists']).lower()}",
        f"- aicrm_next_imports_openclaw_service: {str(result['aicrm_next_imports_openclaw_service']).lower()}",
        f"- local_production_config_modified: {str(result['local_production_config_modified']).lower()}",
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
