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

from aicrm_next.questionnaire import parity_spec  # noqa: E402

Json = dict[str, Any]


@dataclass(frozen=True)
class EndpointPlan:
    name: str
    method: str
    path_template: str
    validation_kind: str
    route_type: str = "api"
    requires_questionnaire_id: bool = False
    requires_slug: bool = False
    requires_submission_id: bool = False


READ_ENDPOINTS: tuple[EndpointPlan, ...] = (
    EndpointPlan("admin_questionnaires_page", "GET", "/admin/questionnaires", "page", route_type="page"),
    EndpointPlan("admin_questionnaires_ui", "GET", "/admin/questionnaires/ui", "page", route_type="page"),
    EndpointPlan("admin_list.default", "GET", "/api/admin/questionnaires", "admin_list"),
    EndpointPlan(
        "admin_detail.sample",
        "GET",
        "/api/admin/questionnaires/{questionnaire_id}",
        "admin_detail",
        requires_questionnaire_id=True,
    ),
    EndpointPlan("admin_preflight.default", "GET", "/api/admin/questionnaires/preflight", "admin_preflight"),
    EndpointPlan(
        "admin_latest_submit_debug.sample",
        "GET",
        "/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug",
        "latest_submit_debug",
        requires_questionnaire_id=True,
    ),
    EndpointPlan(
        "admin_export.sample",
        "GET",
        "/api/admin/questionnaires/{questionnaire_id}/export",
        "admin_export",
        requires_questionnaire_id=True,
    ),
    EndpointPlan("public_page.sample", "GET", "/s/{slug}", "page", route_type="page", requires_slug=True),
    EndpointPlan("public_get.sample", "GET", "/api/h5/questionnaires/{slug}", "public_get", requires_slug=True),
    EndpointPlan(
        "public_result.sample",
        "GET",
        "/api/h5/questionnaires/{slug}/result/{submission_id}",
        "public_result",
        requires_slug=True,
        requires_submission_id=True,
    ),
)

FAKE_SUBMIT_PATH_TEMPLATE = "/api/h5/questionnaires/{slug}/submit"
FAKE_SUBMIT_PAYLOAD = {
    "answers": {"q_activation": "activated", "q_interest": ["ai_tools"]},
    "respondent_identity": {"external_userid": "external_user_masked_gray_001", "openid": "openid_masked_gray_001"},
}

FORBIDDEN_OLD_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FORBIDDEN_OLD_PATH_FRAGMENTS = (
    "/submit",
    "/oauth/start",
    "/oauth/callback",
    "/api/admin/questionnaires",
    "/external-push",
    "/retry",
    "/webhook",
)
LEGACY_ADMIN_AUTH_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def ensure_readonly(method: str, path: str, *, target: str) -> None:
    normalized = method.upper()
    if normalized != "GET" or normalized in FORBIDDEN_OLD_METHODS:
        raise ValueError(f"{target} endpoint is not readonly: {normalized} {path}")
    if target == "old":
        if path.startswith("/api/admin/questionnaires") and normalized != "GET":
            raise ValueError(f"{target} questionnaire admin write is forbidden: {normalized} {path}")
        if any(fragment in path for fragment in FORBIDDEN_OLD_PATH_FRAGMENTS if fragment != "/api/admin/questionnaires"):
            raise ValueError(f"{target} endpoint is forbidden for readonly smoke: {normalized} {path}")


def _build_testclient():
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app
    from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state

    reset_questionnaire_fixture_state()
    return TestClient(create_app())


def _reset_questionnaire_state() -> None:
    from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state

    reset_questionnaire_fixture_state()


def _request_testclient(client: Any, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    if method.upper() != "GET" and not path.endswith("/submit"):
        raise ValueError(f"next endpoint is not allowed for questionnaire gray smoke: {method} {path}")
    response = client.request(method, path, json=payload)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _request_next_read(client: Any | None, args: argparse.Namespace, path: str) -> tuple[int, Json | str]:
    if args.next_testclient:
        ensure_readonly("GET", path, target="next")
        return _request_testclient(client, "GET", path)
    return _request_http(args.next_base_url, "GET", path, target="next")


def _request_http(base_url: str, method: str, path: str, *, target: str) -> tuple[int, Json | str]:
    ensure_readonly(method, path, target=target)
    with httpx.Client(timeout=10.0) as client:
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
    if kind == "admin_list":
        return parity_spec.validate_payload("admin_list.default", payload)
    if kind == "admin_detail":
        return parity_spec.validate_payload("admin_detail.default", payload)
    if kind == "admin_preflight":
        return parity_spec.validate_payload("admin_preflight.default", payload)
    if kind == "public_get":
        return parity_spec.validate_payload("public_get.default", payload)
    if kind == "submit":
        return parity_spec.validate_payload("submit.default", payload)
    if kind == "latest_submit_debug":
        issues = parity_spec.compare_required_keys(payload, ["ok", "submission", "source_status", "safe_debug"])
        submission = payload.get("submission")
        if submission is not None and not isinstance(submission, dict):
            issues.append({"rule": "type_family", "location": "$.submission", "expected": "object_or_null", "actual": type(submission).__name__, "severity": "fail"})
        return issues
    if kind == "admin_export":
        issues = parity_spec.compare_required_keys(payload, ["ok", "export"])
        export = payload.get("export")
        if isinstance(export, dict):
            issues.extend(parity_spec.compare_required_keys(export, ["filename", "items", "total", "format"], location="$.export"))
        else:
            issues.append({"rule": "type_family", "location": "$.export", "expected": "object", "actual": type(export).__name__, "severity": "fail"})
        return issues
    if kind == "public_result":
        issues = parity_spec.compare_required_keys(payload, ["ok", "result", "result_message"])
        result = payload.get("result")
        if isinstance(result, dict):
            issues.extend(parity_spec.compare_required_keys(result, ["submission_id", "questionnaire_id", "slug"], location="$.result"))
        else:
            issues.append({"rule": "type_family", "location": "$.result", "expected": "object", "actual": type(result).__name__, "severity": "fail"})
        return issues
    return [{"rule": "unknown_validation_kind", "kind": kind, "severity": "fail"}]


def _questionnaire_items(payload: Json | str) -> list[Json]:
    if not isinstance(payload, dict):
        return []
    for key in ("items", "questionnaires"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _sample_context_from_list(payload: Json | str) -> Json:
    for item in _questionnaire_items(payload):
        questionnaire_id = item.get("id")
        slug = str(item.get("slug") or "")
        if questionnaire_id and slug:
            return {"questionnaire_id": str(questionnaire_id), "slug": slug}
    return {}


def _add_submission_context(context: Json, payload: Json | str) -> Json:
    if not isinstance(payload, dict):
        return context
    if isinstance(payload.get("submission"), dict):
        submission_id = str(payload["submission"].get("submission_id") or "")
    else:
        submission_id = str(payload.get("submission_id") or "")
    if submission_id:
        context = dict(context)
        context["submission_id"] = submission_id
    return context


def _format_path(plan: EndpointPlan, context: Json) -> str:
    return plan.path_template.format(**{key: str(value) for key, value in context.items()})


def _missing_context(plan: EndpointPlan, context: Json) -> str:
    missing: list[str] = []
    if plan.requires_questionnaire_id and not context.get("questionnaire_id"):
        missing.append("questionnaire_id")
    if plan.requires_slug and not context.get("slug"):
        missing.append("slug")
    if plan.requires_submission_id and not context.get("submission_id"):
        missing.append("submission_id")
    return "missing_" + "_".join(missing) if missing else ""


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
        elif plan.name == "public_get.sample" and old_status in {401, 403} and next_status == 200:
            drift = {
                "endpoint": display_path,
                "field": "wechat_browser_gate",
                "rule": "legacy_wechat_browser_gate",
                "location": "$.status_code",
                "reason": "legacy_wechat_browser_gate",
                "next_satisfies_contract": True,
                "old_status_code": old_status,
            }
            legacy_drift.append(drift)
            warnings.append({"path": display_path, "side": "old", **drift})
        elif plan.name == "public_result.sample" and old_status == 404 and next_status == 200:
            drift = {
                "endpoint": display_path,
                "field": "public_result_api_route",
                "rule": "legacy_missing_public_result_api",
                "location": "$.status_code",
                "reason": "legacy_missing_public_result_api",
                "next_satisfies_contract": True,
                "old_status_code": old_status,
                "note": "Old Flask exposes result as /s/{slug}/result/{result_token}; Next exposes JSON result API.",
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


def _skipped(plan: EndpointPlan, reason: str) -> Json:
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


def _run_fake_submit(args: argparse.Namespace, client: Any | None, context: Json) -> tuple[list[Json], list[Json], Json]:
    if not args.include_fake_submit:
        return [], [], {"reason": "fake_submit_not_requested", "message": "POST submit requires --include-fake-submit and targets Next TestClient only."}
    if not args.next_testclient:
        return [], [{"reason": "fake_submit_requires_next_testclient", "message": "--include-fake-submit is allowed only with --next-testclient."}], {}
    if not context.get("slug"):
        return [], [], {"reason": "missing_slug_for_fake_submit", "message": "No questionnaire slug sample available."}
    path = FAKE_SUBMIT_PATH_TEMPLATE.format(slug=context["slug"])
    status_code, payload = _request_testclient(client, "POST", path, FAKE_SUBMIT_PAYLOAD)
    issues: list[Json] = []
    if status_code != 200:
        issues.append({"path": path, "side": "next", "reason": "fake_submit_unexpected_status", "status_code": status_code})
    elif isinstance(payload, dict):
        issues.extend({"path": path, "side": "next", "reason": "fake_submit_contract", **issue} for issue in _validate_payload("submit", payload))
    else:
        issues.append({"path": path, "side": "next", "reason": "fake_submit_payload_type"})
    result = {
        "name": "submit.fake_next_only",
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
    return [result], issues, {}


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
        "old_submit_executed": False,
        "real_oauth_executed": False,
        "wecom_tag_executed": False,
        "external_webhook_executed": False,
        "next_fake_submit_executed": bool(args.include_fake_submit),
        "default_endpoints_get_only": all(endpoint.method == "GET" for endpoint in READ_ENDPOINTS),
    }

    if args.include_fake_submit and not args.next_testclient:
        blocker = {"reason": "fake_submit_requires_next_testclient", "message": "--include-fake-submit is allowed only with --next-testclient."}
        return {
            "ok": False,
            "mode": "dual-run" if args.old_base_url else "next-only",
            "old_base_url": args.old_base_url,
            "next_base_url": args.next_base_url,
            "next_testclient": bool(args.next_testclient),
            "include_fake_submit": True,
            "run_time": datetime.now(timezone.utc).isoformat(),
            "sample_questionnaire_id": "",
            "sample_slug": "",
            "sample_submission_id": "",
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

    for plan in READ_ENDPOINTS:
        next_missing = _missing_context(plan, next_context)
        old_missing = _missing_context(plan, old_context) if args.old_base_url else ""
        if next_missing or old_missing:
            item = _skipped(plan, old_missing or next_missing)
            route_results.append(item)
            skipped.append(item)
            continue

        old_status: int | None = None
        old_payload: Json | str | None = None
        old_path: str | None = None
        if args.old_base_url:
            old_path = _format_path(plan, old_context)
            try:
                old_status, old_payload = _fetch_old(args, old_path)
            except httpx.RequestError as exc:
                result = _failure_result(plan, "old_unreachable", str(exc))
                route_results.append(result)
                blockers.extend(result["issues"])
                continue

        next_path = _format_path(plan, next_context)
        next_status, next_payload = _request_next_read(client, args, next_path)

        if plan.name == "admin_list.default":
            if args.old_base_url and old_status == 200:
                old_context.update(_sample_context_from_list(old_payload))
            if next_status == 200:
                next_context.update(_sample_context_from_list(next_payload))
        if plan.name == "admin_latest_submit_debug.sample":
            if args.old_base_url and old_status == 200:
                old_context = _add_submission_context(old_context, old_payload)
            if next_status == 200:
                next_context = _add_submission_context(next_context, next_payload)

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

    fake_submit_results, fake_submit_blockers, fake_submit_skip = _run_fake_submit(args, client, next_context)
    route_results.extend(fake_submit_results)
    blockers.extend(fake_submit_blockers)
    if fake_submit_skip:
        skipped.append(fake_submit_skip)

    if args.next_testclient:
        _reset_questionnaire_state()

    return {
        "ok": not blockers,
        "mode": "dual-run" if args.old_base_url else "next-only",
        "old_base_url": args.old_base_url,
        "next_base_url": "" if args.next_testclient else args.next_base_url,
        "next_testclient": bool(args.next_testclient),
        "include_fake_submit": bool(args.include_fake_submit),
        "run_time": datetime.now(timezone.utc).isoformat(),
        "sample_questionnaire_id": next_context.get("questionnaire_id", ""),
        "sample_slug": next_context.get("slug", ""),
        "sample_submission_id": next_context.get("submission_id", ""),
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
        "# Questionnaire Readonly Gray Smoke Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- mode: `{report['mode']}`",
        f"- next: {'TestClient' if report['next_testclient'] else f'`{report['next_base_url']}`'}",
        f"- old_base_url: `{report['old_base_url'] or ''}`",
        f"- include_fake_submit: `{report['include_fake_submit']}`",
        f"- run_time: `{report['run_time']}`",
        f"- sample_questionnaire_id: `{report['sample_questionnaire_id']}`",
        f"- sample_slug: `{report['sample_slug']}`",
        f"- sample_submission_id: `{report['sample_submission_id']}`",
        f"- old_write_endpoints_executed: `{report['side_effect_safety']['old_write_endpoints_executed']}`",
        f"- old_submit_executed: `{report['side_effect_safety']['old_submit_executed']}`",
        f"- real_oauth_executed: `{report['side_effect_safety']['real_oauth_executed']}`",
        f"- wecom_tag_executed: `{report['side_effect_safety']['wecom_tag_executed']}`",
        f"- external_webhook_executed: `{report['side_effect_safety']['external_webhook_executed']}`",
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
        issue_text = "; ".join(issue.get("reason") or issue.get("rule", "issue") for issue in item.get("issues", [])) or item.get("reason", "-")
        lines.append(
            f"| {item.get('name', '-')} | {item.get('method', '-')} | `{item.get('path', '-')}` | {item.get('old_status')} | {item.get('next_status')} | {item.get('status', 'SKIPPED')} | {issue_text} |"
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
    lines.extend([f"- `{item.get('name', '-')}` `{item.get('path', '-')}`: {item.get('reason', 'skipped')}" for item in report["skipped"]] or ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI-CRM Next Questionnaire readonly gray smoke checks.")
    parser.add_argument("--old-base-url", default="", help="Optional old Flask base URL. Only GET requests are sent.")
    parser.add_argument("--next-testclient", action="store_true", help="Run against AI-CRM Next FastAPI TestClient.")
    parser.add_argument("--next-base-url", default="", help="Run read-only checks against a Next HTTP base URL.")
    parser.add_argument("--include-fake-submit", action="store_true", help="Opt in to POST submit against Next TestClient fake/in-memory questionnaire API only.")
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
    print("old_submit_executed:", report["side_effect_safety"]["old_submit_executed"])
    print("real_oauth_executed:", report["side_effect_safety"]["real_oauth_executed"])
    print("wecom_tag_executed:", report["side_effect_safety"]["wecom_tag_executed"])
    print("external_webhook_executed:", report["side_effect_safety"]["external_webhook_executed"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
