#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicrm_next.automation_engine.parity_spec import validate_payload  # noqa: E402

Json = dict[str, Any]


@dataclass(frozen=True)
class SmokeEndpoint:
    name: str
    method: str
    path_template: str
    endpoint_name: str = ""
    old_path_template: str = ""
    payload: Json | None = None


READ_ENDPOINTS: tuple[SmokeEndpoint, ...] = (
    SmokeEndpoint("page.default", "GET", "/admin/automation-conversion", old_path_template="/admin/automation-conversion"),
    SmokeEndpoint(
        "overview.default",
        "GET",
        "/api/admin/automation-conversion/overview",
        endpoint_name="overview.default",
        old_path_template="/api/admin/automation-conversion/dashboard",
    ),
    SmokeEndpoint(
        "pools.default",
        "GET",
        "/api/admin/automation-conversion/pools",
        endpoint_name="pools.default",
        old_path_template="/api/admin/automation-conversion/dashboard",
    ),
    SmokeEndpoint(
        "members.default",
        "GET",
        "/api/admin/automation-conversion/members",
        endpoint_name="members.default",
        old_path_template="/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50",
    ),
    SmokeEndpoint(
        "member_detail.sample",
        "GET",
        "/api/admin/automation-conversion/members/{member_id}",
        endpoint_name="member_detail.default",
        old_path_template="/api/admin/automation-conversion/member?external_contact_id={external_userid}",
    ),
    SmokeEndpoint(
        "execution_records.default",
        "GET",
        "/api/admin/automation-conversion/execution-records",
        endpoint_name="execution_records.default",
        old_path_template="/api/admin/automation-conversion/executions",
    ),
)

FAKE_WRITE_ENDPOINTS: tuple[SmokeEndpoint, ...] = (
    SmokeEndpoint(
        "override_followup_type.fake",
        "POST",
        "/api/admin/automation-conversion/members/{member_id}/override-followup-type",
        payload={"followup_type": "priority", "operator": "d7_5_smoke", "reason": "fake_smoke"},
    ),
    SmokeEndpoint(
        "confirm_conversion.fake",
        "POST",
        "/api/admin/automation-conversion/members/{member_id}/confirm-conversion",
        payload={"operator": "d7_5_smoke", "reason": "fake_smoke"},
    ),
    SmokeEndpoint(
        "enter_silent.fake",
        "POST",
        "/api/admin/automation-conversion/members/{member_id}/enter-silent",
        payload={"operator": "d7_5_smoke", "reason": "fake_smoke"},
    ),
    SmokeEndpoint(
        "exit_marketing.fake",
        "POST",
        "/api/admin/automation-conversion/members/{member_id}/exit-marketing",
        payload={"operator": "d7_5_smoke", "reason": "fake_smoke"},
    ),
)

FORBIDDEN_OLD_PATH_FRAGMENTS = (
    "override-followup-type",
    "confirm-conversion",
    "enter-silent",
    "exit-marketing",
    "push-openclaw-context",
    "activation-webhook",
    "workflow",
    "agent",
)


def _build_testclient() -> Any:
    from fastapi.testclient import TestClient

    from aicrm_next.automation_engine.repo import reset_automation_fixture_state
    from aicrm_next.main import create_app

    reset_automation_fixture_state()
    return TestClient(create_app())


def _request_testclient(client: Any, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    response = client.request(method, path, json=payload if method != "GET" else None)
    try:
        body: Json | str = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


def _request_http(base_url: str, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    ensure_readonly(method, path, target="old")
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, base_url.rstrip("/") + path, json=payload if method != "GET" else None)
    try:
        body: Json | str = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


def ensure_readonly(method: str, path: str, *, target: str) -> None:
    if target == "old" and method.upper() != "GET":
        raise ValueError(f"{target} automation smoke path is not readonly: {method} {path}")
    lowered = path.lower()
    if target == "old" and any(fragment in lowered for fragment in FORBIDDEN_OLD_PATH_FRAGMENTS):
        raise ValueError(f"{target} automation smoke path is forbidden: {method} {path}")


def _sample_context_from_next_members(payload: Json | str) -> Json:
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return {}
    item = items[0] if isinstance(items[0], dict) else {}
    return {
        "member_id": str(item.get("member_id") or ""),
        "external_userid": str(item.get("external_userid") or ""),
        "mobile": str(item.get("mobile") or ""),
    }


def _sample_context_from_old_members(payload: Json | str) -> Json:
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return {}
    item = items[0] if isinstance(items[0], dict) else {}
    return {
        "member_id": str(item.get("member_id") or item.get("id") or ""),
        "external_userid": str(item.get("external_userid") or item.get("external_contact_id") or ""),
        "mobile": str(item.get("mobile") or item.get("phone") or ""),
    }


def _render(template: str, context: Json) -> str:
    path = template
    for key, value in context.items():
        path = path.replace("{" + key + "}", str(value or ""))
    return path


def _result_label(status: str) -> str:
    return status.lower()


def _skipped_route_result(plan: SmokeEndpoint, *, path: str, reason: str) -> Json:
    return {
        "name": plan.name,
        "method": plan.method,
        "path": path,
        "next_path": path,
        "old_path": "",
        "next_status": None,
        "old_status": None,
        "status": "SKIPPED",
        "result": "skipped",
        "issues": [],
        "warnings": [],
        "blockers": [],
        "skip_reason": reason,
    }


def _summary(route_results: list[Json], *, warnings: list[Json], blockers: list[Json], skipped: list[Json], legacy_drift: list[Json]) -> Json:
    route_warning_count = sum(len(item.get("warnings", [])) for item in route_results)
    route_blocker_count = sum(len(item.get("blockers", [])) for item in route_results)
    return {
        "compared": len(route_results),
        "passed": sum(1 for item in route_results if str(item.get("result") or item.get("status", "")).lower() == "pass"),
        "failed": sum(1 for item in route_results if str(item.get("result") or item.get("status", "")).lower() == "fail"),
        "skipped": len(skipped) + sum(1 for item in route_results if str(item.get("result") or item.get("status", "")).lower() == "skipped"),
        "warnings": len(warnings) + route_warning_count,
        "blockers": len(blockers) + route_blocker_count,
        "legacy_drift": len(legacy_drift),
    }


def _final_report(
    *,
    mode: str,
    sample_member_id: str,
    route_results: list[Json],
    skipped: list[Json],
    blockers: list[Json],
    warnings: list[Json],
    legacy_drift: list[Json],
) -> Json:
    summary = _summary(route_results, warnings=warnings, blockers=blockers, skipped=skipped, legacy_drift=legacy_drift)
    overall = "FAIL" if summary["blockers"] or summary["failed"] else "PASS"
    return {
        "ok": overall == "PASS",
        "overall": overall,
        "summary": summary,
        "mode": mode,
        "sample_member_id": sample_member_id,
        "route_results": route_results,
        "results": route_results,
        "skipped": skipped,
        "blockers": blockers,
        "warnings": warnings,
        "legacy_drift": legacy_drift,
        "side_effect_safety": _side_effect_safety(),
    }


def _result_for_plan(
    plan: SmokeEndpoint,
    *,
    next_path: str,
    next_status: int,
    next_payload: Json | str,
    old_path: str = "",
    old_status: int | None = None,
    old_payload: Json | str | None = None,
) -> tuple[Json, list[Json], list[Json], list[Json]]:
    blockers: list[Json] = []
    warnings: list[Json] = []
    legacy_drift: list[Json] = []
    issues: list[Json] = []
    if next_status >= 500:
        issues.append({"reason": "next_5xx", "severity": "blocker", "status_code": next_status})
    if next_status != 200:
        issues.append({"reason": "next_unexpected_status", "severity": "blocker", "status_code": next_status})
    if plan.endpoint_name and isinstance(next_payload, dict):
        validation = validate_payload(plan.endpoint_name, next_payload)
        if validation:
            issues.extend({"reason": "next_missing_required_contract", "severity": "blocker", "details": item} for item in validation)
    elif plan.endpoint_name:
        issues.append({"reason": "next_missing_required_contract", "severity": "blocker", "details": {"rule": "payload_not_object"}})
    if old_status is not None and old_status != 200 and next_status == 200 and not any(item["severity"] == "blocker" for item in issues):
        warning = {
            "reason": "legacy_missing_read_route",
            "name": plan.name,
            "old_path": old_path,
            "old_status": old_status,
            "next_satisfies_contract": True,
        }
        warnings.append(warning)
        legacy_drift.append(warning)
    for issue in issues:
        if issue["severity"] == "blocker":
            blockers.append({"reason": issue["reason"], "name": plan.name, "path": next_path, "details": issue.get("details", {})})
    status = "FAIL" if blockers else "WARN" if warnings else "PASS"
    return (
        {
            "name": plan.name,
            "method": plan.method,
            "path": next_path,
            "next_path": next_path,
            "old_path": old_path,
            "next_status": next_status,
            "old_status": old_status,
            "status": status,
            "result": _result_label(status),
            "issues": issues,
            "warnings": warnings,
            "blockers": blockers,
            "skip_reason": "",
        },
        blockers,
        warnings,
        legacy_drift,
    )


def _side_effect_safety() -> Json:
    return {
        "old_write_endpoints_executed": False,
        "manual_override_executed": False,
        "confirm_conversion_executed": False,
        "openclaw_push_executed": False,
        "wecom_dispatch_executed": False,
        "external_webhook_executed": False,
        "activation_webhook_executed": False,
        "workflow_runtime_executed": False,
        "agent_runtime_executed": False,
        "real_traffic_cutover_executed": False,
        "production_config_modified": False,
        "real_automation_write_executed": False,
        "real_activation_webhook_executed": False,
        "real_openclaw_push_executed": False,
        "real_workflow_runtime_executed": False,
        "real_agent_runtime_executed": False,
        "real_external_webhook_executed": False,
        "note": "Automation smoke defaults to readonly GET endpoints. Fake writes require explicit TestClient mode and never include OpenClaw or activation webhook paths.",
    }


def _request_next(args: argparse.Namespace, client: Any | None, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    if args.next_testclient:
        return _request_testclient(client, method, path, payload)
    return _request_http(args.next_base_url, method, path, payload)


def run_smoke(args: argparse.Namespace) -> Json:
    client = _build_testclient() if args.next_testclient else None
    route_results: list[Json] = []
    skipped: list[Json] = []
    blockers: list[Json] = []
    warnings: list[Json] = []
    legacy_drift: list[Json] = []
    context: Json = {}
    old_context: Json = {}

    if getattr(args, "include_fake_writes", False) and not args.next_testclient:
        blockers.append({"reason": "fake_writes_require_next_testclient"})
        return _final_report(
            mode="next_http",
            sample_member_id="",
            route_results=route_results,
            skipped=skipped,
            blockers=blockers,
            warnings=warnings,
            legacy_drift=legacy_drift,
        )

    for plan in READ_ENDPOINTS:
        if plan.name == "member_detail.sample" and not context.get("member_id"):
            skipped.append({"name": plan.name, "reason": "missing_member_id"})
            route_results.append(_skipped_route_result(plan, path=_render(plan.path_template, context), reason="missing_member_id"))
            continue
        next_path = _render(plan.path_template, context)
        next_status, next_payload = _request_next(args, client, plan.method, next_path)
        old_status: int | None = None
        old_payload: Json | str | None = None
        old_path = ""
        if getattr(args, "old_base_url", ""):
            old_path = _render(plan.old_path_template or plan.path_template, old_context or context)
            old_status, old_payload = _request_http(args.old_base_url, plan.method, old_path)
            if plan.name == "members.default":
                old_context = _sample_context_from_old_members(old_payload)
        result, item_blockers, item_warnings, item_drift = _result_for_plan(
            plan,
            next_path=next_path,
            next_status=next_status,
            next_payload=next_payload,
            old_path=old_path,
            old_status=old_status,
            old_payload=old_payload,
        )
        route_results.append(result)
        blockers.extend(item_blockers)
        warnings.extend(item_warnings)
        legacy_drift.extend(item_drift)
        if plan.name == "members.default":
            context = _sample_context_from_next_members(next_payload)

    if not getattr(args, "include_fake_writes", False):
        skipped.append({"name": "fake_writes", "reason": "fake_writes_not_requested"})
    elif args.next_testclient:
        if not context.get("member_id"):
            skipped.append({"name": "fake_writes", "reason": "missing_member_id"})
        else:
            for plan in FAKE_WRITE_ENDPOINTS:
                path = _render(plan.path_template, context)
                status, payload = _request_testclient(client, plan.method, path, plan.payload)
                ok = status == 200 and isinstance(payload, dict) and bool(payload.get("ok"))
                if not ok:
                    blockers.append({"reason": "fake_write_failed", "name": plan.name, "status_code": status})
                route_results.append(
                    {
                        "name": plan.name,
                        "method": plan.method,
                        "path": path,
                        "next_path": path,
                        "next_status": status,
                        "status": "PASS" if ok else "FAIL",
                        "result": "pass" if ok else "fail",
                        "issues": [] if ok else [{"reason": "fake_write_failed", "severity": "blocker"}],
                        "warnings": [],
                        "blockers": [] if ok else [{"reason": "fake_write_failed", "name": plan.name, "path": path, "status_code": status}],
                        "skip_reason": "",
                    }
                )

    return _final_report(
        mode="next_testclient" if args.next_testclient else "next_http",
        sample_member_id=context.get("member_id", ""),
        route_results=route_results,
        skipped=skipped,
        blockers=blockers,
        warnings=warnings,
        legacy_drift=legacy_drift,
    )


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Automation Readonly Gray Smoke",
        "",
        f"- overall: {report['overall']}",
        f"- mode: {report['mode']}",
        f"- sample_member_id: {report.get('sample_member_id') or '-'}",
        f"- summary: {json.dumps(report.get('summary', {}), ensure_ascii=False)}",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- `{item['reason']}`: {json.dumps(item, ensure_ascii=False)}" for item in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Legacy Drift",
            "",
        ]
    )
    if report["legacy_drift"]:
        lines.extend(f"- `{item['reason']}`: {json.dumps(item, ensure_ascii=False)}" for item in report["legacy_drift"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Side Effect Safety",
            "",
        ]
    )
    for key, value in report["side_effect_safety"].items():
        lines.append(f"- `{key}`: {str(value).lower() if isinstance(value, bool) else value}")
    lines.extend(
        [
            "",
            "## Routes",
            "",
            "| name | method | path | status | issues |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["route_results"]:
        issues = "; ".join(issue.get("reason", issue.get("rule", "issue")) for issue in item.get("issues", [])) or "-"
        lines.append(f"| {item['name']} | {item['method']} | `{item['path']}` | {item['status']} | {issues} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI-CRM Next automation readonly/fake gray smoke.")
    parser.add_argument("--old-base-url", default="")
    parser.add_argument("--next-base-url", default="")
    parser.add_argument("--next-testclient", action="store_true")
    parser.add_argument("--include-fake-writes", action="store_true")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.next_testclient and not args.next_base_url:
        raise SystemExit("next-base-url or next-testclient is required")
    report = run_smoke(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
