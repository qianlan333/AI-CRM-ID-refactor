#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_CAPABILITIES = [
    "User Ops DND",
    "User Ops batch-send preview",
    "User Ops batch-send execute",
    "User Ops deferred jobs",
    "Questionnaire admin write",
    "Questionnaire submit",
    "Questionnaire OAuth",
    "Questionnaire WeCom tag / external push",
    "Product admin write",
    "WeChat Pay checkout / notify",
    "Alipay checkout / notify / return",
    "Media cloud storage upload",
    "WeCom media upload",
    "Customer archive sync",
    "Contacts sync",
    "Identity mapping",
    "Automation manual override",
    "Automation confirm conversion",
    "Automation activation webhook",
    "Automation OpenClaw push",
    "Automation workflow runtime",
    "Automation agent runtime",
    "MCP / OpenClaw legacy adapter",
]

PROTECTED_FILES = [
    "app.py",
    "legacy_flask_app.py",
    "wecom_ability_service/__init__.py",
    "wecom_ability_service/routes.py",
    "wecom_ability_service/http/__init__.py",
    "openclaw_service/LEGACY_FROZEN.md",
    "wecom_ability_service/http/wechat_pay.py",
    "wecom_ability_service/http/alipay_pay.py",
    "wecom_ability_service/http/admin_wechat_pay.py",
    "wecom_ability_service/http/admin_alipay_pay.py",
    "wecom_ability_service/http/public_questionnaire_oauth.py",
    "wecom_ability_service/http/public_questionnaires.py",
    "wecom_ability_service/http/admin_questionnaires.py",
    "wecom_ability_service/http/admin_questionnaire_push_logs.py",
    "wecom_ability_service/http/customer_automation.py",
    "wecom_ability_service/http/automation_conversion.py",
    "wecom_ability_service/http/automation_conversion_runtime_api.py",
    "wecom_ability_service/http/automation_conversion_agent_api.py",
    "wecom_ability_service/http/automation_conversion_operation_tasks.py",
    "wecom_ability_service/http/archive.py",
    "wecom_ability_service/http/contacts.py",
    "wecom_ability_service/http/identity.py",
]

PRODUCTION_PATH_PREFIXES = ("deploy/", "production/", "nginx/", "systemd/", "supervisor/")
PRODUCTION_NAME_MARKERS = ("nginx", "systemd", "supervisor", "production")
VALID_DECISIONS = {"delete", "keep", "tombstone", "needs_manual_review"}


def _repo_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def parse_markdown_table(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if header is None:
            if "file_or_directory" in cells or "capability" in cells:
                header = cells
            continue
        if all(set(cell) <= {"-", " "} for cell in cells):
            continue
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _git_changed_paths() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        paths.append(raw)
    return paths


def _production_config_modified(paths: list[str]) -> bool:
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized.startswith(PRODUCTION_PATH_PREFIXES):
            return True
        name = Path(normalized).name.lower()
        if any(marker in name for marker in PRODUCTION_NAME_MARKERS):
            return True
    return False


def _registrar_source() -> str:
    registrar = REPO_ROOT / "wecom_ability_service" / "http" / "__init__.py"
    return registrar.read_text(encoding="utf-8") if registrar.exists() else ""


def _has_tombstone_marker(path: Path) -> bool:
    if not path.exists() or path.is_dir():
        marker = path / "LEGACY_DEPENDENCY_FALLBACK.md"
        if marker.exists():
            return True
        return False
    source = path.read_text(encoding="utf-8", errors="ignore").lower()
    return any(marker in source for marker in ("tombstone", "frozen", "retired", "fallback"))


def build_report(inventory: Path, blocker_matrix: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    deleted_files_verified: list[str] = []
    kept_files_verified: list[str] = []
    tombstone_files_verified: list[str] = []
    stale_imports: list[str] = []
    protected_files_missing: list[str] = []

    if not inventory.exists():
        blockers.append(f"missing inventory: {inventory}")
        inventory_rows: list[dict[str, str]] = []
    else:
        inventory_rows = parse_markdown_table(inventory)
        if not inventory_rows:
            blockers.append("inventory has no parseable rows")

    registrar_source = _registrar_source()
    for row in inventory_rows:
        rel = row.get("file_or_directory", "")
        decision = row.get("decision", "")
        reason = row.get("reason", "")
        scan_evidence = row.get("scan_evidence", "")
        batch = row.get("retirement_batch", "")
        dependency = row.get("write_external_runtime_dependency", "").lower()
        if decision not in VALID_DECISIONS:
            blockers.append(f"{rel}: invalid decision {decision!r}")
            continue
        if not batch:
            blockers.append(f"{rel}: missing retirement_batch")
        if not reason:
            blockers.append(f"{rel}: missing reason")
        if decision == "delete" and not scan_evidence:
            blockers.append(f"{rel}: delete row missing scan_evidence")
        if decision == "delete" and dependency not in {"no", "none", "false"}:
            blockers.append(f"{rel}: write/external/runtime dependency cannot be delete")

        path = _repo_path(rel)
        if decision == "delete":
            if path.exists():
                blockers.append(f"{rel}: decision=delete but file still exists")
            else:
                deleted_files_verified.append(rel)
            token = Path(rel).stem
            basename = Path(rel).name
            if rel in registrar_source or token in registrar_source or basename in registrar_source:
                stale_imports.append(rel)
        elif decision == "keep":
            if not path.exists():
                blockers.append(f"{rel}: decision=keep but file is missing")
            else:
                kept_files_verified.append(rel)
        elif decision == "tombstone":
            if not path.exists():
                blockers.append(f"{rel}: decision=tombstone but file is missing")
            elif not _has_tombstone_marker(path):
                blockers.append(f"{rel}: tombstone marker not found")
            else:
                tombstone_files_verified.append(rel)
        elif decision == "needs_manual_review":
            if not path.exists():
                warnings.append(f"{rel}: manual-review target missing")

    for rel in PROTECTED_FILES:
        if not _repo_path(rel).exists():
            protected_files_missing.append(rel)
    if protected_files_missing:
        blockers.extend(f"protected file missing: {rel}" for rel in protected_files_missing)

    if not blocker_matrix.exists():
        blockers.append(f"missing blocker matrix: {blocker_matrix}")
        d7_blockers_verified = False
    else:
        matrix_text = blocker_matrix.read_text(encoding="utf-8")
        matrix_rows = parse_markdown_table(blocker_matrix)
        missing_caps = [cap for cap in REQUIRED_CAPABILITIES if cap not in matrix_text]
        forbidden = [
            marker
            for marker in ("delete_ready", "production_ready", "production_approved")
            if marker in matrix_text
        ]
        empty_blockers = [
            row.get("capability", "")
            for row in matrix_rows
            if row.get("capability")
            and (
                not row.get("delete_blocker")
                or not row.get("required_replacement_work")
                or not row.get("required_production_evidence")
            )
        ]
        if missing_caps:
            blockers.append("D7 matrix missing capabilities: " + ", ".join(missing_caps))
        if forbidden:
            blockers.append("D7 matrix contains forbidden marker(s): " + ", ".join(forbidden))
        if empty_blockers:
            blockers.append("D7 matrix rows missing required blocker fields: " + ", ".join(empty_blockers))
        d7_blockers_verified = not missing_caps and not forbidden and not empty_blockers

    changed_paths = _git_changed_paths()
    production_config_modified = _production_config_modified(changed_paths)
    if production_config_modified:
        blockers.append("production/deploy/nginx/systemd config modified")

    ok = not blockers and not stale_imports
    return {
        "ok": ok,
        "blockers": blockers,
        "warnings": warnings,
        "deleted_files_verified": deleted_files_verified,
        "kept_files_verified": kept_files_verified,
        "tombstone_files_verified": tombstone_files_verified,
        "stale_imports": stale_imports,
        "protected_files_missing": protected_files_missing,
        "d7_blockers_verified": d7_blockers_verified,
        "production_config_modified": production_config_modified,
        "recommendation": "READY_FOR_D6_5_DEAD_CLEANUP_ACCEPTANCE" if ok else "FIX_D6_5_DEAD_CLEANUP_BLOCKERS",
    }


def write_markdown(report: dict[str, Any], output_md: Path) -> None:
    lines = [
        "# Legacy D6.5 Dead Cleanup Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- production_config_modified: `{str(report['production_config_modified']).lower()}`",
        f"- d7_blockers_verified: `{str(report['d7_blockers_verified']).lower()}`",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    lines.extend([f"- {item}" for item in blockers] or ["- none"])
    lines.append("")
    lines.append("## Warnings")
    warnings = report.get("warnings") or []
    lines.extend([f"- {item}" for item in warnings] or ["- none"])
    for key in (
        "deleted_files_verified",
        "kept_files_verified",
        "tombstone_files_verified",
        "stale_imports",
        "protected_files_missing",
    ):
        lines.extend(["", f"## {key}"])
        values = report.get(key) or []
        lines.extend([f"- {item}" for item in values] or ["- none"])
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D6.5 dead legacy cleanup evidence.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--blocker-matrix", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    report = build_report(_repo_path(args.inventory), _repo_path(args.blocker_matrix))
    output_md = Path(args.output_md)
    output_json = Path(args.output_json)
    write_markdown(report, output_md)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote markdown report: {output_md}")
    print(f"wrote json report: {output_json}")
    print(f"overall: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
