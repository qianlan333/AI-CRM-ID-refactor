export const GROUP_OPS_WORKSPACE_SCENARIOS = [
    {
        key: "group_ops",
        title: "发送链路 evidence",
        status: "sent",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "external_effect_job_97_sent",
        summary: "Group Ops 真实发送 evidence 已成立，Push Center 显示 sent；这不代表 governance 完整。",
        guardrail: "sent evidence 只能证明发送链路，不允许跳过 approval / allowlist / gray-window。",
        route: "/admin/push-center"
    },
    {
        key: "group_ops",
        title: "治理证据",
        status: "governance-missing",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "approval_allowlist_window_missing",
        summary: "独立 operator approval、receiver allowlist、gray-window 记录仍未 attach。",
        guardrail: "必须保留 requires_approval / requires_allowlist / requires_gray_window。",
        route: "/admin/business-closure"
    },
    {
        key: "ops_plan_broadcast",
        title: "编排预览",
        status: "downstream-pending",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "broadcast_job_pending",
        summary: "编排 shell 只展示 preview；下游 external effect 未执行，不能渲染为 completed。",
        guardrail: "requires_push_center / no_direct_send / no_external_call / no_production_write。",
        route: "/admin/cloud-orchestrator/plans"
    },
    {
        key: "wecom_auth",
        title: "执行配置",
        status: "external-config-blocked",
        evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
        derivedStatus: "external_config_exception",
        summary: "企微配置仍是 external-config-blocked，不进入可执行队列。",
        guardrail: "需要外部配置批准后才能进入真实授权或 callback 取证。",
        route: "/admin/business-closure"
    }
];
export const P1_GROUP_OPS_WORKSPACE_FIXTURE = {
    payload: {
        finalVerdict: "P1_READY_WITH_EXCEPTIONS",
        canClaimPass90Plus: false,
        scenarios: GROUP_OPS_WORKSPACE_SCENARIOS
    },
    leftRailItems: [
        {
            id: "plan-p1-group-ops-preview",
            label: "P1 群运营测试计划",
            kind: "plan",
            status: "governance-missing",
            summary: "计划可进入草稿编排预览，但不能发送或审批。"
        },
        {
            id: "audience-redacted-segment",
            label: "脱敏人群包",
            kind: "audience",
            status: "evidence-incomplete",
            summary: "仅用于布局占位，不包含真实 receiver 明文。"
        },
        {
            id: "task-push-center-preview",
            label: "Push Center preview",
            kind: "task",
            status: "downstream-pending",
            summary: "任务流只读预览，必须经 Push Center gate。"
        }
    ],
    workspaceMode: "draft_only_preview_only",
    dataSourceLabel: "fixture_fallback",
    dataBindingStatus: "fixture_fallback",
    realExternalCallExecuted: false,
    productionWriteExecuted: false
};
