#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicrm_next.ops_enrollment import parity_spec  # noqa: E402

Json = dict[str, Any]


@dataclass(frozen=True)
class EndpointPlan:
    name: str
    method: str
    path: str
    validation_kind: str
    route_type: str = "api"


READ_ENDPOINTS: tuple[EndpointPlan, ...] = (
    EndpointPlan("admin_user_ops_page", "GET", "/admin/user-ops/ui", "page", route_type="page"),
    EndpointPlan("overview.default", "GET", "/api/admin/user-ops/overview", "overview"),
    EndpointPlan("list.default", "GET", "/api/admin/user-ops/list", "list"),
    EndpointPlan("list.wecom_added", "GET", "/api/admin/user-ops/list?wecom_status=added", "list"),
    EndpointPlan("list.not_added", "GET", "/api/admin/user-ops/list?wecom_status=not_added", "list"),
    EndpointPlan(
        "list.mobile_bound",
        "GET",
        "/api/admin/user-ops/list?mobile_binding_status=bound",
        "list",
    ),
    EndpointPlan(
        "list.activation_activated",
        "GET",
        "/api/admin/user-ops/list?activation_bucket=activated",
        "list",
    ),
    EndpointPlan("send_records.default", "GET", "/api/admin/user-ops/send-records", "send_records"),
)

FORBIDDEN_OLD_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FORBIDDEN_OLD_PATH_FRAGMENTS = (
    "/do-not-disturb",
    "/batch-send/preview",
    "/batch-send/execute",
    "/run-deferred-jobs",
    "/api/internal/user-ops",
)
LEGACY_ADMIN_AUTH_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def ensure_readonly(method: str, path: str, *, target: str) -> None:
    normalized = method.upper()
    if normalized != "GET" or normalized in FORBIDDEN_OLD_METHODS:
        raise ValueError(f"{target} endpoint is not readonly: {normalized} {path}")
    if target == "old" and any(fragment in path for fragment in FORBIDDEN_OLD_PATH_FRAGMENTS):
        raise ValueError(f"{target} endpoint is forbidden for readonly smoke: {normalized} {path}")


def _build_testclient():
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    return TestClient(create_app())


def _request_testclient(client: Any, method: str, path: str) -> tuple[int, Json | str]:
    ensure_readonly(method, path, target="next")
    response = client.request(method, path)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _request_http(base_url: str, method: str, path: str, *, target: str) -> tuple[int, Json | str]:
    ensure_readonly(method, path, target=target)
    with httpx.Client(timeout=10.0) as client:
        response = client.get(base_url.rstrip("/") + path)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _fetch_next(args: argparse.Namespace, client: Any | None, method: str, path: str) -> tuple[int, Json | str]:
    if args.next_testclient:
        return _request_testclient(client, method, path)
    return _request_http(args.next_base_url, method, path, target="next")


def _fetch_old(args: argparse.Namespace, method: str, path: str) -> tuple[int, Json | str]:
    return _request_http(args.old_base_url, method, path, target="old")


def _validate_payload(kind: str, payload: Json | str) -> list[Json]:
    if kind == "page":
        return []
    if not isinstance(payload, dict):
        return [{"rule": "payload_type", "expected": "object", "actual": type(payload).__name__, "severity": "fail"}]
    if kind == "overview":
        return parity_spec.validate_payload("overview.default", payload)
    if kind == "list":
        return parity_spec.validate_payload("list.default", payload)
    if kind == "send_records":
        return parity_spec.validate_payload("send_records.default", payload)
    return [{"rule": "unknown_validation_kind", "kind": kind, "severity": "fail"}]


def _issue_identity(issue: Json) -> tuple[str, str, str] | None:
    if issue.get("rule") == "required_key":
        return ("required_key", str(issue.get("location") or "$"), str(issue.get("key") or ""))
    if issue.get("rule") == "card_label":
        return ("card_label", str(issue.get("location") or "$.cards"), str(issue.get("label") or ""))
    if issue.get("rule") == "card_labels":
        return ("card_labels", str(issue.get("location") or "$.cards"), str(issue.get("message") or ""))
    if issue.get("rule") in {"items_type", "item_type", "send_records_items"}:
        return (str(issue.get("rule")), str(issue.get("location") or "$.items"), "")
    return None


def _legacy_reason(issue: Json) -> str:
    if issue.get("rule") == "card_label":
        return "legacy_missing_required_card_label"
    return "legacy_missing_required_contract"


def _contract_field(issue: Json) -> str:
    return str(issue.get("label") or issue.get("key") or issue.get("rule") or "")


def _classify_issues(path: str, old_issues: list[Json], next_issues: list[Json]) -> tuple[list[Json], list[Json], list[Json]]:
    blockers: list[Json] = []
    warnings: list[Json] = []
    legacy_drift: list[Json] = []
    old_identities = {identity for issue in old_issues for identity in [_issue_identity(issue)] if identity is not None}
    next_identities = {identity for issue in next_issues for identity in [_issue_identity(issue)] if identity is not None}

    for issue in next_issues:
        identity = _issue_identity(issue)
        reason = "both_missing_required_contract" if identity in old_identities else "next_missing_required_contract"
        blockers.append({"path": path, "side": "next", "reason": reason, **issue})

    for issue in old_issues:
        identity = _issue_identity(issue)
        if identity in next_identities:
            continue
        drift = {
            "endpoint": path,
            "field": _contract_field(issue),
            "rule": issue.get("rule"),
            "location": issue.get("location"),
            "reason": _legacy_reason(issue),
            "next_satisfies_contract": True,
        }
        legacy_drift.append(drift)
        warnings.append({"path": path, "side": "old", **drift})
    return blockers, warnings, legacy_drift


def _result_for_plan(
    plan: EndpointPlan,
    *,
    next_status: int | None,
    next_payload: Json | str | None,
    old_status: int | None = None,
    old_payload: Json | str | None = None,
) -> tuple[Json, list[Json], list[Json], list[Json]]:
    blockers: list[Json] = []
    warnings: list[Json] = []
    legacy_drift: list[Json] = []
    next_issues: list[Json] = []
    old_issues: list[Json] = []

    if next_status is None:
        blockers.append({"path": plan.path, "side": "next", "reason": "next_not_executed"})
    elif next_status >= 500:
        blockers.append({"path": plan.path, "side": "next", "reason": "next_status_5xx", "status_code": next_status})
    elif next_status != 200:
        blockers.append({"path": plan.path, "side": "next", "reason": "next_unexpected_status", "status_code": next_status})
    else:
        next_issues = _validate_payload(plan.validation_kind, next_payload if next_payload is not None else {})

    if old_status is not None:
        if old_status >= 500:
            blockers.append({"path": plan.path, "side": "old", "reason": "old_status_5xx", "status_code": old_status})
        elif (
            plan.route_type == "page"
            and old_status in LEGACY_ADMIN_AUTH_REDIRECT_STATUSES
            and next_status == 200
        ):
            drift = {
                "endpoint": plan.path,
                "field": "admin_auth_redirect",
                "rule": "legacy_admin_auth_redirect",
                "location": "$.status_code",
                "reason": "legacy_admin_auth_redirect",
                "next_satisfies_contract": True,
                "old_status_code": old_status,
            }
            legacy_drift.append(drift)
            warnings.append({"path": plan.path, "side": "old", **drift})
        elif old_status != 200:
            blockers.append({"path": plan.path, "side": "old", "reason": "old_unexpected_status", "status_code": old_status})
        else:
            old_issues = _validate_payload(plan.validation_kind, old_payload if old_payload is not None else {})

    if old_status is None:
        blockers.extend({"path": plan.path, "side": "next", "reason": "next_missing_required_contract", **issue} for issue in next_issues)
    elif old_status == 200 and next_status == 200:
        classified_blockers, classified_warnings, classified_drift = _classify_issues(plan.path, old_issues, next_issues)
        blockers.extend(classified_blockers)
        warnings.extend(classified_warnings)
        legacy_drift.extend(classified_drift)

    status = "PASS"
    if blockers:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    return (
        {
            "name": plan.name,
            "method": plan.method,
            "path": plan.path,
            "route_type": plan.route_type,
            "side_effect_risk": "read",
            "next_status": next_status,
            "old_status": old_status,
            "status": status,
            "ok": status in {"PASS", "WARN"},
            "issues": blockers + warnings,
            "legacy_drift": legacy_drift,
        },
        blockers,
        warnings,
        legacy_drift,
    )


def _failure_result(plan: EndpointPlan, reason: str, message: str) -> Json:
    issue = {"path": plan.path, "side": "old", "reason": reason, "message": message}
    return {
        "name": plan.name,
        "method": plan.method,
        "path": plan.path,
        "route_type": plan.route_type,
        "side_effect_risk": "read",
        "next_status": None,
        "old_status": None,
        "status": "FAIL",
        "ok": False,
        "issues": [issue],
        "legacy_drift": [],
    }


def run_smoke(args: argparse.Namespace) -> Json:
    if not args.next_testclient and not args.next_base_url:
        raise ValueError("--next-testclient or --next-base-url is required")

    route_results: list[Json] = []
    blockers: list[Json] = []
    warnings: list[Json] = []
    skipped: list[Json] = []
    legacy_drift: list[Json] = []
    side_effect_safety = {
        "old_write_endpoints_executed": False,
        "wecom_dispatch_executed": False,
        "media_upload_executed": False,
        "deferred_jobs_executed": False,
        "default_endpoints_get_only": all(endpoint.method == "GET" for endpoint in READ_ENDPOINTS),
    }

    client = _build_testclient() if args.next_testclient else None
    for plan in READ_ENDPOINTS:
        old_status: int | None = None
        old_payload: Json | str | None = None
        if args.old_base_url:
            try:
                old_status, old_payload = _fetch_old(args, plan.method, plan.path)
            except httpx.RequestError as exc:
                result = _failure_result(plan, "old_unreachable", str(exc))
                route_results.append(result)
                blockers.extend(result["issues"])
                continue

        next_status, next_payload = _fetch_next(args, client, plan.method, plan.path)
        result, result_blockers, result_warnings, result_drift = _result_for_plan(
            plan,
            next_status=next_status,
            next_payload=next_payload,
            old_status=old_status,
            old_payload=old_payload,
        )
        route_results.append(result)
        blockers.extend(result_blockers)
        warnings.extend(result_warnings)
        legacy_drift.extend(result_drift)

    return {
        "ok": not blockers,
        "mode": "dual-run" if args.old_base_url else "next-only",
        "old_base_url": args.old_base_url,
        "next_base_url": "" if args.next_testclient else args.next_base_url,
        "next_testclient": bool(args.next_testclient),
        "run_time": datetime.now(timezone.utc).isoformat(),
        "route_results": route_results,
        "blockers": blockers,
        "warnings": warnings,
        "skipped": skipped,
        "legacy_drift": legacy_drift,
        "side_effect_safety": side_effect_safety,
        "summary": {
            "compared": len(route_results),
            "passed": sum(1 for item in route_results if item["status"] == "PASS"),
            "warnings": sum(1 for item in route_results if item["status"] == "WARN"),
            "failed": sum(1 for item in route_results if item["status"] == "FAIL"),
            "skipped": len(skipped),
        },
    }


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# User Ops Readonly Gray Smoke Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- mode: `{report['mode']}`",
        f"- next: {'TestClient' if report['next_testclient'] else f'`{report['next_base_url']}`'}",
        f"- old_base_url: `{report['old_base_url'] or ''}`",
        f"- run_time: `{report['run_time']}`",
        f"- old_write_endpoints_executed: `{report['side_effect_safety']['old_write_endpoints_executed']}`",
        f"- wecom_dispatch_executed: `{report['side_effect_safety']['wecom_dispatch_executed']}`",
        f"- media_upload_executed: `{report['side_effect_safety']['media_upload_executed']}`",
        f"- deferred_jobs_executed: `{report['side_effect_safety']['deferred_jobs_executed']}`",
        "",
        "## Summary",
        "",
        f"- compared: {report['summary']['compared']}",
        f"- passed: {report['summary']['passed']}",
        f"- warnings: {report['summary']['warnings']}",
        f"- failed: {report['summary']['failed']}",
        f"- skipped: {report['summary']['skipped']}",
        "",
        "## Routes",
        "",
        "| name | method | path | old_status | next_status | status | issues |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["route_results"]:
        issue_text = "; ".join(issue.get("reason") or issue.get("rule", "issue") for issue in item.get("issues", [])) or "-"
        lines.append(
            f"| {item['name']} | {item['method']} | `{item['path']}` | {item['old_status']} | {item['next_status']} | {item['status']} | {issue_text} |"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- `{item.get('reason')}` `{item.get('path')}`: {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- `{item.get('reason')}` `{item.get('path')}`: {item}" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Legacy Drift", ""])
    lines.extend(
        [
            f"- `{item.get('reason')}` `{item.get('endpoint')}` field=`{item.get('field')}` next_satisfies_contract={item.get('next_satisfies_contract')}"
            for item in report["legacy_drift"]
        ]
        or ["- none"]
    )
    lines.extend(["", "## Skipped", ""])
    lines.extend([f"- `{item['name']}` `{item['path']}`: {item.get('reason', 'skipped')}" for item in report["skipped"]] or ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI-CRM Next User Ops readonly gray smoke checks.")
    parser.add_argument("--old-base-url", default="", help="Optional old Flask base URL. Only GET requests are sent.")
    parser.add_argument("--next-testclient", action="store_true", help="Run against AI-CRM Next FastAPI TestClient.")
    parser.add_argument("--next-base-url", default="", help="Run read-only checks against a Next HTTP base URL.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    print("old_write_endpoints_executed:", report["side_effect_safety"]["old_write_endpoints_executed"])
    print("wecom_dispatch_executed:", report["side_effect_safety"]["wecom_dispatch_executed"])
    print("media_upload_executed:", report["side_effect_safety"]["media_upload_executed"])
    print("deferred_jobs_executed:", report["side_effect_safety"]["deferred_jobs_executed"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
