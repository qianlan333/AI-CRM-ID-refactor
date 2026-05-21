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

from aicrm_next.automation_engine import parity_spec  # noqa: E402

Json = dict[str, Any]


@dataclass(frozen=True)
class EndpointPlan:
    name: str
    method: str
    path_template: str
    validation_kind: str
    route_type: str = "api"
    requires_member_id: bool = False
    old_path_template: str | None = None
    old_requires_external_userid: bool = False


READ_ENDPOINTS: tuple[EndpointPlan, ...] = (
    EndpointPlan("admin_automation_page", "GET", "/admin/automation-conversion", "page", route_type="page"),
    EndpointPlan(
        "overview.default",
        "GET",
        "/api/admin/automation-conversion/overview",
        "overview",
        old_path_template="/api/admin/automation-conversion/dashboard",
    ),
    EndpointPlan(
        "pools.default",
        "GET",
        "/api/admin/automation-conversion/pools",
        "pools",
        old_path_template="/api/admin/automation-conversion/dashboard",
    ),
    EndpointPlan(
        "members.default",
        "GET",
        "/api/admin/automation-conversion/members",
        "members",
        old_path_template="/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50",
    ),
    EndpointPlan(
        "member_detail.sample",
        "GET",
        "/api/admin/automation-conversion/members/{member_id}",
        "member_detail",
        requires_member_id=True,
        old_path_template="/api/admin/automation-conversion/member?external_contact_id={external_userid}",
        old_requires_external_userid=True,
    ),
    EndpointPlan(
        "execution_records.default",
        "GET",
        "/api/admin/automation-conversion/execution-records",
        "execution_records",
        old_path_template="/api/admin/automation-conversion/executions",
    ),
)


@dataclass(frozen=True)
class FakeWritePlan:
    name: str
    path_template: str
    payload: Json
    validation_kind: str = "fake_write"


FAKE_WRITE_PLANS: tuple[FakeWritePlan, ...] = (
    FakeWritePlan(
        "override_followup_type.fake_next_only",
        "/api/admin/automation-conversion/members/{member_id}/override-followup-type",
        {"followup_type": "priority", "operator": "gray_smoke", "reason": "fake_gray_smoke"},
    ),
    FakeWritePlan(
        "confirm_conversion.fake_next_only",
        "/api/admin/automation-conversion/members/{member_id}/confirm-conversion",
        {"operator": "gray_smoke", "reason": "fake_gray_smoke"},
    ),
    FakeWritePlan(
        "enter_silent.fake_next_only",
        "/api/admin/automation-conversion/members/{member_id}/enter-silent",
        {"operator": "gray_smoke", "reason": "fake_gray_smoke"},
    ),
    FakeWritePlan(
        "exit_marketing.fake_next_only",
        "/api/admin/automation-conversion/members/{member_id}/exit-marketing",
        {"operator": "gray_smoke", "reason": "fake_gray_smoke"},
    ),
)

FORBIDDEN_OLD_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FORBIDDEN_OLD_PATH_FRAGMENTS = (
    "override-followup-type",
    "confirm-conversion",
    "enter-silent",
    "exit-marketing",
    "push-openclaw-context",
    "activation-webhook",
    "workflow",
    "agent",
    "webhook",
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

    from aicrm_next.automation_engine.repo import reset_automation_fixture_state
    from aicrm_next.main import create_app

    reset_automation_fixture_state()
    return TestClient(create_app())


def _reset_automation_state() -> None:
    from aicrm_next.automation_engine.repo import reset_automation_fixture_state

    reset_automation_fixture_state()


def _request_testclient(client: Any, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    if method.upper() != "GET" and not _is_allowed_fake_write_path(path):
        raise ValueError(f"next endpoint is not allowed for automation gray smoke: {method} {path}")
    response = client.request(method, path, json=payload)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _is_allowed_fake_write_path(path: str) -> bool:
    return any(
        path.startswith("/api/admin/automation-conversion/members/")
        and path.endswith(template.path_template.split("{member_id}", 1)[1])
        for template in FAKE_WRITE_PLANS
    )


def _request_next_read(client: Any | None, args: argparse.Namespace, path: str) -> tuple[int, Json | str]:
    if args.next_testclient:
        ensure_readonly("GET", path, target="next")
        return _request_testclient(client, "GET", path)
    return _request_http(args.next_base_url, "GET", path, target="next")


def _request_http(base_url: str, method: str, path: str, *, target: str) -> tuple[int, Json | str]:
    ensure_readonly(method, path, target=target)
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        response = client.get(base_url.rstrip("/") + path)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _fetch_old(args: argparse.Namespace, path: str) -> tuple[int, Json | str]:
    return _request_http(args.old_base_url, "GET", path, target="old")


def _validate_payload(kind: str, payload: Json | str) -> list[Json]:
    if kind == "page":
        return []
    if not isinstance(payload, dict):
        return [{"rule": "payload_type", "expected": "object", "actual": type(payload).__name__, "severity": "fail"}]
    if kind == "overview":
        return parity_spec.validate_payload("overview.default", payload)
    if kind == "pools":
        return parity_spec.validate_payload("pools.default", payload)
    if kind == "members":
        return parity_spec.validate_payload("members.default", payload)
    if kind == "member_detail":
        return parity_spec.validate_payload("member_detail.default", payload)
    if kind == "execution_records":
        return parity_spec.validate_payload("execution_records.default", payload)
    if kind == "fake_write":
        issues = parity_spec.compare_required_keys(payload, ["ok", "member", "history"])
        if isinstance(payload.get("member"), dict):
            issues.extend(parity_spec.compare_required_keys(payload["member"], parity_spec.MEMBER_ITEM_KEYS, location="$.member"))
        return issues
    return [{"rule": "unknown_validation_kind", "kind": kind, "severity": "fail"}]


def _member_items(payload: Json | str) -> list[Json]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _sample_context_from_members(payload: Json | str) -> Json:
    for item in _member_items(payload):
        member_id = str(item.get("member_id") or "")
        if member_id:
            return {"member_id": member_id, "external_userid": str(item.get("external_userid") or "")}
    return {}


def _sample_context_from_old_members(payload: Json | str) -> Json:
    if not isinstance(payload, dict):
        return {}
    candidate_lists: list[Any] = []
    for key in ("items", "members", "customers"):
        candidate_lists.append(payload.get(key))
    result = payload.get("result")
    if isinstance(result, dict):
        candidate_lists.extend([result.get("items"), result.get("members"), result.get("customers")])
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, dict):
        audience_details = dashboard.get("audience_member_details")
        if isinstance(audience_details, dict):
            for group in audience_details.get("groups") or []:
                if isinstance(group, dict):
                    candidate_lists.append(group.get("items"))
    for candidate_list in candidate_lists:
        if not isinstance(candidate_list, list):
            continue
        for item in candidate_list:
            if not isinstance(item, dict):
                continue
            external_userid = str(item.get("external_contact_id") or item.get("external_userid") or "")
            member_id = str(item.get("id") or item.get("member_id") or "")
            if external_userid:
                return {"external_userid": external_userid, "member_id": member_id}
    return {}


def _all_member_ids(payload: Json | str) -> list[str]:
    seen: list[str] = []
    for item in _member_items(payload):
        member_id = str(item.get("member_id") or "")
        if member_id and member_id not in seen:
            seen.append(member_id)
    return seen


def _format_path(plan: EndpointPlan | FakeWritePlan, context: Json) -> str:
    return plan.path_template.format(**{key: str(value) for key, value in context.items()})


def _missing_context(plan: EndpointPlan, context: Json) -> str:
    if plan.requires_member_id and not context.get("member_id"):
        return "missing_member_id"
    return ""


def _missing_old_context(plan: EndpointPlan, context: Json) -> str:
    if plan.old_requires_external_userid and not context.get("external_userid"):
        return "missing_external_userid"
    return ""


def _old_path_for_plan(plan: EndpointPlan, context: Json) -> str:
    template = plan.old_path_template or plan.path_template
    return template.format(**{key: str(value) for key, value in context.items()})


def _issue_identity(issue: Json) -> tuple[str, str, str] | None:
    if issue.get("rule") == "required_key":
        return ("required_key", str(issue.get("location") or "$"), str(issue.get("key") or ""))
    if issue.get("rule") == "type_family":
        return ("type_family", str(issue.get("location") or "$"), str(issue.get("expected") or ""))
    return None


def _classify_issues(path: str, old_issues: list[Json], next_issues: list[Json]) -> tuple[list[Json], list[Json], list[Json]]:
    blockers: list[Json] = []
    warnings: list[Json] = []
    legacy_drift: list[Json] = []
    next_identities = {identity for issue in next_issues for identity in [_issue_identity(issue)] if identity is not None}
    old_identities = {identity for issue in old_issues for identity in [_issue_identity(issue)] if identity is not None}

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
            "field": issue.get("key") or issue.get("rule"),
            "rule": issue.get("rule"),
            "location": issue.get("location"),
            "reason": "legacy_missing_required_contract",
            "next_satisfies_contract": True,
        }
        legacy_drift.append(drift)
        warnings.append({"path": path, "side": "old", **drift})
    return blockers, warnings, legacy_drift


def _result_for_plan(
    plan: EndpointPlan,
    *,
    next_path: str,
    next_status: int | None,
    next_payload: Json | str | None,
    old_path: str | None = None,
    old_status: int | None = None,
    old_payload: Json | str | None = None,
) -> tuple[Json, list[Json], list[Json], list[Json]]:
    blockers: list[Json] = []
    warnings: list[Json] = []
    legacy_drift: list[Json] = []
    next_issues: list[Json] = []
    old_issues: list[Json] = []
    display_path = plan.path_template

    if next_status is None:
        blockers.append({"path": display_path, "side": "next", "reason": "next_not_executed"})
    elif next_status >= 500:
        blockers.append({"path": display_path, "side": "next", "reason": "next_status_5xx", "status_code": next_status})
    elif next_status != 200:
        blockers.append({"path": display_path, "side": "next", "reason": "next_unexpected_status", "status_code": next_status})
    else:
        next_issues = _validate_payload(plan.validation_kind, next_payload if next_payload is not None else {})

    if old_status is not None:
        if old_status >= 500:
            blockers.append({"path": display_path, "side": "old", "reason": "old_status_5xx", "status_code": old_status})
        elif plan.route_type == "page" and old_status in LEGACY_ADMIN_AUTH_REDIRECT_STATUSES and next_status == 200:
            drift = {
                "endpoint": display_path,
                "field": "admin_auth_redirect",
                "rule": "legacy_admin_auth_redirect",
                "location": "$.status_code",
                "reason": "legacy_admin_auth_redirect",
                "next_satisfies_contract": True,
                "old_status_code": old_status,
            }
            legacy_drift.append(drift)
            warnings.append({"path": display_path, "side": "old", **drift})
        elif old_status in {404, 405} and next_status == 200:
            drift = {
                "endpoint": display_path,
                "field": "automation_readonly_route",
                "rule": "legacy_missing_read_route",
                "location": "$.status_code",
                "reason": "legacy_missing_read_route",
                "next_satisfies_contract": True,
                "old_status_code": old_status,
                "note": "Old Flask may expose automation conversion through legacy page/data endpoints; Next satisfies the scoped readonly contract.",
            }
            legacy_drift.append(drift)
            warnings.append({"path": display_path, "side": "old", **drift})
        elif old_status != 200:
            blockers.append({"path": display_path, "side": "old", "reason": "old_unexpected_status", "status_code": old_status})
        else:
            old_issues = _validate_payload(plan.validation_kind, old_payload if old_payload is not None else {})

    if old_status is None:
        blockers.extend({"path": display_path, "side": "next", "reason": "next_missing_required_contract", **issue} for issue in next_issues)
    elif old_status == 200 and next_status == 200:
        classified_blockers, classified_warnings, classified_drift = _classify_issues(display_path, old_issues, next_issues)
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
            "path": display_path,
            "old_path": old_path,
            "next_path": next_path,
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


def _skipped(plan: EndpointPlan | FakeWritePlan, reason: str) -> Json:
    return {
        "name": plan.name,
        "method": getattr(plan, "method", "POST"),
        "path": plan.path_template,
        "old_path": None,
        "next_path": None,
        "route_type": "api",
        "side_effect_risk": "read" if isinstance(plan, EndpointPlan) else "next_fake_write",
        "next_status": None,
        "old_status": None,
        "status": "SKIPPED",
        "ok": True,
        "reason": reason,
        "issues": [{"rule": reason, "severity": "skip"}],
        "legacy_drift": [],
    }


def _failure_result(plan: EndpointPlan, reason: str, message: str) -> Json:
    issue = {"path": plan.path_template, "side": "old", "reason": reason, "message": message}
    return {
        "name": plan.name,
        "method": plan.method,
        "path": plan.path_template,
        "old_path": None,
        "next_path": None,
        "route_type": plan.route_type,
        "side_effect_risk": "read",
        "next_status": None,
        "old_status": None,
        "status": "FAIL",
        "ok": False,
        "issues": [issue],
        "legacy_drift": [],
    }


def _run_fake_writes(args: argparse.Namespace, client: Any | None, member_ids: list[str]) -> tuple[list[Json], list[Json], Json]:
    if not args.include_fake_writes:
        return [], [], {"reason": "fake_writes_not_requested", "message": "Fake state-machine writes require --include-fake-writes and target Next TestClient only."}
    if not args.next_testclient:
        return [], [{"reason": "fake_writes_require_next_testclient", "message": "--include-fake-writes is allowed only with --next-testclient."}], {}
    if not member_ids:
        return [], [], {"reason": "missing_member_id_for_fake_writes", "message": "No automation member sample available."}

    results: list[Json] = []
    blockers: list[Json] = []
    for index, plan in enumerate(FAKE_WRITE_PLANS):
        member_id = member_ids[index % len(member_ids)]
        path = plan.path_template.format(member_id=member_id)
        status_code, payload = _request_testclient(client, "POST", path, plan.payload)
        issues: list[Json] = []
        if status_code != 200:
            issues.append({"path": path, "side": "next", "reason": "fake_write_unexpected_status", "status_code": status_code})
        elif isinstance(payload, dict):
            issues.extend({"path": path, "side": "next", "reason": "fake_write_contract", **issue} for issue in _validate_payload(plan.validation_kind, payload))
        else:
            issues.append({"path": path, "side": "next", "reason": "fake_write_payload_type"})
        result = {
            "name": plan.name,
            "method": "POST",
            "path": path,
            "old_path": None,
            "next_path": path,
            "route_type": "api",
            "side_effect_risk": "next_fake_write",
            "next_status": status_code,
            "old_status": None,
            "status": "PASS" if not issues else "FAIL",
            "ok": not issues,
            "issues": issues,
            "legacy_drift": [],
        }
        results.append(result)
        blockers.extend(issues)
    return results, blockers, {}


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
        "openclaw_push_executed": False,
        "wecom_dispatch_executed": False,
        "external_webhook_executed": False,
        "activation_webhook_executed": False,
        "workflow_runtime_executed": False,
        "next_fake_writes_executed": False,
        "default_endpoints_get_only": all(endpoint.method == "GET" for endpoint in READ_ENDPOINTS),
    }

    if args.include_fake_writes and not args.next_testclient:
        blocker = {"reason": "fake_writes_require_next_testclient", "message": "--include-fake-writes is allowed only with --next-testclient."}
        return {
            "ok": False,
            "mode": "dual-run" if args.old_base_url else "next-only",
            "old_base_url": args.old_base_url,
            "next_base_url": args.next_base_url,
            "next_testclient": bool(args.next_testclient),
            "include_fake_writes": True,
            "run_time": datetime.now(timezone.utc).isoformat(),
            "sample_member_id": "",
            "route_results": [],
            "blockers": [blocker],
            "warnings": [],
            "skipped": [],
            "legacy_drift": [],
            "side_effect_safety": side_effect_safety,
            "summary": {"compared": 0, "passed": 0, "warnings": 0, "failed": 0, "skipped": 0},
        }

    client = _build_testclient() if args.next_testclient else None
    old_context: Json = {}
    next_context: Json = {}
    next_member_ids: list[str] = []

    for plan in READ_ENDPOINTS:
        next_missing = _missing_context(plan, next_context)
        old_missing = _missing_old_context(plan, old_context) if args.old_base_url else ""
        if next_missing or old_missing:
            item = _skipped(plan, old_missing or next_missing)
            route_results.append(item)
            skipped.append(item)
            continue

        old_status: int | None = None
        old_payload: Json | str | None = None
        old_path: str | None = None
        if args.old_base_url:
            old_path = _old_path_for_plan(plan, old_context)
            try:
                old_status, old_payload = _fetch_old(args, old_path)
            except httpx.RequestError as exc:
                result = _failure_result(plan, "old_unreachable", str(exc))
                route_results.append(result)
                blockers.extend(result["issues"])
                continue

        next_path = _format_path(plan, next_context)
        next_status, next_payload = _request_next_read(client, args, next_path)

        if plan.name == "members.default":
            if args.old_base_url and old_status == 200:
                old_context.update(_sample_context_from_old_members(old_payload))
            if next_status == 200:
                next_context.update(_sample_context_from_members(next_payload))
                next_member_ids = _all_member_ids(next_payload)

        result, result_blockers, result_warnings, result_drift = _result_for_plan(
            plan,
            next_path=next_path,
            next_status=next_status,
            next_payload=next_payload,
            old_path=old_path,
            old_status=old_status,
            old_payload=old_payload,
        )
        route_results.append(result)
        blockers.extend(result_blockers)
        warnings.extend(result_warnings)
        legacy_drift.extend(result_drift)

    fake_write_results, fake_write_blockers, fake_write_skip = _run_fake_writes(args, client, next_member_ids)
    route_results.extend(fake_write_results)
    blockers.extend(fake_write_blockers)
    if fake_write_results:
        side_effect_safety["next_fake_writes_executed"] = True
    if fake_write_skip:
        skipped.append(fake_write_skip)

    if args.next_testclient:
        _reset_automation_state()

    return {
        "ok": not blockers,
        "mode": "dual-run" if args.old_base_url else "next-only",
        "old_base_url": args.old_base_url,
        "next_base_url": "" if args.next_testclient else args.next_base_url,
        "next_testclient": bool(args.next_testclient),
        "include_fake_writes": bool(args.include_fake_writes),
        "run_time": datetime.now(timezone.utc).isoformat(),
        "sample_member_id": next_context.get("member_id", ""),
        "route_results": route_results,
        "blockers": blockers,
        "warnings": warnings,
        "skipped": skipped,
        "legacy_drift": legacy_drift,
        "side_effect_safety": side_effect_safety,
        "summary": {
            "compared": sum(1 for item in route_results if item.get("status") in {"PASS", "WARN", "FAIL"}),
            "passed": sum(1 for item in route_results if item.get("status") == "PASS"),
            "warnings": sum(1 for item in route_results if item.get("status") == "WARN"),
            "failed": sum(1 for item in route_results if item.get("status") == "FAIL"),
            "skipped": len(skipped),
        },
    }


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Automation Readonly Gray Smoke Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- mode: `{report['mode']}`",
        f"- next: {'TestClient' if report['next_testclient'] else f'`{report['next_base_url']}`'}",
        f"- old_base_url: `{report['old_base_url'] or ''}`",
        f"- include_fake_writes: `{report['include_fake_writes']}`",
        f"- run_time: `{report['run_time']}`",
        f"- sample_member_id: `{report['sample_member_id']}`",
        f"- old_write_endpoints_executed: `{report['side_effect_safety']['old_write_endpoints_executed']}`",
        f"- openclaw_push_executed: `{report['side_effect_safety']['openclaw_push_executed']}`",
        f"- wecom_dispatch_executed: `{report['side_effect_safety']['wecom_dispatch_executed']}`",
        f"- external_webhook_executed: `{report['side_effect_safety']['external_webhook_executed']}`",
        f"- activation_webhook_executed: `{report['side_effect_safety']['activation_webhook_executed']}`",
        f"- workflow_runtime_executed: `{report['side_effect_safety']['workflow_runtime_executed']}`",
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
    lines.extend([f"- `{item.get('name', 'item')}` `{item.get('path', '')}`: {item.get('reason', 'skipped')}" for item in report["skipped"]] or ["- none"])
    lines.extend(["", "## Side Effect Safety", ""])
    for key, value in report["side_effect_safety"].items():
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI-CRM Next Automation readonly gray smoke checks.")
    parser.add_argument("--old-base-url", default="", help="Optional old Flask base URL. Only GET requests are sent.")
    parser.add_argument("--next-testclient", action="store_true", help="Run against AI-CRM Next FastAPI TestClient.")
    parser.add_argument("--next-base-url", default="", help="Run read-only checks against a Next HTTP base URL.")
    parser.add_argument("--include-fake-writes", action="store_true", help="Run Next TestClient-only fake state-machine writes.")
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
    print("openclaw_push_executed:", report["side_effect_safety"]["openclaw_push_executed"])
    print("wecom_dispatch_executed:", report["side_effect_safety"]["wecom_dispatch_executed"])
    print("external_webhook_executed:", report["side_effect_safety"]["external_webhook_executed"])
    print("activation_webhook_executed:", report["side_effect_safety"]["activation_webhook_executed"])
    print("workflow_runtime_executed:", report["side_effect_safety"]["workflow_runtime_executed"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
