#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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

REQUIRED_ADAPTERS = [
    "CloudStorageAdapter",
    "WeComMediaAdapter",
    "WeComTagAdapter",
    "WeComMessageDispatchAdapter",
    "WeChatOAuthAdapter",
    "WeChatPayAdapter",
    "AlipayAdapter",
    "OpenClawWebhookAdapter",
    "ArchiveSyncAdapter",
    "ContactsSyncAdapter",
    "IdentityMappingAdapter",
    "AutomationRuntimeAdapter",
]

REQUIRED_BATCHES = ["D7.1", "D7.2", "D7.3", "D7.4", "D7.5", "D7.6", "D7.7"]
FORBIDDEN_STATUS_MARKERS = ["production_ready", "production_approved", "delete_ready"]
REAL_EXECUTION_CLAIMS = [
    "real external call executed",
    "real traffic cutover executed",
    "production canary executed",
    "production outbound enabled",
]


def _repo_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def parse_markdown_table(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if header is None:
            if "capability" in cells or "adapter_name" in cells or "batch" in cells:
                header = cells
            continue
        if all(set(cell) <= {"-", " "} for cell in cells):
            continue
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return rows


def _read(path: Path, blockers: list[str]) -> str:
    if not path.exists():
        blockers.append(f"missing file: {path.relative_to(REPO_ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def build_report(
    blocker_matrix: Path,
    replacement_plan: Path,
    adapter_catalog: Path,
    readiness_matrix: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    blocker_text = _read(blocker_matrix, blockers)
    plan_text = _read(replacement_plan, blockers)
    adapter_text = _read(adapter_catalog, blockers)
    readiness_text = _read(readiness_matrix, blockers)
    all_text = "\n".join([blocker_text, plan_text, adapter_text, readiness_text])

    covered_capabilities = [cap for cap in REQUIRED_CAPABILITIES if cap in blocker_text and cap in readiness_text]
    missing_capabilities = [cap for cap in REQUIRED_CAPABILITIES if cap not in blocker_text or cap not in readiness_text]
    if missing_capabilities:
        blockers.append("missing capabilities: " + ", ".join(missing_capabilities))

    covered_adapters = [adapter for adapter in REQUIRED_ADAPTERS if adapter in adapter_text]
    missing_adapters = [adapter for adapter in REQUIRED_ADAPTERS if adapter not in adapter_text]
    if missing_adapters:
        blockers.append("missing adapters: " + ", ".join(missing_adapters))

    missing_batches = [batch for batch in REQUIRED_BATCHES if batch not in plan_text]
    if missing_batches:
        blockers.append("missing D7 batches: " + ", ".join(missing_batches))

    forbidden_status_markers = [marker for marker in FORBIDDEN_STATUS_MARKERS if marker in all_text]
    if forbidden_status_markers:
        blockers.append("forbidden status markers: " + ", ".join(forbidden_status_markers))

    executed_claims = [claim for claim in REAL_EXECUTION_CLAIMS if claim in all_text.lower()]
    if executed_claims:
        blockers.append("D7 docs claim real execution: " + ", ".join(executed_claims))

    adapter_rows = parse_markdown_table(adapter_catalog) if adapter_catalog.exists() else []
    external_adapter_failures: list[str] = []
    missing_env_flags: list[str] = []
    for row in adapter_rows:
        adapter_name = row.get("adapter_name", "")
        if not adapter_name:
            continue
        if "AICRM_NEXT_ENABLE_" not in row.get("production_enable_env_flags", ""):
            missing_env_flags.append(adapter_name)
        required_fields = {
            "idempotency_key": row.get("idempotency_key", ""),
            "audit_log_required": row.get("audit_log_required", ""),
            "timeout_policy": row.get("timeout_policy", ""),
            "retry_policy": row.get("retry_policy", ""),
            "rollback_behavior": row.get("rollback_behavior", ""),
        }
        if not required_fields["idempotency_key"] or required_fields["audit_log_required"].lower() != "yes":
            external_adapter_failures.append(adapter_name)
        if not required_fields["timeout_policy"] or not required_fields["retry_policy"] or not required_fields["rollback_behavior"]:
            external_adapter_failures.append(adapter_name)

    if missing_env_flags:
        blockers.append("production env flag missing for adapters: " + ", ".join(sorted(set(missing_env_flags))))
    if external_adapter_failures:
        blockers.append("adapter safety fields incomplete: " + ", ".join(sorted(set(external_adapter_failures))))

    readiness_rows = parse_markdown_table(readiness_matrix) if readiness_matrix.exists() else []
    allowed_statuses = {
        "blocked_by_design",
        "fake_contract_ready",
        "staging_contract_ready",
        "production_contract_ready",
        "pending_human_signoff",
    }
    bad_statuses = [
        f"{row.get('capability', '')}:{row.get('current_status', '')}"
        for row in readiness_rows
        if row.get("current_status") and row.get("current_status") not in allowed_statuses
    ]
    if bad_statuses:
        blockers.append("invalid readiness statuses: " + ", ".join(bad_statuses))

    ok = not blockers
    return {
        "ok": ok,
        "blockers": blockers,
        "warnings": warnings,
        "covered_capabilities": covered_capabilities,
        "missing_capabilities": missing_capabilities,
        "covered_adapters": covered_adapters,
        "missing_adapters": missing_adapters,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": "READY_FOR_D7_PLANNING_ACCEPTANCE" if ok else "FIX_D7_PLANNING_BLOCKERS",
    }


def write_markdown(report: dict[str, Any], output_md: Path) -> None:
    lines = [
        "# D7 Replacement Planning Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    lines.extend([f"- {item}" for item in blockers] or ["- none"])
    lines.append("")
    lines.append("## Warnings")
    warnings = report.get("warnings") or []
    lines.extend([f"- {item}" for item in warnings] or ["- none"])
    for key in ("covered_capabilities", "missing_capabilities", "covered_adapters", "missing_adapters", "forbidden_status_markers"):
        lines.extend(["", f"## {key}"])
        values = report.get(key) or []
        lines.extend([f"- {item}" for item in values] or ["- none"])
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D7 replacement planning docs.")
    parser.add_argument("--blocker-matrix", required=True)
    parser.add_argument("--replacement-plan", required=True)
    parser.add_argument("--adapter-catalog", required=True)
    parser.add_argument("--readiness-matrix", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    report = build_report(
        _repo_path(args.blocker_matrix),
        _repo_path(args.replacement_plan),
        _repo_path(args.adapter_catalog),
        _repo_path(args.readiness_matrix),
    )
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
