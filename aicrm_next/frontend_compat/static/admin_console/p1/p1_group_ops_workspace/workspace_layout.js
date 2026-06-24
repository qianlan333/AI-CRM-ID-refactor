import { escapeHtml } from "../shared/dom.js";
import { renderGuardrailNotice } from "../shared/guardrail_notice.js";
import { renderStatusBadge } from "../shared/status_badge.js";
import { renderStatusCard } from "../shared/status_card.js";
import { statusMeta } from "../shared/status_model.js";
import { defaultRequestJson, loadGroupOpsWorkspaceData, parseWorkspaceApiConfig } from "./workspace_api.js";
import { renderGroupedWorkspaceCanvas } from "./workspace_canvas.js";
import { renderWorkspaceDetailPanel, renderWorkspaceSelectedPreviewResult, } from "./workspace_detail.js";
import { ENTITY_FILTER_OPTIONS, STATUS_FILTER_OPTIONS, filterWorkspaceView } from "./workspace_filters.js";
import { buildWorkspaceCanvasLanes } from "./workspace_grouping.js";
import { moveWorkspaceCanvasSelection } from "./workspace_keyboard.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE, createUnavailableWorkspaceFixture } from "./workspace_fixture.js";
import { renderWorkspacePreviewResult } from "./workspace_preview.js";
import { buildGroupOpsWorkspaceStatusModel, workspaceCanRenderGlobalPass } from "./workspace_status.js";
import { createWorkspaceViewState, selectEntityInViewState, selectionFromViewState, toggleWorkspaceCanvasLane, updateWorkspaceViewState } from "./workspace_view_state.js";
function isSelectedListItem(item, viewState) {
    return item.entityType === viewState.selectedEntityType && item.detailId === viewState.selectedEntityId;
}
function renderOption(value, currentValue) {
    return `<option value="${escapeHtml(value)}"${value === currentValue ? " selected" : ""}>${escapeHtml(value)}</option>`;
}
function renderFilterToolbar(viewState, filtered) {
    return `
    <section class="p1-workspace-filters" aria-label="Workspace local filters" data-view-state-memory-only="true" data-filter-result-count="${filtered.visibleLeftRailItems.length}" data-filter-data-state="${escapeHtml(filtered.dataState)}">
      <div class="p1-workspace-panel-head">
        <h2>Search / filters</h2>
        <p>筛选只作用于已加载的脱敏只读数据；不写 URL、不保存后端、不触发执行。</p>
      </div>
      <div class="p1-workspace-filter-grid">
        <label>
          <span>Keyword</span>
          <input type="search" value="${escapeHtml(viewState.keyword)}" placeholder="plan name or internal id" data-workspace-filter="keyword" autocomplete="off">
        </label>
        <label>
          <span>Plan status</span>
          <select data-workspace-filter="planStatusFilter">${STATUS_FILTER_OPTIONS.map((option) => renderOption(option, viewState.planStatusFilter)).join("")}</select>
        </label>
        <label>
          <span>Entity type</span>
          <select data-workspace-filter="entityTypeFilter">${ENTITY_FILTER_OPTIONS.map((option) => renderOption(option, viewState.entityTypeFilter)).join("")}</select>
        </label>
        <label>
          <span>Execution status</span>
          <select data-workspace-filter="executionStatusFilter">${STATUS_FILTER_OPTIONS.map((option) => renderOption(option, viewState.executionStatusFilter)).join("")}</select>
        </label>
        <label>
          <span>Push Center status</span>
          <select data-workspace-filter="pushCenterStatusFilter">${STATUS_FILTER_OPTIONS.map((option) => renderOption(option, viewState.pushCenterStatusFilter)).join("")}</select>
        </label>
        <label>
          <span>Panel mode</span>
          <select data-workspace-filter="panelMode">
            ${["summary", "detail", "guardrail"].map((option) => renderOption(option, viewState.panelMode)).join("")}
          </select>
        </label>
      </div>
      <p class="p1-workspace-filter-summary">${escapeHtml(filtered.resultSummary)}；原始 evidence status 不会被筛选改变。</p>
    </section>
  `;
}
function renderStateBanner(fixture, filtered) {
    if (filtered.isEmpty) {
        return `
      <section class="p1-workspace-state-banner p1-workspace-state-banner--empty" data-empty-search-result="true" data-can-claim-pass90="false">
        <strong>Empty search result</strong>
        <p>${escapeHtml(filtered.emptyReason)}</p>
      </section>
    `;
    }
    if (filtered.dataState === "real_data_unavailable") {
        return `
      <section class="p1-workspace-state-banner p1-workspace-state-banner--danger" data-real-data-unavailable="true" data-can-claim-pass90="false">
        <strong>Read-only API unavailable</strong>
        <p>API read failure keeps this workspace in preview fallback; it must not render sent or completed.</p>
      </section>
    `;
    }
    if (filtered.dataState === "partial_data") {
        return `
      <section class="p1-workspace-state-banner p1-workspace-state-banner--warning" data-partial-data="true" data-can-claim-pass90="false">
        <strong>Partial data</strong>
        <p>部分 Push Center 或 governance evidence 仍不完整；缺失项继续显示 evidence-incomplete / governance-missing。</p>
      </section>
    `;
    }
    return `
    <section class="p1-workspace-state-banner" data-readonly-data-ready="true" data-can-claim-pass90="false">
      <strong>Read-only data loaded</strong>
      <p>${escapeHtml(fixture.dataSourceLabel)} 已绑定；筛选不改变任何 evidence status。</p>
    </section>
  `;
}
function renderLeftRailItem(item, viewState) {
    const meta = statusMeta(item.status);
    const selectedClass = isSelectedListItem(item, viewState) ? " p1-workspace-list-item--selected" : "";
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
function renderSafePreviewBanner() {
    return `
    <section class="p1-workspace-safe-preview-banner" aria-label="Read-only safety state" data-safe-preview-affordance="true" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <strong>Safe preview only</strong>
      <span>不会发送、不审批、不写生产；preview 不等于已执行，sent evidence 不等于 governance complete。</span>
    </section>
  `;
}
function renderSafePreviewFooter() {
    return `
    <section class="p1-workspace-safe-preview-footer" aria-label="Fixed safe preview summary" data-safe-preview-footer="true" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <strong>Safety summary</strong>
      <p>preview-only=true；production_write=false；real_external_call=false；can_claim_pass_90_plus=false。Requires approval / allowlist / gray-window 的项目仍需运营治理证据。</p>
    </section>
  `;
}
function renderLeftRail(filtered) {
    const rows = filtered.visibleLeftRailItems.length > 0
        ? filtered.visibleLeftRailItems.map((item) => renderLeftRailItem(item, filtered.viewState)).join("")
        : `<section class="p1-workspace-empty-state" data-empty-search-result="true"><strong>No matching item</strong><p>${escapeHtml(filtered.emptyReason)}</p></section>`;
    return `
    <aside class="p1-workspace-left" aria-label="计划、人群、任务列表">
      <div class="p1-workspace-panel-head">
        <h2>计划 / 人群 / 任务</h2>
        <p>点击计划、人群、节点、执行或 Push Center 项只会更新本地只读 detail selection。</p>
      </div>
      <div class="p1-workspace-list">${rows}</div>
    </aside>
  `;
}
function renderPropertyPanel(fixture, filtered) {
    const selection = selectionFromViewState(fixture, filtered.viewState);
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
function attachSelectionHandlers(root, fixture, viewState) {
    if (typeof root.querySelectorAll !== "function")
        return;
    const nodes = root.querySelectorAll("[data-workspace-select-type][data-workspace-select-id]");
    nodes.forEach((node) => {
        node.addEventListener("click", () => {
            const entityType = node.dataset.workspaceSelectType;
            const detailId = node.dataset.workspaceSelectId;
            if (!entityType || !detailId)
                return;
            renderP1GroupOpsWorkspace(root, fixture, selectEntityInViewState(viewState, entityType, detailId));
        });
    });
}
function attachFilterHandlers(root, fixture, viewState) {
    if (typeof root.querySelectorAll !== "function")
        return;
    const nodes = root.querySelectorAll("[data-workspace-filter]");
    nodes.forEach((node) => {
        const eventName = node.tagName === "INPUT" ? "input" : "change";
        node.addEventListener(eventName, () => {
            const key = node.dataset.workspaceFilter;
            if (!key)
                return;
            renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
                [key]: node.value
            }));
        });
    });
}
function attachCanvasLaneHandlers(root, fixture, viewState) {
    if (typeof root.querySelectorAll !== "function")
        return;
    const nodes = root.querySelectorAll("[data-workspace-lane-toggle]");
    nodes.forEach((node) => {
        node.addEventListener("click", () => {
            const laneId = node.dataset.workspaceLaneToggle;
            if (!laneId)
                return;
            renderP1GroupOpsWorkspace(root, fixture, toggleWorkspaceCanvasLane(viewState, laneId));
        });
    });
}
function attachKeyboardHandlers(root, fixture, viewState) {
    if (typeof root.querySelector !== "function")
        return;
    const canvas = root.querySelector("[data-keyboard-navigation]");
    if (!canvas)
        return;
    canvas.addEventListener("keydown", (event) => {
        const allowedKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", " ", "Escape"];
        if (!allowedKeys.includes(event.key))
            return;
        event.preventDefault();
        const filtered = filterWorkspaceView(fixture, viewState);
        const lanes = buildWorkspaceCanvasLanes(fixture, filtered, filtered.viewState);
        renderP1GroupOpsWorkspace(root, fixture, moveWorkspaceCanvasSelection(lanes, filtered.viewState, event.key));
    });
}
export function renderP1GroupOpsWorkspace(root, fixture = P1_GROUP_OPS_WORKSPACE_FIXTURE, viewState = createWorkspaceViewState(fixture)) {
    const model = buildGroupOpsWorkspaceStatusModel(fixture);
    const filtered = filterWorkspaceView(fixture, viewState);
    const selection = selectionFromViewState(fixture, filtered.viewState);
    root.innerHTML = `
    <section class="p1-native-group-ops-workspace" data-p1-native-workspace="group_ops" data-draft-only="true" data-preview-only="true" data-can-claim-pass90="false" data-view-state-memory-only="true" data-selected-entity-type="${escapeHtml(filtered.viewState.selectedEntityType)}" data-selected-entity-id="${escapeHtml(filtered.viewState.selectedEntityId)}" data-panel-mode="${escapeHtml(filtered.viewState.panelMode)}">
      ${renderWorkspaceHeader(fixture)}
      ${renderSafePreviewBanner()}
      ${renderFilterToolbar(filtered.viewState, filtered)}
      ${renderStateBanner(fixture, filtered)}
      <div class="p1-workspace-grid">
        ${renderLeftRail(filtered)}
        ${renderGroupedWorkspaceCanvas(fixture, filtered, filtered.viewState)}
        ${renderPropertyPanel(fixture, filtered)}
      </div>
      ${renderWorkspaceSelectedPreviewResult(fixture, selection)}
      ${renderWorkspacePreviewResult(model)}
      ${renderSafePreviewFooter()}
    </section>
  `;
    attachSelectionHandlers(root, fixture, filtered.viewState);
    attachFilterHandlers(root, fixture, filtered.viewState);
    attachCanvasLaneHandlers(root, fixture, filtered.viewState);
    attachKeyboardHandlers(root, fixture, filtered.viewState);
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
        renderP1GroupOpsWorkspace(root, createUnavailableWorkspaceFixture("read_only_api_unavailable"));
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
