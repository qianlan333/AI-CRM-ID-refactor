#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Json = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[1]

KNOWN_BATCHES: dict[str, Json] = {
    "media_readonly": {
        "readonly": True,
        "signoff": "docs/batch_1_media_readonly_canary_signoff.md",
        "rollback_flag": "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
    },
    "product_readonly": {
        "readonly": True,
        "signoff": "docs/batch_2_product_readonly_canary_signoff.md",
        "rollback_flag": "AICRM_NEXT_ROUTE_PRODUCT_READONLY=false",
    },
    "customer_readonly": {
        "readonly": True,
        "signoff": "docs/batch_3_customer_readonly_canary_signoff.md",
        "rollback_flag": "AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false",
    },
    "user_ops_readonly": {
        "readonly": True,
        "signoff": "docs/batch_4_user_ops_readonly_canary_signoff.md",
        "rollback_flag": "AICRM_NEXT_ROUTE_USER_OPS_READONLY=false",
    },
    "questionnaire_readonly": {
        "readonly": True,
        "signoff": "docs/batch_5_questionnaire_readonly_canary_signoff.md",
        "rollback_flag": "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false",
    },
}

ALLOWED_TRUE_SAFETY = {"default_endpoints_get_only", "fake_writes_next_testclient_only"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: str, *, label: str) -> Json:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"{label} JSON does not exist: {json_path}")
    with json_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} JSON must contain an object: {json_path}")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_pass(report: Json) -> bool:
    return report.get("ok") is True or str(report.get("overall", "")).upper() == "PASS"


def _status(report: Json) -> str:
    if _is_pass(report):
        return "PASS"
    if report.get("ok") is False or str(report.get("overall", "")).upper() == "FAIL":
        return "FAIL"
    return "UNKNOWN"


def _side_effect_safety(*reports: Json) -> Json:
    safety: Json = {}
    for report in reports:
        source = report.get("side_effect_safety")
        if isinstance(source, dict):
            safety.update(source)
    return safety


def _safety_violations(safety: Json) -> list[Json]:
    violations: list[Json] = []
    for key, value in sorted(safety.items()):
        if value is True and key not in ALLOWED_TRUE_SAFETY:
            violations.append({"reason": "side_effect_safety_violation", "field": key})
    for required in ("production_config_modified", "real_traffic_cutover_executed"):
        if safety.get(required) is True:
            violations.append({"reason": "production_action_detected", "field": required})
    return violations


def _approval_package_check(path: Path, batch: str) -> Json:
    if not path.exists():
        return {"ok": False, "reason": "approval_package_missing", "path": str(path)}
    text = path.read_text(encoding="utf-8")
    required = [
        "not a production cutover",
        "pending_human_signoff",
        "Batch 1",
        "Batch 2",
        "Batch 3",
        "Batch 4",
        "Batch 5",
        "Batch 1 Media readonly",
    ]
    missing = [item for item in required if item not in text]
    batch_name_missing = batch not in text
    forbidden = []
    for marker in ("production_approved", "approved_for_production: true"):
        if marker in text:
            forbidden.append(marker)
    return {
        "ok": not missing and not batch_name_missing and not forbidden,
        "path": str(path),
        "missing": missing + ([batch] if batch_name_missing else []),
        "forbidden": forbidden,
    }


def _rollback_check(readiness: Json, rollback_flag: str) -> Json:
    rollback = readiness.get("rollback_dry_run")
    if isinstance(rollback, dict) and rollback.get("route_flag_rollback_instruction") == rollback_flag:
        return {"ok": True, "source": "readiness_json", "rollback_flag": rollback_flag}
    text = json.dumps(readiness, ensure_ascii=False)
    if rollback_flag in text:
        return {"ok": True, "source": "readiness_json_text", "rollback_flag": rollback_flag}
    return {"ok": False, "reason": "rollback_instruction_missing", "rollback_flag": rollback_flag}


def _signoff_check(signoff_path: Path | None) -> Json:
    if signoff_path is None:
        return {"ok": False, "reason": "signoff_template_missing", "path": ""}
    if not signoff_path.exists():
        return {"ok": False, "reason": "signoff_template_missing", "path": str(signoff_path)}
    text = signoff_path.read_text(encoding="utf-8")
    has_pending = "staging_simulated_only" in text or "pending" in text
    forbidden = "production_approved" in text
    return {"ok": has_pending and not forbidden, "path": str(signoff_path), "forbidden": forbidden}


def build_report(args: argparse.Namespace) -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []

    batch_meta = KNOWN_BATCHES.get(args.batch)
    if not batch_meta:
        blockers.append({"reason": "unknown_batch", "batch": args.batch, "known_batches": sorted(KNOWN_BATCHES)})
        batch_meta = {"readonly": False, "signoff": "", "rollback_flag": ""}
    elif not batch_meta["readonly"]:
        blockers.append({"reason": "target_batch_not_readonly", "batch": args.batch})

    approval_package_path = Path(args.approval_package)
    package_check = _approval_package_check(approval_package_path, args.batch)
    if not package_check["ok"]:
        blockers.append({"reason": "approval_package_not_ready", "result": package_check})

    readiness = _load_json(args.batch_readiness_json, label="batch readiness")
    smoke = _load_json(args.smoke_json, label="smoke")
    parity = _load_json(args.parity_json, label="parity")

    if not _is_pass(readiness):
        blockers.append({"reason": "readiness_not_pass", "source": args.batch_readiness_json})
    if _as_list(readiness.get("blockers")):
        blockers.append({"reason": "readiness_has_blockers", "items": readiness.get("blockers")})
    if not _is_pass(smoke):
        blockers.append({"reason": "smoke_not_pass", "source": args.smoke_json})
    if _as_list(smoke.get("blockers")):
        blockers.append({"reason": "smoke_has_blockers", "items": smoke.get("blockers")})
    if not _is_pass(parity):
        blockers.append({"reason": "parity_not_pass", "source": args.parity_json})
    if _as_list(parity.get("blockers")):
        blockers.append({"reason": "parity_has_blockers", "items": parity.get("blockers")})

    safety = _side_effect_safety(readiness, smoke, parity)
    safety.setdefault("production_config_modified", False)
    safety.setdefault("real_traffic_cutover_executed", False)
    blockers.extend(_safety_violations(safety))

    rollback = _rollback_check(readiness, str(batch_meta.get("rollback_flag") or ""))
    if not rollback["ok"]:
        blockers.append({"reason": "rollback_instruction_missing", "result": rollback})

    signoff_name = str(batch_meta.get("signoff") or "")
    signoff_path = PROJECT_ROOT / signoff_name if signoff_name else None
    signoff = _signoff_check(signoff_path)
    if not signoff["ok"]:
        blockers.append({"reason": "signoff_template_not_ready", "result": signoff})

    approval_status = "pending_human_signoff"
    recommended_next_action = "REQUEST_HUMAN_SIGNOFF_FOR_BATCH_1_MEDIA_READONLY" if not blockers else "NO_GO_FIX_BLOCKERS"
    if args.batch != "media_readonly" and not blockers:
        warnings.append({"reason": "recommended_first_batch_is_media_readonly", "requested_batch": args.batch})
        recommended_next_action = "REVIEW_BATCH_ORDER_BEFORE_HUMAN_SIGNOFF"

    return {
        "ok": not blockers,
        "batch": args.batch,
        "generated_at": _utc_now(),
        "approval_status": approval_status,
        "recommended_next_action": recommended_next_action,
        "source_reports": {
            "approval_package": args.approval_package,
            "batch_readiness_json": args.batch_readiness_json,
            "smoke_json": args.smoke_json,
            "parity_json": args.parity_json,
        },
        "source_status": {
            "readiness": _status(readiness),
            "smoke": _status(smoke),
            "parity": _status(parity),
        },
        "blockers": blockers,
        "warnings": warnings,
        "side_effect_safety": safety,
        "approval_package_check": package_check,
        "rollback_check": rollback,
        "signoff_check": signoff,
    }


def write_json(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Production Canary Approval Readiness Report",
        "",
        f"- batch: `{report['batch']}`",
        f"- ok: `{report['ok']}`",
        f"- approval_status: `{report['approval_status']}`",
        f"- recommended_next_action: `{report['recommended_next_action']}`",
        f"- generated_at: `{report['generated_at']}`",
        "",
        "## Source Status",
        "",
    ]
    for key, value in report["source_status"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- `{item.get('reason')}`: {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- `{item.get('reason')}`: {item}" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Side Effect Safety", ""])
    for key, value in sorted(report["side_effect_safety"].items()):
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Approval Boundary", ""])
    lines.append("- This checker never returns production approval.")
    lines.append("- Passing status means the package can go to human review.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check production canary approval package readiness.")
    parser.add_argument("--approval-package", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--batch-readiness-json", required=True)
    parser.add_argument("--smoke-json", required=True)
    parser.add_argument("--parity-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_markdown(report, Path(args.output_md))
    write_json(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("approval_status:", report["approval_status"])
    print("recommended_next_action:", report["recommended_next_action"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
