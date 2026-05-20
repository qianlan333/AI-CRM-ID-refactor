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
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aicrm_next.customer_read_model import parity_spec as customer_spec  # noqa: E402
from aicrm_next.ops_enrollment import parity_spec as user_ops_spec  # noqa: E402

Json = dict[str, Any]


@dataclass(frozen=True)
class EndpointPlan:
    scope: str
    name: str
    method: str
    path: str
    validation_kind: str


CUSTOMER_LIST_ENDPOINTS = [
    EndpointPlan("customer", "customers.default", "GET", "/api/customers", "customer_list"),
    EndpointPlan("customer", "customers.page", "GET", "/api/customers?limit=5&offset=0", "customer_list"),
    EndpointPlan("customer", "customers.owner_filter", "GET", "/api/customers?owner_userid={owner_userid}", "customer_list"),
    EndpointPlan("customer", "customers.is_bound_true", "GET", "/api/customers?is_bound=true", "customer_list"),
    EndpointPlan("customer", "customers.keyword", "GET", "/api/customers?keyword={keyword}", "customer_list"),
]

CUSTOMER_SAMPLE_ENDPOINTS = [
    EndpointPlan("customer", "customer_detail.sample", "GET", "/api/customers/{external_userid}", "customer_detail"),
    EndpointPlan(
        "customer",
        "customer_timeline.sample",
        "GET",
        "/api/customers/{external_userid}/timeline",
        "customer_timeline",
    ),
    EndpointPlan(
        "customer",
        "customer_timeline.page",
        "GET",
        "/api/customers/{external_userid}/timeline?limit=5&offset=0",
        "customer_timeline",
    ),
    EndpointPlan(
        "customer",
        "recent_messages.sample",
        "GET",
        "/api/messages/{external_userid}/recent",
        "recent_messages",
    ),
    EndpointPlan(
        "customer",
        "recent_messages.limit",
        "GET",
        "/api/messages/{external_userid}/recent?limit=5",
        "recent_messages",
    ),
]

USER_OPS_ENDPOINTS = [
    EndpointPlan("user_ops", "overview.default", "GET", "/api/admin/user-ops/overview", "user_ops_overview"),
    EndpointPlan("user_ops", "list.default", "GET", "/api/admin/user-ops/list", "user_ops_list"),
    EndpointPlan("user_ops", "list.wecom_added", "GET", "/api/admin/user-ops/list?wecom_status=added", "user_ops_list"),
    EndpointPlan("user_ops", "list.not_added", "GET", "/api/admin/user-ops/list?wecom_status=not_added", "user_ops_list"),
    EndpointPlan(
        "user_ops",
        "list.mobile_bound",
        "GET",
        "/api/admin/user-ops/list?mobile_binding_status=bound",
        "user_ops_list",
    ),
    EndpointPlan(
        "user_ops",
        "list.activated",
        "GET",
        "/api/admin/user-ops/list?activation_bucket=activated",
        "user_ops_list",
    ),
    EndpointPlan("user_ops", "send_records.default", "GET", "/api/admin/user-ops/send-records", "user_ops_send_records"),
]

FORBIDDEN_OLD_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def parse_scopes(raw_scope: str) -> list[str]:
    scopes = [item.strip() for item in raw_scope.split(",") if item.strip()]
    unknown = sorted(set(scopes) - {"customer", "user_ops"})
    if unknown:
        raise ValueError(f"unknown scope(s): {', '.join(unknown)}")
    return scopes or ["customer", "user_ops"]


def default_endpoint_plans(scopes: list[str]) -> list[EndpointPlan]:
    plans: list[EndpointPlan] = []
    if "customer" in scopes:
        plans.extend(CUSTOMER_LIST_ENDPOINTS)
        plans.extend(CUSTOMER_SAMPLE_ENDPOINTS)
    if "user_ops" in scopes:
        plans.extend(USER_OPS_ENDPOINTS)
    return plans


def ensure_old_endpoint_is_readonly(method: str, path: str) -> None:
    normalized_method = method.upper()
    if normalized_method in FORBIDDEN_OLD_METHODS or normalized_method != "GET":
        raise ValueError(f"old service endpoint is not readonly: {normalized_method} {path}")


def _fetch_old_http(base_url: str, method: str, path: str) -> Json:
    ensure_old_endpoint_is_readonly(method, path)
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, base_url.rstrip("/") + path)
    return _response_to_result(response)


def _fetch_next_http(base_url: str, method: str, path: str) -> Json:
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, base_url.rstrip("/") + path)
    return _response_to_result(response)


def _fetch_next_testclient(method: str, path: str) -> Json:
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    response = TestClient(create_app()).request(method, path)
    return _response_to_result(response)


def _response_to_result(response: Any) -> Json:
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text}
    return {"status_code": response.status_code, "payload": payload}


def _customer_items(payload: Json) -> list[Json]:
    for key in ("items", "customers"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _sample_context(customer_list_payload: Json) -> Json:
    items = _customer_items(customer_list_payload)
    if not items:
        return {}
    sample = items[0]
    return {
        "external_userid": str(sample.get("external_userid") or ""),
        "owner_userid": str(sample.get("owner_userid") or ""),
        "keyword": str(sample.get("customer_name") or sample.get("mobile") or sample.get("external_userid") or ""),
    }


def _format_path(path: str, context: Json) -> str:
    safe_context = {key: str(value) for key, value in context.items()}
    return path.format(**safe_context)


def _is_sample_endpoint(plan: EndpointPlan) -> bool:
    return "{external_userid}" in plan.path


def _is_customer_dynamic_filter(plan: EndpointPlan) -> bool:
    return "{owner_userid}" in plan.path or "{keyword}" in plan.path


def _validate_payload(kind: str, payload: Any) -> list[Json]:
    if not isinstance(payload, dict):
        return [{"rule": "payload_type", "expected": "object", "actual": type(payload).__name__, "severity": "fail"}]
    if kind == "customer_list":
        return customer_spec.validate_payload("customers.default", payload)
    if kind == "customer_detail":
        return customer_spec.validate_payload("customer_detail.default", payload)
    if kind == "customer_timeline":
        return customer_spec.validate_payload("customer_timeline.default", payload)
    if kind == "recent_messages":
        return customer_spec.validate_payload("recent_messages.default", payload)
    if kind == "user_ops_overview":
        return user_ops_spec.validate_payload("overview.default", payload)
    if kind == "user_ops_list":
        return _validate_user_ops_list(payload)
    if kind == "user_ops_send_records":
        return user_ops_spec.validate_payload("send_records.default", payload)
    return [{"rule": "unknown_validation_kind", "kind": kind, "severity": "fail"}]


def _validate_user_ops_list(payload: Json) -> list[Json]:
    issues = user_ops_spec.compare_required_keys(payload, user_ops_spec.LIST_REQUIRED_KEYS)
    issues.extend(user_ops_spec.compare_item_required_keys(payload, user_ops_spec.LIST_ITEM_REQUIRED_KEYS))
    return issues


def _compare_type_family(kind: str, old_payload: Any, next_payload: Any) -> list[Json]:
    if not isinstance(old_payload, dict) or not isinstance(next_payload, dict):
        return []
    if kind.startswith("customer") or kind == "recent_messages":
        return customer_spec.compare_type_family(old_payload, next_payload)
    if kind == "user_ops_overview":
        return user_ops_spec.compare_type_family(old_payload, next_payload, user_ops_spec.OVERVIEW_REQUIRED_KEYS)
    if kind == "user_ops_list":
        return user_ops_spec.compare_type_family(old_payload, next_payload, user_ops_spec.LIST_REQUIRED_KEYS)
    if kind == "user_ops_send_records":
        return user_ops_spec.compare_type_family(old_payload, next_payload, user_ops_spec.SEND_RECORDS_REQUIRED_KEYS)
    return []


LEGACY_DRIFT_RULES = {"required_key", "card_label", "card_labels"}


def _issue_identity(issue: Json) -> tuple[str, str, str] | None:
    rule = str(issue.get("rule") or "")
    if rule == "required_key":
        return (rule, str(issue.get("location") or "$"), str(issue.get("key") or ""))
    if rule == "card_label":
        return (rule, str(issue.get("location") or "$.cards"), str(issue.get("label") or ""))
    if rule == "card_labels":
        return (rule, str(issue.get("location") or "$.cards"), str(issue.get("message") or ""))
    return None


def _legacy_drift_reason(issue: Json) -> str:
    if issue.get("rule") == "card_label":
        return "legacy_missing_required_card_label"
    return "legacy_missing_required_contract"


def _contract_blocker_reason(issue: Json, *, both_missing: bool) -> str:
    if both_missing:
        return "both_missing_required_card_label" if issue.get("rule") == "card_label" else "both_missing_required_contract"
    return "next_missing_required_card_label" if issue.get("rule") == "card_label" else "next_missing_required_contract"


def _classify_contract_issues(issues: list[Json], path: str) -> tuple[list[Json], list[Json]]:
    old_missing_identities = {
        identity
        for issue in issues
        if issue.get("side") == "old"
        and issue.get("severity") == "fail"
        and issue.get("rule") in LEGACY_DRIFT_RULES
        for identity in [_issue_identity(issue)]
        if identity is not None
    }
    next_missing_identities = {
        identity
        for issue in issues
        if issue.get("side") == "next"
        and issue.get("severity") == "fail"
        and issue.get("rule") in LEGACY_DRIFT_RULES
        for identity in [_issue_identity(issue)]
        if identity is not None
    }

    classified: list[Json] = []
    legacy_drift: list[Json] = []
    for issue in issues:
        issue = dict(issue)
        identity = _issue_identity(issue)
        if issue.get("side") == "old" and issue.get("severity") == "fail" and issue.get("rule") in LEGACY_DRIFT_RULES:
            if identity not in next_missing_identities:
                issue["severity"] = "warning"
                issue["reason"] = _legacy_drift_reason(issue)
                issue["next_satisfies_contract"] = True
                drift_item = {
                    "endpoint": path,
                    "field": issue.get("label") or issue.get("key") or issue.get("rule"),
                    "rule": issue.get("rule"),
                    "location": issue.get("location"),
                    "reason": issue["reason"],
                    "next_satisfies_contract": True,
                }
                legacy_drift.append(drift_item)
            else:
                issue["reason"] = _contract_blocker_reason(issue, both_missing=True)
        elif issue.get("side") == "next" and issue.get("severity") == "fail" and issue.get("rule") in LEGACY_DRIFT_RULES:
            issue["reason"] = _contract_blocker_reason(issue, both_missing=identity in old_missing_identities)
        classified.append(issue)
    return classified, legacy_drift


def _compare_endpoint(plan: EndpointPlan, path: str, old_result: Json, next_result: Json) -> Json:
    issues: list[Json] = []
    old_status = int(old_result.get("status_code", 0))
    next_status = int(next_result.get("status_code", 0))
    if old_status != 200:
        issues.append({"rule": "old_status_code", "expected": 200, "actual": old_status, "severity": "fail"})
    if next_status != 200:
        issues.append({"rule": "next_status_code", "expected": 200, "actual": next_status, "severity": "fail"})
    if old_status == 200:
        issues.extend({"side": "old", **issue} for issue in _validate_payload(plan.validation_kind, old_result.get("payload")))
    if next_status == 200:
        issues.extend({"side": "next", **issue} for issue in _validate_payload(plan.validation_kind, next_result.get("payload")))
    if old_status == 200 and next_status == 200:
        issues.extend(_compare_type_family(plan.validation_kind, old_result.get("payload"), next_result.get("payload")))
    legacy_drift: list[Json] = []
    if old_status == 200 and next_status == 200:
        issues, legacy_drift = _classify_contract_issues(issues, path)
    status = "PASS" if not any(issue.get("severity") == "fail" for issue in issues) else "FAIL"
    if status == "PASS" and any(issue.get("severity") == "warning" for issue in issues):
        status = "WARN"
    return {
        "scope": plan.scope,
        "endpoint": plan.name,
        "method": plan.method,
        "path": path,
        "old_status": old_status,
        "next_status": next_status,
        "status": status,
        "issues": issues,
        "legacy_drift": legacy_drift,
    }


def _skipped_result(plan: EndpointPlan, path: str, reason: str) -> Json:
    return {
        "scope": plan.scope,
        "endpoint": plan.name,
        "method": plan.method,
        "path": path,
        "old_status": None,
        "next_status": None,
        "status": "SKIPPED",
        "reason": reason,
        "issues": [{"rule": reason, "severity": "skip"}],
    }


def _old_unreachable_result(plan: EndpointPlan, path: str, exc: Exception) -> Json:
    return {
        "scope": plan.scope,
        "endpoint": plan.name,
        "method": plan.method,
        "path": path,
        "old_status": None,
        "next_status": None,
        "status": "FAIL",
        "reason": "old_unreachable",
        "issues": [{"rule": "old_unreachable", "severity": "fail", "message": str(exc)}],
    }


def run_dual_run(args: argparse.Namespace) -> Json:
    scopes = parse_scopes(args.scope)
    if not args.old_base_url:
        raise ValueError("--old-base-url is required for readonly dual-run")
    if not args.next_testclient and not args.next_base_url:
        raise ValueError("--next-base-url or --next-testclient is required")

    results: list[Json] = []
    skipped: list[Json] = []
    customer_context: Json = {}

    for plan in default_endpoint_plans(scopes):
        if _is_sample_endpoint(plan) and not customer_context.get("external_userid"):
            result = _skipped_result(plan, plan.path, "no_customer_sample")
            results.append(result)
            skipped.append(result)
            continue
        if _is_customer_dynamic_filter(plan):
            token_name = "owner_userid" if "{owner_userid}" in plan.path else "keyword"
            if not customer_context.get(token_name):
                result = _skipped_result(plan, plan.path, f"missing_{token_name}_sample")
                results.append(result)
                skipped.append(result)
                continue

        path = _format_path(plan.path, customer_context)
        try:
            old_result = _fetch_old_http(args.old_base_url, plan.method, path)
        except httpx.RequestError as exc:
            result = _old_unreachable_result(plan, path, exc)
            results.append(result)
            continue

        if plan.name == "customers.default" and int(old_result.get("status_code", 0)) == 200:
            customer_context = _sample_context(old_result.get("payload") or {})

        if args.next_testclient:
            next_result = _fetch_next_testclient(plan.method, path)
        else:
            next_result = _fetch_next_http(args.next_base_url, plan.method, path)
        results.append(_compare_endpoint(plan, path, old_result, next_result))

    blockers = [
        {"endpoint": item["endpoint"], "path": item["path"], "issues": item.get("issues", [])}
        for item in results
        if item["status"] == "FAIL"
    ]
    warnings = [
        {"endpoint": item["endpoint"], "path": item["path"], "issues": item.get("issues", [])}
        for item in results
        if item["status"] == "WARN"
    ]
    legacy_drift = [
        {**drift, "endpoint": item["endpoint"], "path": item["path"]}
        for item in results
        for drift in item.get("legacy_drift", [])
    ]
    skipped_results = [item for item in results if item["status"] == "SKIPPED"]
    return {
        "ok": not blockers,
        "old_base_url": args.old_base_url,
        "next_base_url": "" if args.next_testclient else args.next_base_url,
        "next_testclient": bool(args.next_testclient),
        "run_time": datetime.now(timezone.utc).isoformat(),
        "scope": scopes,
        "side_effect_safety": {
            "old_service_methods_allowed": ["GET"],
            "old_service_write_methods_forbidden": sorted(FORBIDDEN_OLD_METHODS),
            "old_service_write_endpoints_executed": False,
        },
        "blockers": blockers,
        "warnings": warnings,
        "legacy_drift": legacy_drift,
        "skipped": skipped_results,
        "endpoint_results": results,
        "summary": {
            "compared": sum(1 for item in results if item["status"] in {"PASS", "FAIL", "WARN"}),
            "passed": sum(1 for item in results if item["status"] == "PASS"),
            "warnings": sum(1 for item in results if item["status"] == "WARN"),
            "failed": sum(1 for item in results if item["status"] == "FAIL"),
            "skipped": len(skipped_results),
        },
    }


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI-CRM Next Readonly HTTP Dual-Run Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- old_base_url: `{report['old_base_url']}`",
        f"- next: {'TestClient' if report['next_testclient'] else f'`{report['next_base_url']}`'}",
        f"- run_time: `{report['run_time']}`",
        f"- scope: `{','.join(report['scope'])}`",
        f"- old service allowed methods: `{', '.join(report['side_effect_safety']['old_service_methods_allowed'])}`",
        f"- old service write endpoints executed: `{report['side_effect_safety']['old_service_write_endpoints_executed']}`",
        "",
        "## Summary",
        "",
        f"- compared: {report['summary']['compared']}",
        f"- passed: {report['summary']['passed']}",
        f"- warnings: {report['summary'].get('warnings', 0)}",
        f"- failed: {report['summary']['failed']}",
        f"- skipped: {report['summary']['skipped']}",
        "",
        "## Endpoint Results",
        "",
        "| scope | endpoint | method | path | old_status | next_status | status | issues |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["endpoint_results"]:
        issue_text = (
            "; ".join(
                issue.get("reason") or issue.get("rule", "issue")
                for issue in item.get("issues", [])
                if issue.get("severity") in {"fail", "warning"}
            )
            or item.get("reason", "-")
        )
        lines.append(
            f"| {item['scope']} | {item['endpoint']} | {item['method']} | `{item['path']}` | "
            f"{item['old_status']} | {item['next_status']} | {item['status']} | {issue_text} |"
        )
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        for item in report["blockers"]:
            lines.append(f"- `{item['endpoint']}` `{item['path']}`: {', '.join(issue.get('rule', 'issue') for issue in item.get('issues', []))}")
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        for item in report["warnings"]:
            warning_text = ", ".join(
                issue.get("reason") or issue.get("rule", "issue")
                for issue in item.get("issues", [])
                if issue.get("severity") == "warning"
            )
            lines.append(f"- `{item['endpoint']}` `{item['path']}`: {warning_text}")
    else:
        lines.append("- None")
    lines.extend(["", "## Legacy Drift", ""])
    if report.get("legacy_drift"):
        for item in report["legacy_drift"]:
            lines.append(
                f"- `{item['endpoint']}` `{item['path']}`: {item.get('reason')} "
                f"`{item.get('field')}`; next_satisfies_contract={item.get('next_satisfies_contract')}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Skipped", ""])
    if report["skipped"]:
        for item in report["skipped"]:
            lines.append(f"- `{item['endpoint']}` `{item['path']}`: {item.get('reason', 'skipped')}")
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only HTTP dual-run checks between old Flask and AI-CRM Next.")
    parser.add_argument("--old-base-url", required=True, help="Old Flask base URL. The tool only sends GET requests to this service.")
    parser.add_argument("--next-base-url", default="", help="AI-CRM Next base URL.")
    parser.add_argument("--next-testclient", action="store_true", help="Use AI-CRM Next FastAPI TestClient instead of HTTP.")
    parser.add_argument("--scope", default="customer,user_ops", help="Comma-separated scopes: customer,user_ops.")
    parser.add_argument("--output-md", required=True, help="Markdown report output path.")
    parser.add_argument("--output-json", required=True, help="JSON report output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_dual_run(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
