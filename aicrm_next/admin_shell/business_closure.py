from __future__ import annotations

from typing import Any


def business_closure_payload() -> dict[str, Any]:
    return {
        "finalVerdict": "P1_READY_WITH_EXCEPTIONS",
        "canClaimPass90Plus": False,
        "scenarios": [
            {
                "key": "external_orders",
                "title": "External Orders",
                "status": "ready",
                "evidenceStatus": "EVIDENCE_COLLECTED",
                "derivedStatus": "order_linked",
                "summary": "订单、internal event、customer projection 和 Push Center 证据已收集。",
                "guardrail": "继续展示 order_linked / reconciliation，不渲染为全局 PASS_90_PLUS。",
                "route": "/admin/orders",
            },
            {
                "key": "ops_plan_broadcast",
                "title": "Ops Plan -> Broadcast",
                "status": "downstream-pending",
                "evidenceStatus": "EVIDENCE_COLLECTED",
                "derivedStatus": "push_center_pending",
                "summary": "Next-native cloud_plan 已到 broadcast_job / Push Center pending。",
                "guardrail": "展示 downstream pending，不伪装成 sent 或 completed。",
                "route": "/admin/push-center",
            },
            {
                "key": "group_ops",
                "title": "Group Ops / Push Center",
                "status": "governance-missing",
                "evidenceStatus": "EVIDENCE_COLLECTED",
                "derivedStatus": "sent_with_governance_residual_risk",
                "summary": "真实 external effect 已 sent，但 approval / allowlist / gray-window 佐证未 attach。",
                "guardrail": "展示 governance_missing / evidence_incomplete，不把发送成功等同治理完成。",
                "route": "/admin/automation-conversion/group-ops/ui",
            },
            {
                "key": "wecom_auth",
                "title": "WeCom Auth / Callback",
                "status": "external-config-blocked",
                "evidenceStatus": "BLOCKED_CONFIG_NOT_APPROVED",
                "derivedStatus": "external_config_exception",
                "summary": "Next routes fail-closed；git-external WeCom 配置 / callback evidence 未生效。",
                "guardrail": "展示 external-config-blocked，不假装企微授权已完成。",
                "route": "/admin/channels",
            },
        ],
    }
