import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "./workspace_fixture.js";
function text(value) {
    return String(value ?? "").trim();
}
function intValue(value) {
    const parsed = Number.parseInt(text(value), 10);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}
function asRecord(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function asArray(value) {
    return Array.isArray(value) ? value : [];
}
function normalizePlanStatus(rawStatus) {
    const status = text(rawStatus).toLowerCase();
    if (status === "active" || status === "enabled")
        return "ready";
    if (status === "disabled" || status === "paused")
        return "blocked";
    if (status === "archived" || status === "deleted")
        return "failed-terminal";
    return "pending";
}
function normalizePushCenterStatus(rawStatus, retryable = false, operatorActionRequired = false) {
    const status = text(rawStatus).toLowerCase().replace(/_/g, "-");
    if (operatorActionRequired)
        return "operator-action-required";
    if (retryable)
        return "retryable";
    if (status === "sent" || status === "succeeded" || status === "success")
        return "sent";
    if (status === "failed-terminal" || status === "terminal-failed")
        return "failed-terminal";
    if (status === "blocked")
        return "blocked";
    if (status === "pending" || status === "queued" || status === "running")
        return "pending";
    return "evidence-incomplete";
}
function firstPlan(payload) {
    const item = asArray(payload.items)[0];
    return item ? asRecord(item) : null;
}
function sourceStatus(...payloads) {
    for (const payload of payloads) {
        const value = text(payload.source_status);
        if (value)
            return value;
    }
    return "read_only_api";
}
function planId(plan) {
    return intValue(plan?.id);
}
function planName(plan) {
    return text(plan?.plan_name || plan?.name) || "Group Ops plan";
}
function groupSummary(detail, groupsPayload, listPlan) {
    const detailSummary = asRecord(detail.groups_summary);
    const groupsSummary = asRecord(groupsPayload.summary);
    return {
        bound_group_count: intValue(detailSummary.bound_group_count ?? groupsSummary.bound_group_count ?? listPlan?.bound_group_count),
        estimated_reach: intValue(detailSummary.estimated_reach ?? groupsSummary.estimated_reach ?? listPlan?.today_estimated_reach),
        internal_member_count: intValue(detailSummary.internal_member_count ?? groupsSummary.internal_member_count),
        external_member_count: intValue(detailSummary.external_member_count ?? groupsSummary.external_member_count)
    };
}
function firstPushCenterItem(payload) {
    const item = asArray(payload.items)[0];
    return item ? asRecord(item) : null;
}
function leftRailFromRealData(plan, detail, groups, nodes, executions, pushCenter) {
    const summary = groupSummary(detail, groups, plan);
    const nodeCount = asArray(nodes.items ?? detail.nodes).length;
    const executionTotal = intValue(executions.total);
    const pushItem = firstPushCenterItem(pushCenter);
    const pushStatus = pushItem
        ? normalizePushCenterStatus(pushItem.effective_status || pushItem.status || pushItem.raw_status, Boolean(pushItem.retryable), Boolean(pushItem.operator_action_required))
        : "evidence-incomplete";
    return [
        {
            id: `plan-${planId(plan)}`,
            label: planName(plan),
            kind: "plan",
            status: normalizePlanStatus(plan.status),
            summary: `${text(plan.plan_type) || "standard"} / ${text(plan.status) || "unknown"} / 只读绑定`
        },
        {
            id: `audience-plan-${planId(plan)}`,
            label: "Audience / receiver summary",
            kind: "audience",
            status: intValue(summary.bound_group_count) > 0 ? "ready" : "evidence-incomplete",
            summary: `${intValue(summary.bound_group_count)} 个绑定群，预计触达 ${intValue(summary.estimated_reach)}；不展示 raw receiver 或群成员标识。`
        },
        {
            id: `task-plan-${planId(plan)}`,
            label: "Task / content summary",
            kind: "task",
            status: nodeCount > 0 ? "pending" : "evidence-incomplete",
            summary: `${nodeCount} 个动作节点，${executionTotal} 条执行记录；preview-only，不执行任务。`
        },
        {
            id: `push-center-plan-${planId(plan)}`,
            label: "Push Center linked status",
            kind: "task",
            status: pushStatus,
            summary: pushItem ? "找到只读 Push Center projection；详情仍需通过 Push Center gate 解释。" : "未找到 linked Push Center projection，不能伪造成 sent。"
        }
    ];
}
function scenariosFromRealData(plan, detail, groups, nodes, executions, pushCenter) {
    const summary = groupSummary(detail, groups, plan);
    const nodeCount = asArray(nodes.items ?? detail.nodes).length;
    const executionTotal = intValue(executions.total);
    const pushItem = firstPushCenterItem(pushCenter);
    const pushStatus = pushItem
        ? normalizePushCenterStatus(pushItem.effective_status || pushItem.status || pushItem.raw_status, Boolean(pushItem.retryable), Boolean(pushItem.operator_action_required))
        : "evidence-incomplete";
    const pushDerived = pushItem ? text(pushItem.projection_id || pushItem.id || pushItem.display_id) || "push_center_projection_found" : "push_center_not_linked";
    return [
        {
            key: "group_ops",
            title: `计划：${planName(plan)}`,
            status: normalizePlanStatus(plan.status),
            evidenceStatus: "REAL_DATA_BOUND",
            derivedStatus: `plan_${planId(plan)}_readonly`,
            summary: `${intValue(summary.bound_group_count)} 个绑定群，预计触达 ${intValue(summary.estimated_reach)}；真实数据只读展示。`,
            guardrail: "只读绑定计划状态；不保存、不审批、不发送。",
            route: `/admin/automation-conversion/group-ops/plans/${planId(plan)}`
        },
        {
            key: "group_ops",
            title: "Push Center / evidence node",
            status: pushStatus,
            evidenceStatus: pushItem ? "REAL_DATA_BOUND" : "EVIDENCE_INCOMPLETE",
            derivedStatus: pushDerived,
            summary: pushItem ? "Push Center 只读 projection 可见；sent 仍不代表 governance complete。" : "未找到 Push Center projection，保持 evidence-incomplete。",
            guardrail: "必须通过 Push Center gate 解释，不允许 direct send。",
            route: "/admin/push-center"
        },
        {
            key: "group_ops",
            title: "治理状态",
            status: "governance-missing",
            evidenceStatus: "EVIDENCE_COLLECTED",
            derivedStatus: "approval_allowlist_window_missing",
            summary: "独立 operator approval、receiver allowlist、gray-window 记录仍需 attach。",
            guardrail: "requires_approval / requires_allowlist / requires_gray_window 仍然生效。",
            route: "/admin/business-closure"
        },
        {
            key: "ops_plan_broadcast",
            title: "Preview canvas summary",
            status: nodeCount > 0 ? "downstream-pending" : "evidence-incomplete",
            evidenceStatus: "REAL_DATA_BOUND",
            derivedStatus: `nodes_${nodeCount}_executions_${executionTotal}`,
            summary: `${nodeCount} 个计划节点，${executionTotal} 条执行记录；仅前端内存 preview，不执行 downstream external effect。`,
            guardrail: "no_direct_send / no_external_call / no_production_write。",
            route: `/admin/automation-conversion/group-ops/plans/${planId(plan)}`
        }
    ];
}
export const DEFAULT_WORKSPACE_API_CONFIG = {
    plansUrl: "/api/admin/automation-conversion/group-ops/plans?limit=8",
    planDetailBaseUrl: "/api/admin/automation-conversion/group-ops/plans/",
    planGroupsSuffix: "/groups",
    planNodesSuffix: "/nodes",
    planExecutionsBaseUrl: "/api/automation/group-ops/plans/",
    pushCenterJobsUrl: "/api/admin/push-center/jobs?section=group_ops&limit=8"
};
export function parseWorkspaceApiConfig(documentRef = document) {
    const node = documentRef.getElementById("p1GroupOpsWorkspaceApiConfig");
    if (!node?.textContent)
        return DEFAULT_WORKSPACE_API_CONFIG;
    try {
        return { ...DEFAULT_WORKSPACE_API_CONFIG, ...JSON.parse(node.textContent) };
    }
    catch (_error) {
        return DEFAULT_WORKSPACE_API_CONFIG;
    }
}
export function defaultRequestJson() {
    const adminApi = globalThis.AdminApi;
    if (adminApi?.requestJson)
        return adminApi.requestJson.bind(adminApi);
    return async function requestJsonWithFetch(url) {
        const response = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
        const payload = await response.json();
        if (!response.ok || payload?.ok === false)
            throw new Error(text(payload?.error || payload?.message || response.statusText));
        return payload;
    };
}
export async function loadGroupOpsWorkspaceData(config = DEFAULT_WORKSPACE_API_CONFIG, requestJson = defaultRequestJson()) {
    const plans = asRecord(await requestJson(config.plansUrl));
    const plan = firstPlan(plans);
    const selectedPlanId = planId(plan);
    if (!plan || selectedPlanId <= 0) {
        return {
            ...P1_GROUP_OPS_WORKSPACE_FIXTURE,
            dataSourceLabel: sourceStatus(plans),
            dataBindingStatus: "real_data_unavailable",
            leftRailItems: [
                {
                    id: "plan-empty",
                    label: "No Group Ops plan found",
                    kind: "plan",
                    status: "evidence-incomplete",
                    summary: "只读 API 可达，但没有可绑定的 Group Ops 计划。"
                }
            ],
            payload: {
                finalVerdict: "P1_READY_WITH_EXCEPTIONS",
                canClaimPass90Plus: false,
                scenarios: [
                    {
                        key: "group_ops",
                        title: "Group Ops real-data binding",
                        status: "evidence-incomplete",
                        evidenceStatus: "REAL_DATA_UNAVAILABLE",
                        derivedStatus: "plan_not_found",
                        summary: "没有找到 Group Ops plan，保留 preview-only fallback。",
                        guardrail: "不能伪造成真实数据已绑定。",
                        route: "/admin/automation-conversion/group-ops/ui"
                    }
                ]
            }
        };
    }
    const detailUrl = `${config.planDetailBaseUrl}${encodeURIComponent(String(selectedPlanId))}`;
    const [detail, groups, nodes, executions, pushCenter] = await Promise.all([
        requestJson(detailUrl),
        requestJson(`${detailUrl}${config.planGroupsSuffix}`),
        requestJson(`${detailUrl}${config.planNodesSuffix}`),
        requestJson(`${config.planExecutionsBaseUrl}${encodeURIComponent(String(selectedPlanId))}/executions?limit=8`),
        requestJson(config.pushCenterJobsUrl)
    ]);
    const detailPayload = asRecord(detail);
    const groupsPayload = asRecord(groups);
    const nodesPayload = asRecord(nodes);
    const executionsPayload = asRecord(executions);
    const pushPayload = asRecord(pushCenter);
    return {
        payload: {
            finalVerdict: "P1_READY_WITH_EXCEPTIONS",
            canClaimPass90Plus: false,
            scenarios: scenariosFromRealData(plan, detailPayload, groupsPayload, nodesPayload, executionsPayload, pushPayload)
        },
        leftRailItems: leftRailFromRealData(plan, detailPayload, groupsPayload, nodesPayload, executionsPayload, pushPayload),
        workspaceMode: "draft_only_preview_only",
        dataSourceLabel: sourceStatus(plans, detailPayload, groupsPayload, nodesPayload, executionsPayload),
        dataBindingStatus: "real_data_bound",
        realExternalCallExecuted: false,
        productionWriteExecuted: false
    };
}
