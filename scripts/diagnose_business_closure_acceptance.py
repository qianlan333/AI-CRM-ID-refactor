#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


SCENARIOS: dict[str, dict[str, Any]] = {
    "group_ops_gray_send": {
        "title": "Group Ops gray send acceptance",
        "capability_owner": "automation_engine",
        "routes": [
            "/api/automation/group-ops/webhooks/{webhook_key}",
            "/api/admin/push-center/jobs/{job_id}/reconciliation",
        ],
        "required_env": ["AICRM_GROUP_OPS_GRAY_SEND_APPROVED", "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST"],
        "checks": [
            "dry-run plan exists before real receiver execution",
            "receiver is allowlisted before any real send",
            "Push Center reconciliation can explain job/effect/attempt status",
        ],
        "success_criteria": "Approved receiver gray send can be reconciled in Push Center.",
    },
    "ops_plan_to_broadcast": {
        "title": "Ops plan approval to broadcast E2E acceptance",
        "capability_owner": "platform_foundation",
        "routes": [
            "/api/admin/internal-events/{event_id}/reconciliation",
            "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve",
            "/api/admin/push-center/jobs",
        ],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN"],
        "checks": [
            "approval event creates or reuses one internal_event",
            "consumer run creates or links one business job",
            "duplicate approval does not duplicate jobs",
        ],
        "success_criteria": "Approval can be traced to consumer run, job, and Push Center status.",
    },
    "external_orders_enablement": {
        "title": "External orders enablement acceptance",
        "capability_owner": "commerce",
        "routes": ["/api/external/orders", "/api/external/orders/{order_no}"],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN"],
        "checks": [
            "missing server token remains controlled unavailable",
            "missing or wrong bearer token is rejected",
            "correct bearer token can read local order projection",
        ],
        "success_criteria": "External systems can safely authenticate and read local order state.",
    },
    "external_orders": {
        "title": "External orders enablement acceptance",
        "capability_owner": "commerce",
        "routes": ["/api/external/orders", "/api/external/orders/{order_no}"],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN"],
        "checks": [
            "missing server token remains controlled unavailable",
            "missing or wrong bearer token is rejected",
            "correct bearer token can read local order projection",
        ],
        "success_criteria": "External systems can safely authenticate and read local order state.",
    },
    "external_orders_gray": {
        "title": "External orders gray acceptance",
        "capability_owner": "commerce",
        "routes": [
            "/api/external/orders",
            "/api/admin/wechat-shop/orders/{order_id}/sync",
            "/api/admin/push-center/jobs/{job_id}/reconciliation",
        ],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN", "AICRM_EXTERNAL_ORDERS_GRAY_APPROVED"],
        "checks": [
            "gray source is approved before live order calls",
            "duplicate order payload is idempotent",
            "order/customer/channel/source correlation is visible",
        ],
        "success_criteria": "Gray order lifecycle can be reconciled without leaking token or customer data.",
    },
    "wecom_auth_operator": {
        "title": "WeCom auth operator readiness acceptance",
        "capability_owner": "auth_wecom",
        "routes": ["/auth/wecom/start", "/auth/wecom/callback"],
        "required_env": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "ADMIN_LOGIN_REDIRECT_URI"],
        "checks": [
            "auth start route is reachable",
            "missing code and invalid state are controlled failures",
            "token exchange remains blocked unless separately approved",
        ],
        "success_criteria": "Operator auth readiness is explainable without exposing secrets.",
    },
    "wecom_callback_gray": {
        "title": "WeCom callback gray acceptance",
        "capability_owner": "channel_entry",
        "routes": ["/wecom/external-contact/callback", "/api/wecom/events"],
        "required_env": ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET", "AICRM_WECOM_CALLBACK_GRAY_APPROVED"],
        "checks": [
            "invalid signature does not enqueue work",
            "duplicate callback reuses idempotency key",
            "accepted callback can be traced to event/job status",
        ],
        "success_criteria": "Gray callback can be verified, deduplicated, and reconciled.",
    },
    "core_admin_ops": {
        "title": "Core CRM admin operations acceptance",
        "capability_owner": "automation_engine",
        "routes": ["/admin/channels", "/api/admin/channels/{channel_id:int}", "/api/admin/channels/runtime-diagnosis"],
        "required_env": [],
        "checks": [
            "old draft #974 is closed or rebuilt from current main",
            "channel save errors expose FastAPI detail",
            "static asset cache behavior is covered before channel UX work ships",
        ],
        "success_criteria": "Operators can save and diagnose critical admin channel state.",
    },
}


def _present(env: dict[str, str], key: str) -> bool:
    return bool(str(env.get(key) or "").strip())


def _missing_env(env: dict[str, str], keys: list[str]) -> list[str]:
    return [key for key in keys if not _present(env, key)]


def _csv(value: str) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _value_or_not_provided(value: str) -> str:
    return str(value or "").strip() or "not_provided"


def _group_ops_blocking_reasons(env: dict[str, str], *, receiver_token: str) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if not _present(env, "AICRM_GROUP_OPS_GRAY_SEND_APPROVED"):
        reasons.append(
            {
                "code": "missing_operator_approval",
                "message": "AICRM_GROUP_OPS_GRAY_SEND_APPROVED must be configured before gray execution readiness.",
            }
        )
    if not _present(env, "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST"):
        reasons.append(
            {
                "code": "missing_receiver_allowlist",
                "message": "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST must contain the approved test receiver token.",
            }
        )
    if not str(receiver_token or "").strip():
        reasons.append(
            {
                "code": "missing_receiver_token",
                "message": "--receiver-token is required for operator execution readiness.",
            }
        )
    elif _present(env, "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST") and str(receiver_token).strip() not in _csv(
        env.get("AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST", "")
    ):
        reasons.append(
            {
                "code": "receiver_not_allowlisted",
                "message": "The supplied receiver token is not present in AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST.",
            }
        )
    return reasons


def _generic_blocking_reasons(missing_env: list[str], *, receiver_required: bool, receiver_token: str) -> list[dict[str, str]]:
    reasons = [
        {"code": "missing_required_env", "message": f"{key} is required before operator execution readiness."}
        for key in missing_env
    ]
    if receiver_required and not str(receiver_token or "").strip():
        reasons.append({"code": "missing_receiver_token", "message": "--receiver-token is required for this gray scenario."})
    return reasons


def _group_ops_evidence(
    *,
    plan_id: str,
    event_id: str,
    effect_job_id: str,
    attempt_id: str,
    push_center_job_id: str,
    operator_execute_allowed: bool,
    blocking_reasons: list[dict[str, str]],
) -> dict[str, Any]:
    push_center_status = "ready_for_operator_reconciliation" if operator_execute_allowed else "not_collected"
    return {
        "evidence_status": "READY_FOR_OPERATOR_COLLECTION" if operator_execute_allowed else "READINESS_ONLY",
        "plan_id": _value_or_not_provided(plan_id),
        "event_id": _value_or_not_provided(event_id),
        "effect_job_id": _value_or_not_provided(effect_job_id),
        "attempt_id": _value_or_not_provided(attempt_id),
        "push_center_job_id": _value_or_not_provided(push_center_job_id),
        "push_center_status": push_center_status,
        "push_center_reconciliation_route": (
            "/api/admin/push-center/jobs/{job_id}/reconciliation"
            if not push_center_job_id
            else f"/api/admin/push-center/jobs/{push_center_job_id}/reconciliation"
        ),
        "retryable": False,
        "operator_action_required": bool(blocking_reasons),
        "business_explanation": (
            "Gray-send readiness checks passed; collect real job/effect/attempt evidence only during an approved operator run."
            if operator_execute_allowed
            else "Gray-send evidence is readiness-only until approval, receiver allowlist, and receiver token checks pass."
        ),
        "next_action_label": "Collect Push Center reconciliation" if operator_execute_allowed else "Resolve blocking reasons",
    }


def _ops_plan_e2e_evidence(
    *,
    plan_id: str,
    approval_event_id: str,
    internal_event_id: str,
    consumer_run_id: str,
    broadcast_job_id: str,
    effect_job_id: str,
    push_center_job_id: str,
    approval_status: str,
    consumer_status: str,
    duplicate_handling: str,
) -> dict[str, Any]:
    approval_state = str(approval_status or "").strip().lower()
    consumer_state = str(consumer_status or "").strip().lower()
    blocking_reasons: list[dict[str, str]] = []
    retryable = False
    operator_action_required = False
    pending_reason = ""
    derived_status = "readiness_only"
    business_explanation = "Ops plan evidence is readiness-only until plan, approval, event, consumer, and job identifiers are attached."
    next_action_label = "Attach plan evidence"

    if not str(plan_id or "").strip():
        blocking_reasons.append({"code": "missing_plan_id", "message": "--plan-id is required to trace an ops plan approval E2E."})
        derived_status = "missing_plan_id"
        pending_reason = "plan_id_not_provided"
    elif approval_state in {"", "pending", "not_approved", "draft", "waiting_approval"}:
        derived_status = "pending_approval"
        pending_reason = "plan_not_approved"
        operator_action_required = True
        business_explanation = "Plan exists in the evidence request but is not approved yet; no downstream internal event or job should be claimed."
        next_action_label = "Approve plan or attach approval evidence"
    elif not str(internal_event_id or "").strip():
        derived_status = "missing_internal_event"
        pending_reason = "approval_without_internal_event_evidence"
        operator_action_required = True
        business_explanation = "Approval evidence is present, but no internal_event id was attached; event creation/reuse still needs proof."
        next_action_label = "Attach internal_event reconciliation"
    elif not str(consumer_run_id or "").strip():
        derived_status = "consumer_pending"
        pending_reason = "internal_event_has_no_consumer_run_evidence"
        operator_action_required = False
        business_explanation = "Internal event evidence is present, but no consumer run was attached; wait for or inspect consumer execution."
        next_action_label = "Collect consumer run"
    elif consumer_state in {"failed_retryable", "blocked"}:
        derived_status = "consumer_failed"
        pending_reason = consumer_state
        retryable = True
        operator_action_required = True
        business_explanation = "Consumer evidence indicates a retryable or blocked failure; retry or operator action is required."
        next_action_label = "Retry consumer"
    elif consumer_state in {"failed", "failed_terminal"}:
        derived_status = "consumer_failed"
        pending_reason = consumer_state
        retryable = False
        operator_action_required = True
        business_explanation = "Consumer evidence indicates a terminal failure; manual investigation is required before claiming E2E completion."
        next_action_label = "Manual investigation"
    elif consumer_state == "succeeded" and (str(broadcast_job_id or "").strip() or str(effect_job_id or "").strip()):
        derived_status = "job_linked"
        business_explanation = "Consumer succeeded and a broadcast or external effect job id is attached; collect Push Center reconciliation next."
        next_action_label = "Collect Push Center reconciliation"
    elif consumer_state == "succeeded":
        derived_status = "missing_business_job"
        pending_reason = "consumer_succeeded_without_job_evidence"
        operator_action_required = True
        business_explanation = "Consumer succeeded, but no broadcast_job or external_effect_job id was attached; job creation still needs proof."
        next_action_label = "Attach generated job"
    else:
        derived_status = "consumer_pending"
        pending_reason = consumer_state or "consumer_status_not_provided"
        business_explanation = "Consumer evidence is incomplete; attach consumer status and generated job evidence before E2E completion."
        next_action_label = "Attach consumer status"

    return {
        "evidence_status": "READINESS_ONLY" if blocking_reasons or derived_status != "job_linked" else "E2E_EVIDENCE_ATTACHED",
        "plan_id": _value_or_not_provided(plan_id),
        "approval_event_id": _value_or_not_provided(approval_event_id),
        "internal_event_id": _value_or_not_provided(internal_event_id),
        "consumer_run_id": _value_or_not_provided(consumer_run_id),
        "broadcast_job_id": _value_or_not_provided(broadcast_job_id),
        "external_effect_job_id": _value_or_not_provided(effect_job_id),
        "push_center_job_id": _value_or_not_provided(push_center_job_id),
        "derived_status": derived_status,
        "pending_reason": pending_reason or "not_applicable",
        "retryable": retryable,
        "operator_action_required": operator_action_required,
        "business_explanation": business_explanation,
        "next_action_label": next_action_label,
        "duplicate_handling": str(duplicate_handling or "").strip() or "not_collected",
        "push_center_reconciliation_route": (
            "/api/admin/push-center/jobs/{job_id}/reconciliation"
            if not push_center_job_id
            else f"/api/admin/push-center/jobs/{push_center_job_id}/reconciliation"
        ),
        "blocking_reasons": blocking_reasons,
    }


def _external_orders_request_mode(*, token_configured: bool, request_token: str, request_mode: str, env_token: str) -> str:
    explicit = str(request_mode or "").strip().lower()
    if explicit:
        return explicit
    if not token_configured:
        return "dry_run"
    if not str(request_token or "").strip():
        return "no_token"
    if str(request_token).strip() != str(env_token or "").strip():
        return "wrong_token"
    return "valid_token"


def _visible_admin_order(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "yes", "1", "visible", "found", "linked"}


def _external_orders_evidence(
    *,
    env: dict[str, str],
    request_token: str,
    request_mode: str,
    order_no: str,
    external_order_id: str,
    idempotency_key: str,
    customer_id: str,
    channel_id: str,
    source: str,
    internal_event_id: str,
    admin_order_visibility: str,
) -> dict[str, Any]:
    server_token = str(env.get("AUTOMATION_INTERNAL_API_TOKEN") or "").strip()
    token_configured = bool(server_token)
    mode = _external_orders_request_mode(
        token_configured=token_configured,
        request_token=request_token,
        request_mode=request_mode,
        env_token=server_token,
    )
    blocking_reasons: list[dict[str, str]] = []

    if not token_configured:
        blocking_reasons.append(
            {
                "code": "missing_internal_token_config",
                "message": "AUTOMATION_INTERNAL_API_TOKEN is not configured; external order routes should stay controlled-disabled.",
            }
        )
    elif mode == "no_token":
        blocking_reasons.append(
            {
                "code": "missing_request_token",
                "message": "Attach a redacted request-token check before claiming external order API readiness.",
            }
        )
    elif mode == "wrong_token":
        blocking_reasons.append(
            {
                "code": "invalid_request_token",
                "message": "The request token does not match the configured internal token; expect an auth rejection.",
            }
        )

    order_attached = bool(str(order_no or "").strip() or str(external_order_id or "").strip())
    idempotency_attached = bool(str(idempotency_key or "").strip())
    customer_channel_attached = all(str(value or "").strip() for value in [customer_id, channel_id, source])
    event_attached = bool(str(internal_event_id or "").strip())
    admin_visible = _visible_admin_order(admin_order_visibility)
    evidence_complete = bool(order_attached and idempotency_attached and customer_channel_attached and event_attached and admin_visible)

    if token_configured and mode == "valid_token" and not evidence_complete:
        blocking_reasons.append(
            {
                "code": "token_configured_but_not_executed",
                "message": "Valid token readiness is present, but this diagnostic is dry-run and cannot claim order linkage without evidence ids.",
            }
        )
    if not order_attached:
        blocking_reasons.append(
            {
                "code": "missing_order_evidence",
                "message": "Attach order_id or external_order_id evidence from the external order acceptance run.",
            }
        )
    if not idempotency_attached:
        blocking_reasons.append(
            {
                "code": "missing_idempotency_evidence",
                "message": "Attach the idempotency key or duplicate-order evidence before claiming order readiness.",
            }
        )
    if not customer_channel_attached:
        blocking_reasons.append(
            {
                "code": "missing_customer_channel_link",
                "message": "Attach customer_id, channel_id, and source correlation evidence.",
            }
        )
    if not event_attached:
        blocking_reasons.append(
            {
                "code": "missing_internal_event",
                "message": "Attach the internal_event id created or reused by the order flow.",
            }
        )
    if not admin_visible:
        blocking_reasons.append(
            {
                "code": "missing_admin_visibility",
                "message": "Attach admin order visibility evidence from the order page or diagnostic payload.",
            }
        )

    derived_status = "order_linked" if token_configured and mode == "valid_token" and evidence_complete else (
        "controlled_disabled" if not token_configured else "readiness_only"
    )
    auth_status = {
        "dry_run": "not_executed",
        "no_token": "missing_request_token",
        "wrong_token": "invalid_request_token",
        "valid_token": "valid_token_readiness",
    }.get(mode, "not_executed")
    if not token_configured:
        auth_status = "controlled_disabled"

    if derived_status == "order_linked":
        blocking_reasons = [{"code": "order_linked", "message": "Order, idempotency, customer/channel/source, event, and admin visibility evidence are attached."}]

    return {
        "evidence_status": "ORDER_LINKED_EVIDENCE_ATTACHED" if derived_status == "order_linked" else "READINESS_ONLY",
        "token_configured": token_configured,
        "token_redacted": True,
        "token_never_logged": True,
        "auth_status": auth_status,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "controlled_disabled_reason": "AUTOMATION_INTERNAL_API_TOKEN not configured" if not token_configured else "",
        "request_mode": mode,
        "order_id": _value_or_not_provided(order_no),
        "external_order_id": _value_or_not_provided(external_order_id),
        "idempotency_key": _value_or_not_provided(idempotency_key),
        "customer_id": _value_or_not_provided(customer_id),
        "channel_id": _value_or_not_provided(channel_id),
        "source": _value_or_not_provided(source),
        "internal_event_id": _value_or_not_provided(internal_event_id),
        "admin_order_visibility": _value_or_not_provided(admin_order_visibility),
        "reconciliation_status": derived_status,
        "derived_status": derived_status,
        "retryable": False,
        "operator_action_required": derived_status != "order_linked",
        "business_explanation": (
            "External order evidence is linked and ready for operator review without exposing token or customer secrets."
            if derived_status == "order_linked"
            else "External order acceptance remains readiness-only until token, order, idempotency, customer/channel/source, event, and admin visibility evidence are attached."
        ),
        "next_action_label": "Attach final evidence report" if derived_status == "order_linked" else "Resolve external order blocking reasons",
        "real_external_call_executed": False,
        "production_write_executed": False,
        "blocking_reasons": blocking_reasons,
    }


def _scenario_payload(
    name: str,
    *,
    execute: bool = False,
    receiver_token: str = "",
    request_token: str = "",
    request_mode: str = "",
    order_no: str = "",
    external_order_id: str = "",
    idempotency_key: str = "",
    customer_id: str = "",
    channel_id: str = "",
    source: str = "",
    admin_order_visibility: str = "",
    plan_id: str = "",
    event_id: str = "",
    effect_job_id: str = "",
    attempt_id: str = "",
    push_center_job_id: str = "",
    approval_event_id: str = "",
    internal_event_id: str = "",
    consumer_run_id: str = "",
    broadcast_job_id: str = "",
    approval_status: str = "",
    consumer_status: str = "",
    duplicate_handling: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(env or os.environ)
    spec = SCENARIOS[name]
    missing = _missing_env(env, list(spec["required_env"]))
    requires_receiver = name in {"group_ops_gray_send", "wecom_callback_gray"}
    if name == "group_ops_gray_send":
        blocking_reasons = _group_ops_blocking_reasons(env, receiver_token=receiver_token)
    else:
        blocking_reasons = _generic_blocking_reasons(missing, receiver_required=requires_receiver, receiver_token=receiver_token)
    execute_allowed = bool(execute and not blocking_reasons)
    unsafe_execute_requested = bool(execute and not execute_allowed)
    status = "blocked" if unsafe_execute_requested else ("ready_for_operator_execute" if execute_allowed else "dry_run_ready")
    payload = {
        "ok": not unsafe_execute_requested,
        "scenario": name,
        "title": spec["title"],
        "capability_owner": spec["capability_owner"],
        "dry_run": not execute_allowed,
        "execute_requested": bool(execute),
        "operator_execute_allowed": execute_allowed,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
        "status": status,
        "routes": list(spec["routes"]),
        "blocking_reasons": blocking_reasons if unsafe_execute_requested else [],
        "required_env": [
            {"key": key, "configured": _present(env, key), "value": "[redacted]" if _present(env, key) else ""}
            for key in spec["required_env"]
        ],
        "missing_env": missing,
        "inputs": {
            "receiver_token_configured": bool(receiver_token),
            "receiver_token": "[redacted]" if receiver_token else "",
            "request_token_configured": bool(request_token),
            "request_token": "[redacted]" if request_token else "",
            "request_mode": request_mode,
            "order_no": order_no,
            "external_order_id": external_order_id,
            "idempotency_key": idempotency_key,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "source": source,
            "admin_order_visibility": admin_order_visibility,
            "plan_id": plan_id,
            "event_id": event_id,
            "effect_job_id": effect_job_id,
            "attempt_id": attempt_id,
            "push_center_job_id": push_center_job_id,
            "approval_event_id": approval_event_id,
            "internal_event_id": internal_event_id,
            "consumer_run_id": consumer_run_id,
            "broadcast_job_id": broadcast_job_id,
            "approval_status": approval_status,
            "consumer_status": consumer_status,
            "duplicate_handling": duplicate_handling,
        },
        "redaction_policy": {
            "receiver_token": "redacted",
            "receiver_allowlist": "redacted",
            "token_secret_external_userid": "must_not_be_committed",
        },
        "checks": list(spec["checks"]),
        "success_criteria": spec["success_criteria"],
        "next_action": _next_action(name, unsafe_execute_requested, execute_allowed),
    }
    if name == "group_ops_gray_send":
        payload["operator_evidence"] = _group_ops_evidence(
            plan_id=plan_id,
            event_id=event_id,
            effect_job_id=effect_job_id,
            attempt_id=attempt_id,
            push_center_job_id=push_center_job_id,
            operator_execute_allowed=execute_allowed,
            blocking_reasons=blocking_reasons,
        )
    if name == "ops_plan_to_broadcast":
        evidence = _ops_plan_e2e_evidence(
            plan_id=plan_id,
            approval_event_id=approval_event_id,
            internal_event_id=internal_event_id or event_id,
            consumer_run_id=consumer_run_id,
            broadcast_job_id=broadcast_job_id,
            effect_job_id=effect_job_id,
            push_center_job_id=push_center_job_id,
            approval_status=approval_status,
            consumer_status=consumer_status,
            duplicate_handling=duplicate_handling,
        )
        payload["e2e_evidence"] = evidence
        payload["blocking_reasons"] = list(evidence["blocking_reasons"])
        payload["status"] = evidence["derived_status"]
    if name in {"external_orders", "external_orders_enablement", "external_orders_gray"}:
        evidence = _external_orders_evidence(
            env=env,
            request_token=request_token,
            request_mode=request_mode,
            order_no=order_no,
            external_order_id=external_order_id,
            idempotency_key=idempotency_key,
            customer_id=customer_id,
            channel_id=channel_id,
            source=source,
            internal_event_id=internal_event_id or event_id,
            admin_order_visibility=admin_order_visibility,
        )
        payload["external_orders_evidence"] = evidence
        payload["blocking_reasons"] = list(evidence["blocking_reasons"])
        payload["status"] = evidence["derived_status"]
    return payload


def _next_action(name: str, unsafe_execute_requested: bool, execute_allowed: bool) -> str:
    if unsafe_execute_requested:
        return "Resolve missing approval/env/receiver inputs before any operator execution."
    if execute_allowed:
        return "Run the documented operator-owned gray acceptance steps; this diagnostic script still performs no external call."
    if name == "core_admin_ops":
        return "Close or rebuild #974 from current main before channel admin UX fixes."
    return "Attach this dry-run payload to the next acceptance PR and keep real execution disabled."


def run(
    *,
    scenario: str,
    execute: bool = False,
    receiver_token: str = "",
    request_token: str = "",
    request_mode: str = "",
    order_no: str = "",
    external_order_id: str = "",
    idempotency_key: str = "",
    customer_id: str = "",
    channel_id: str = "",
    source: str = "",
    admin_order_visibility: str = "",
    plan_id: str = "",
    event_id: str = "",
    effect_job_id: str = "",
    attempt_id: str = "",
    push_center_job_id: str = "",
    approval_event_id: str = "",
    internal_event_id: str = "",
    consumer_run_id: str = "",
    broadcast_job_id: str = "",
    approval_status: str = "",
    consumer_status: str = "",
    duplicate_handling: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    names = list(SCENARIOS) if scenario == "all" else [scenario]
    items = [
        _scenario_payload(
            name,
            execute=execute,
            receiver_token=receiver_token,
            request_token=request_token,
            request_mode=request_mode,
            order_no=order_no,
            external_order_id=external_order_id,
            idempotency_key=idempotency_key,
            customer_id=customer_id,
            channel_id=channel_id,
            source=source,
            admin_order_visibility=admin_order_visibility,
            plan_id=plan_id,
            event_id=event_id,
            effect_job_id=effect_job_id,
            attempt_id=attempt_id,
            push_center_job_id=push_center_job_id,
            approval_event_id=approval_event_id,
            internal_event_id=internal_event_id,
            consumer_run_id=consumer_run_id,
            broadcast_job_id=broadcast_job_id,
            approval_status=approval_status,
            consumer_status=consumer_status,
            duplicate_handling=duplicate_handling,
            env=env,
        )
        for name in names
    ]
    return {
        "ok": all(item["ok"] for item in items),
        "scenario": scenario,
        "items": items,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run business closure acceptance diagnostics.")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS.keys()], default="all")
    parser.add_argument("--execute", action="store_true", help="Request operator execution readiness; the script still performs no external call.")
    parser.add_argument("--receiver-token", default="")
    parser.add_argument("--request-token", default="")
    parser.add_argument("--request-mode", choices=["dry_run", "no_token", "wrong_token", "valid_token"], default="")
    parser.add_argument("--order-no", default="")
    parser.add_argument("--external-order-id", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--customer-id", default="")
    parser.add_argument("--channel-id", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--admin-order-visibility", default="")
    parser.add_argument("--plan-id", default="")
    parser.add_argument("--event-id", default="")
    parser.add_argument("--effect-job-id", default="")
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--push-center-job-id", default="")
    parser.add_argument("--approval-event-id", default="")
    parser.add_argument("--internal-event-id", default="")
    parser.add_argument("--consumer-run-id", default="")
    parser.add_argument("--broadcast-job-id", default="")
    parser.add_argument("--approval-status", default="")
    parser.add_argument("--consumer-status", default="")
    parser.add_argument("--duplicate-handling", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run(
        scenario=args.scenario,
        execute=bool(args.execute),
        receiver_token=args.receiver_token,
        request_token=args.request_token,
        request_mode=args.request_mode,
        order_no=args.order_no,
        external_order_id=args.external_order_id,
        idempotency_key=args.idempotency_key,
        customer_id=args.customer_id,
        channel_id=args.channel_id,
        source=args.source,
        admin_order_visibility=args.admin_order_visibility,
        plan_id=args.plan_id,
        event_id=args.event_id,
        effect_job_id=args.effect_job_id,
        attempt_id=args.attempt_id,
        push_center_job_id=args.push_center_job_id,
        approval_event_id=args.approval_event_id,
        internal_event_id=args.internal_event_id,
        consumer_run_id=args.consumer_run_id,
        broadcast_job_id=args.broadcast_job_id,
        approval_status=args.approval_status,
        consumer_status=args.consumer_status,
        duplicate_handling=args.duplicate_handling,
    )
    print_json(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
