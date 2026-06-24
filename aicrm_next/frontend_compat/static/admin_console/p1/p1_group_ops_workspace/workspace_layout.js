import { escapeHtml } from "../shared/dom.js";
import { renderGuardrailNotice } from "../shared/guardrail_notice.js";
import { renderStatusBadge } from "../shared/status_badge.js";
import { renderStatusCard } from "../shared/status_card.js";
import { statusMeta } from "../shared/status_model.js";
import { defaultRequestJson, loadGroupOpsWorkspaceData, parseWorkspaceApiConfig } from "./workspace_api.js";
import { createWorkspaceSelectionState, renderWorkspaceDetailPanel, renderWorkspaceSelectedPreviewResult, selectWorkspaceEntity } from "./workspace_detail.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "./workspace_fixture.js";
import { renderWorkspaceCanvas, renderWorkspacePreviewResult } from "./workspace_preview.js";
import { buildGroupOpsWorkspaceStatusModel, workspaceCanRenderGlobalPass } from "./workspace_status.js";
function isSelectedListItem(item, selection) {
    if (item.entityType !== selection.selectedEntityType)
        return false;
    if (item.entityType === "plan")
        return selection.selectedPlanId === item.detailId;
    if (item.entityType === "group")
        return selection.selectedGroupId === item.detailId;
    if (item.entityType === "node")
        return selection.selectedNodeId === item.detailId;
    if (item.entityType === "execution")
        return selection.selectedExecutionId === item.detailId;
    if (item.entityType === "push_center")
        return selection.selectedPushCenterJobId === item.detailId;
    return false;
}
function renderLeftRailItem(item, selection) {
    const meta = statusMeta(item.status);
    const selectedClass = isSelectedListItem(item, selection) ? " p1-workspace-list-item--selected" : "";
    return `
    <button type="button" class="p1-workspace-list-item p1-workspace-list-item--${meta.tone}${selectedClass}" data-kind="${escapeHtml(item.kind)}" data-status="${escapeHtml(item.status)}" data-workspace-select-type="${escapeHtml(item.entityType)}" data-workspace-select-id="${escapeHtml(item.detailId)}">
      <div class="p1-workspace-list-item__head">
        <span>${escapeHtml(item.kind)}</span>
        ${renderStatusBadge(item.status)}
      </div>
      <strong>${escapeHtml(item.label)}</strong>
      <p>${escapeHtml(item.summary)}</p>
    </button>
  `;
}
function renderWorkspaceHeader(fixture) {
    return `
    <section class="admin-card p1-workspace-banner" data-workspace-mode="${escapeHtml(fixture.workspaceMode)}" data-final-verdict="${escapeHtml(fixture.payload.finalVerdict)}" data-data-binding-status="${escapeHtml(fixture.dataBindingStatus)}" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Native workspace preview</h2>
        <p>当前为 draft-only / preview-only；不会发送、不审批、不写生产。数据源：${escapeHtml(fixture.dataSourceLabel)}。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">${escapeHtml(fixture.payload.finalVerdict)}</span>
    </section>
  `;
}
function renderLeftRail(fixture, selection) {
    return `
    <aside class="p1-workspace-left" aria-label="计划、人群、任务列表">
      <div class="p1-workspace-panel-head">
        <h2>计划 / 人群 / 任务</h2>
        <p>点击计划、人群、节点、执行或 Push Center 项只会更新本地只读 detail selection。</p>
      </div>
      <div class="p1-workspace-list">${fixture.leftRailItems.map((item) => renderLeftRailItem(item, selection)).join("")}</div>
    </aside>
  `;
}
function renderPropertyPanel(fixture, selection) {
    const cards = fixture.payload.scenarios.map((scenario) => renderStatusCard(scenario, {
        dragHandle: true,
        dragDisabledReason: "P1 native workspace uses readonly preview only; no direct send."
    })).join("");
    const governanceScenario = fixture.payload.scenarios.find((scenario) => scenario.status === "governance-missing");
    const guardrailNotice = governanceScenario ? renderGuardrailNotice(governanceScenario) : "";
    const canPass = workspaceCanRenderGlobalPass(fixture.payload);
    return `
    <aside class="p1-workspace-right" aria-label="属性面板与护栏">
      <div class="p1-workspace-panel-head">
        <h2>属性面板 / guardrail / evidence state</h2>
        <p>Group Ops 发送 evidence 已存在，但 governance evidence incomplete；真正执行必须走 approval / allowlist / Push Center / external effect gates。</p>
      </div>
      <section class="p1-workspace-guardrail-summary" data-can-render-pass90="${canPass ? "true" : "false"}">
        <strong>Guardrail summary</strong>
        ${guardrailNotice}
        <p>P1_READY_WITH_EXCEPTIONS 不等于 PASS_90_PLUS；sent evidence 不等于 governance complete。</p>
      </section>
      ${renderWorkspaceDetailPanel(fixture, selection)}
      <div class="p1-workspace-status-stack">${cards}</div>
    </aside>
  `;
}
function attachSelectionHandlers(root, fixture, selection) {
    if (typeof root.querySelectorAll !== "function")
        return;
    const nodes = root.querySelectorAll("[data-workspace-select-type][data-workspace-select-id]");
    nodes.forEach((node) => {
        node.addEventListener("click", () => {
            const entityType = node.dataset.workspaceSelectType;
            const detailId = node.dataset.workspaceSelectId;
            if (!entityType || !detailId)
                return;
            renderP1GroupOpsWorkspace(root, fixture, selectWorkspaceEntity(selection, entityType, detailId));
        });
    });
}
export function renderP1GroupOpsWorkspace(root, fixture = P1_GROUP_OPS_WORKSPACE_FIXTURE, selection = createWorkspaceSelectionState(fixture)) {
    const model = buildGroupOpsWorkspaceStatusModel(fixture);
    root.innerHTML = `
    <section class="p1-native-group-ops-workspace" data-p1-native-workspace="group_ops" data-draft-only="true" data-preview-only="true" data-can-claim-pass90="false">
      ${renderWorkspaceHeader(fixture)}
      <div class="p1-workspace-grid">
        ${renderLeftRail(fixture, selection)}
        ${renderWorkspaceCanvas(model, fixture, selection)}
        ${renderPropertyPanel(fixture, selection)}
      </div>
      ${renderWorkspaceSelectedPreviewResult(fixture, selection)}
      ${renderWorkspacePreviewResult(model)}
    </section>
  `;
    attachSelectionHandlers(root, fixture, selection);
}
function boot() {
    const root = document.getElementById("p1GroupOpsWorkspaceApp");
    if (!root)
        return;
    renderP1GroupOpsWorkspace(root);
    loadGroupOpsWorkspaceData(parseWorkspaceApiConfig(), defaultRequestJson())
        .then((fixture) => {
        renderP1GroupOpsWorkspace(root, fixture);
    })
        .catch(() => {
        renderP1GroupOpsWorkspace(root, {
            ...P1_GROUP_OPS_WORKSPACE_FIXTURE,
            dataBindingStatus: "real_data_unavailable",
            dataSourceLabel: "read_only_api_unavailable"
        });
    });
}
if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    }
    else {
        boot();
    }
}
