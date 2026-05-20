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

REQUIRED_SMOKE_ROUTE_NAMES = {
    "admin_user_ops_page",
    "overview.default",
    "list.default",
    "list.wecom_added",
    "list.not_added",
    "list.mobile_bound",
    "list.activation_activated",
    "send_records.default",
}

REQUIRED_DUAL_ENDPOINTS = {
    "overview.default",
    "list.default",
    "list.wecom_added",
    "list.not_added",
    "list.mobile_bound",
    "list.activated",
    "send_records.default",
}

REQUIRED_SCREENSHOT_ROUTES = {"/admin/user-ops/ui"}

FALSE_SAFETY_FIELDS = {
    "old_write_endpoints_executed",
    "old_service_write_endpoints_executed",
    "wecom_dispatch_executed",
    "media_upload_executed",
    "deferred_jobs_executed",
    "production_config_modified",
    "real_traffic_cutover_executed",
}

FORBIDDEN_ROUTE_FRAGMENTS = {
    "/do-not-disturb",
    "/batch-send/preview",
    "/batch-send/execute",
    "/run-deferred-jobs",
    "/api/internal/user-ops",
}

REQUIRED_OVERVIEW_CARD = "激活待录入"


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


def _safety_from_reports(*reports: Json) -> Json:
    safety: Json = {}
    for report in reports:
        source = report.get("side_effect_safety")
        if isinstance(source, dict):
            safety.update(source)
    return safety


def _smoke_route_names(report: Json) -> set[str]:
    return {
        item.get("name")
        for item in _as_list(report.get("route_results"))
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _dual_endpoint_map(report: Json) -> dict[str, Json]:
    return {
        str(item.get("endpoint")): item
        for item in _as_list(report.get("endpoint_results"))
        if isinstance(item, dict) and isinstance(item.get("endpoint"), str)
    }


def _non_get_routes(*reports: Json) -> list[Json]:
    findings: list[Json] = []
    for report in reports:
        for collection_name in ("route_results", "endpoint_results"):
            for item in _as_list(report.get(collection_name)):
                if not isinstance(item, dict):
                    continue
                if item.get("method") != "GET":
                    findings.append(
                        {
                            "name": item.get("name") or item.get("endpoint"),
                            "method": item.get("method"),
                            "path": item.get("path"),
                        }
                    )
    return findings


def _forbidden_routes(*reports: Json) -> list[Json]:
    findings: list[Json] = []
    for report in reports:
        for collection_name in ("route_results", "endpoint_results"):
            for item in _as_list(report.get(collection_name)):
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "")
                matched = sorted(fragment for fragment in FORBIDDEN_ROUTE_FRAGMENTS if fragment in path)
                if matched:
                    findings.append({"name": item.get("name") or item.get("endpoint"), "path": path, "matched": matched})
    return findings


def _overview_item(report: Json) -> Json | None:
    for item in _as_list(report.get("route_results")):
        if isinstance(item, dict) and item.get("name") == "overview.default":
            return item
    return None


def _next_missing_activation_card(report: Json) -> bool:
    overview = _overview_item(report)
    if not overview:
        return True
    if overview.get("status") == "FAIL":
        for issue in _as_list(overview.get("issues")):
            if not isinstance(issue, dict):
                continue
            if issue.get("side") == "next" and (
                issue.get("label") == REQUIRED_OVERVIEW_CARD
                or issue.get("field") == REQUIRED_OVERVIEW_CARD
                or issue.get("key") == REQUIRED_OVERVIEW_CARD
            ):
                return True
        return True
    for issue in _as_list(overview.get("issues")):
        if isinstance(issue, dict) and issue.get("side") == "next" and issue.get("label") == REQUIRED_OVERVIEW_CARD:
            return True
    return False


def _accepted_legacy_drift(*reports: Json) -> list[Json]:
    accepted: list[Json] = []
    for report in reports:
        for item in _as_list(report.get("legacy_drift")):
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or item.get("label") or "")
            if field == REQUIRED_OVERVIEW_CARD and item.get("next_satisfies_contract") is True:
                accepted.append(item)
    return accepted


def _unexpected_warnings(readonly_dual: Json) -> list[Json]:
    unexpected: list[Json] = []
    for item in _as_list(readonly_dual.get("warnings")):
        if not isinstance(item, dict):
            continue
        issues = _as_list(item.get("issues"))
        if not issues:
            unexpected.append(item)
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                unexpected.append(item)
                continue
            reason = str(issue.get("reason") or issue.get("rule") or "")
            next_ok = issue.get("next_satisfies_contract") is True
            field = str(issue.get("field") or issue.get("label") or "")
            if not (reason.startswith("legacy_") and next_ok and field == REQUIRED_OVERVIEW_CARD):
                unexpected.append(item)
    return unexpected


def _check_screenshot_baseline(path: str) -> Json:
    route_status_path = Path(path)
    if not route_status_path.exists():
        return {"ok": False, "reason": "screenshot_route_status_missing", "path": str(route_status_path)}
    payload = _load_json(str(route_status_path), label="screenshot route_status")
    route_results = payload.get("route_results")
    if not isinstance(route_results, list):
        return {"ok": False, "reason": "route_results_missing", "path": str(route_status_path)}
    indexed = {item.get("route"): item for item in route_results if isinstance(item, dict)}
    missing = sorted(route for route in REQUIRED_SCREENSHOT_ROUTES if route not in indexed)
    failed = sorted(route for route in REQUIRED_SCREENSHOT_ROUTES if route in indexed and not indexed[route].get("ok"))
    return {
        "ok": not missing and not failed,
        "path": str(route_status_path),
        "required_routes": sorted(REQUIRED_SCREENSHOT_ROUTES),
        "missing_routes": missing,
        "failed_routes": failed,
        "summary": payload.get("summary", {}),
    }


def _check_real_pg_evidence(path: str) -> Json:
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {"ok": False, "reason": "real_pg_evidence_missing", "path": str(evidence_path)}
    text = evidence_path.read_text(encoding="utf-8")
    has_pass = "passed" in text.lower() or "PASS" in text
    return {"ok": has_pass, "path": str(evidence_path), "reason": "" if has_pass else "real_pg_pass_marker_missing"}


def _check_route_flags_doc(path: str) -> Json:
    doc_path = Path(path)
    if not doc_path.exists():
        return {"ok": False, "reason": "route_flags_doc_missing", "path": str(doc_path)}
    text = doc_path.read_text(encoding="utf-8")
    required = [
        "AICRM_NEXT_ROUTE_USER_OPS_READONLY=true",
        "AICRM_NEXT_ROUTE_USER_OPS_WRITES=false",
        "AICRM_NEXT_USER_OPS_DND=false",
        "AICRM_NEXT_USER_OPS_BATCH_SEND=false",
        "AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false",
        "AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false",
        "AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false",
        "AICRM_NEXT_ROUTE_USER_OPS_READONLY=false",
    ]
    missing = [item for item in required if item not in text]
    return {"ok": not missing, "path": str(doc_path), "missing": missing}


def build_readiness_report(args: argparse.Namespace) -> Json:
    user_ops_smoke = _load_json(args.user_ops_smoke_json, label="user ops smoke")
    user_ops_parity = _load_json(args.user_ops_parity_json, label="user ops parity")
    readonly_dual = _load_json(args.readonly_dual_json, label="readonly dual-run")
    screenshot = _check_screenshot_baseline(args.route_status_json)
    real_pg = _check_real_pg_evidence(args.real_pg_evidence)
    route_flags = _check_route_flags_doc(args.route_flags_doc)

    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_evidence: list[Json] = []

    if not _is_pass(user_ops_smoke):
        blockers.append({"reason": "user_ops_smoke_not_pass", "source": args.user_ops_smoke_json})
    if _as_list(user_ops_smoke.get("blockers")):
        blockers.append({"reason": "user_ops_smoke_has_blockers", "items": user_ops_smoke.get("blockers")})
    if not _is_pass(user_ops_parity):
        blockers.append({"reason": "user_ops_parity_not_pass", "source": args.user_ops_parity_json})
    if _as_list(user_ops_parity.get("blockers")):
        blockers.append({"reason": "user_ops_parity_has_blockers", "items": user_ops_parity.get("blockers")})
    if not _is_pass(readonly_dual):
        blockers.append({"reason": "readonly_dual_run_not_pass", "source": args.readonly_dual_json})
    if _as_list(readonly_dual.get("blockers")):
        blockers.append({"reason": "readonly_dual_run_has_blockers", "items": readonly_dual.get("blockers")})

    missing_smoke_routes = sorted(REQUIRED_SMOKE_ROUTE_NAMES - _smoke_route_names(user_ops_smoke))
    if missing_smoke_routes:
        blockers.append({"reason": "missing_required_smoke_routes", "routes": missing_smoke_routes})

    dual_by_endpoint = _dual_endpoint_map(readonly_dual)
    missing_dual = sorted(REQUIRED_DUAL_ENDPOINTS - set(dual_by_endpoint))
    if missing_dual:
        blockers.append({"reason": "missing_required_dual_endpoints", "endpoints": missing_dual})
    for endpoint in sorted(REQUIRED_DUAL_ENDPOINTS):
        item = dual_by_endpoint.get(endpoint)
        if not item:
            continue
        if item.get("status") == "SKIPPED":
            blockers.append({"reason": "required_dual_endpoint_skipped", "endpoint": endpoint, "detail": item.get("reason")})
        if item.get("status") == "FAIL":
            blockers.append({"reason": "required_dual_endpoint_failed", "endpoint": endpoint, "issues": item.get("issues", [])})

    if _next_missing_activation_card(user_ops_smoke):
        blockers.append({"reason": "next_missing_activation_pending_card", "field": REQUIRED_OVERVIEW_CARD})

    unexpected_warnings = _unexpected_warnings(readonly_dual)
    if unexpected_warnings:
        warnings.append({"reason": "readonly_dual_run_has_non_legacy_warnings", "items": unexpected_warnings})

    non_get = _non_get_routes(user_ops_smoke, readonly_dual)
    if non_get:
        blockers.append({"reason": "non_get_route_in_user_ops_canary", "routes": non_get})
    forbidden_routes = _forbidden_routes(user_ops_smoke, readonly_dual)
    if forbidden_routes:
        blockers.append({"reason": "forbidden_user_ops_route_in_canary", "routes": forbidden_routes})

    safety = _safety_from_reports(user_ops_smoke, readonly_dual)
    safety.setdefault("production_config_modified", False)
    safety.setdefault("real_traffic_cutover_executed", False)
    safety.setdefault("old_service_write_endpoints_executed", False)
    for field in sorted(FALSE_SAFETY_FIELDS):
        if safety.get(field) is True:
            blockers.append({"reason": "side_effect_safety_violation", "field": field})
        elif field not in safety:
            warnings.append({"reason": "side_effect_safety_field_missing", "field": field})
    if safety.get("default_endpoints_get_only") is not True:
        blockers.append({"reason": "default_endpoints_not_get_only"})

    if not screenshot["ok"]:
        blockers.append({"reason": "screenshot_baseline_not_ready", "result": screenshot})
    if not real_pg["ok"]:
        blockers.append({"reason": "real_pg_evidence_not_ready", "result": real_pg})
    if not route_flags["ok"]:
        blockers.append({"reason": "route_flags_not_ready", "result": route_flags})

    for label, path in {
        "user_ops_smoke_json": args.user_ops_smoke_json,
        "user_ops_parity_json": args.user_ops_parity_json,
        "readonly_dual_json": args.readonly_dual_json,
    }.items():
        if not Path(path).exists():
            missing_evidence.append({"reason": label + "_missing", "path": path})

    rollback = {
        "route_flag_rollback_instruction": "AICRM_NEXT_ROUTE_USER_OPS_READONLY=false",
        "expected_owner_after_rollback": "old Flask",
        "rollback_verified": "dry-run only",
        "production_config_modified": False,
    }
    legacy_drift = _accepted_legacy_drift(user_ops_smoke, readonly_dual)

    readiness_status = "canary_plan_ready" if not blockers else "not_ready"
    return {
        "ok": not blockers,
        "run_time": _utc_now(),
        "readiness_status": readiness_status,
        "recommendation": "GO_TO_STAGING_CANARY_SIGNOFF" if not blockers else "NO_GO",
        "source_reports": {
            "user_ops_smoke_json": args.user_ops_smoke_json,
            "user_ops_parity_json": args.user_ops_parity_json,
            "readonly_dual_json": args.readonly_dual_json,
            "route_status_json": args.route_status_json,
            "real_pg_evidence": args.real_pg_evidence,
            "route_flags_doc": args.route_flags_doc,
        },
        "required_smoke_route_names": sorted(REQUIRED_SMOKE_ROUTE_NAMES),
        "required_dual_endpoints": sorted(REQUIRED_DUAL_ENDPOINTS),
        "legacy_drift": legacy_drift,
        "side_effect_safety": safety,
        "rollback_dry_run": rollback,
        "screenshot_baseline": screenshot,
        "real_pg_evidence": real_pg,
        "route_flags": route_flags,
        "blockers": blockers,
        "warnings": warnings,
        "missing_evidence": missing_evidence,
    }


def write_json_report(report: Json, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Batch 4 User Ops Canary Readiness Report",
        "",
        f"- run_time: `{report['run_time']}`",
        f"- readiness_status: `{report['readiness_status']}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- ok: `{report['ok']}`",
        "",
        "## Source Reports",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in report["source_reports"].items())
    lines.extend(["", "## Legacy Drift"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["legacy_drift"]] or ["- none"])
    lines.extend(["", "## Side Effect Safety"])
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(report["side_effect_safety"].items()))
    lines.extend(["", "## Rollback Dry Run"])
    lines.extend(f"- {key}: `{value}`" for key, value in report["rollback_dry_run"].items())
    lines.extend(["", "## Blockers"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Missing Evidence"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["missing_evidence"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Batch 4 User Ops readonly canary readiness from existing reports.")
    parser.add_argument("--user-ops-smoke-json", required=True)
    parser.add_argument("--user-ops-parity-json", required=True)
    parser.add_argument("--readonly-dual-json", required=True)
    parser.add_argument(
        "--route-status-json",
        default=str(PROJECT_ROOT / "artifacts" / "frontend_screenshots" / "route_status.json"),
        help="Frontend screenshot route status JSON.",
    )
    parser.add_argument(
        "--real-pg-evidence",
        default=str(PROJECT_ROOT / "docs" / "real_postgres_integration_run.md"),
        help="Real local/test PostgreSQL integration evidence document.",
    )
    parser.add_argument(
        "--route-flags-doc",
        default=str(PROJECT_ROOT / "docs" / "batch_4_user_ops_readonly_route_flags.md"),
        help="Batch 4 route flags dry-run document.",
    )
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_readiness_report(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_markdown_report(report, args.output_md)
    write_json_report(report, args.output_json)
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("readiness_status:", report["readiness_status"])
    print("recommendation:", report["recommendation"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
