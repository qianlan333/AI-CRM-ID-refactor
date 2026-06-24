import { escapeHtml } from "../shared/dom.js";
import { renderGuardrailNotice } from "../shared/guardrail_notice.js";
import { renderStatusBadge } from "../shared/status_badge.js";
import { renderStatusCard } from "../shared/status_card.js";
import { statusMeta } from "../shared/status_model.js";
import { defaultRequestJson, loadGroupOpsWorkspaceData, parseWorkspaceApiConfig } from "./workspace_api.js";
import {
  buildCopySafeBundleJson,
  buildCopySafeBundleText,
  copyBundleSummaryToClipboard,
  type CopySafeResult
} from "./workspace_bundle_export.js";
import { renderGroupedWorkspaceCanvas } from "./workspace_canvas.js";
import {
  renderWorkspaceDetailPanel,
  renderWorkspaceSelectedPreviewResult,
} from "./workspace_detail.js";
import {
  archiveDraft,
  buildWorkspaceDraftPayload,
  createDraft,
  isDraftConflictError,
  updateDraft,
  type WorkspaceDraftResponse
} from "./workspace_draft_api.js";
import { ENTITY_FILTER_OPTIONS, STATUS_FILTER_OPTIONS, filterWorkspaceView, type FilteredWorkspaceView } from "./workspace_filters.js";
import { buildWorkspaceCanvasLanes } from "./workspace_grouping.js";
import { moveWorkspaceCanvasSelection, type WorkspaceKeyboardKey } from "./workspace_keyboard.js";
import {
  clearMultiSelection,
  countMultiSelected,
  isEntityMultiSelected,
  selectVisibleItems,
  selectVisibleLaneItems,
  toggleMultiSelectedEntity
} from "./workspace_multi_select.js";
import { buildWorkspacePreviewBundle } from "./workspace_preview_bundle.js";
import {
  P1_GROUP_OPS_WORKSPACE_FIXTURE,
  createUnavailableWorkspaceFixture,
  type WorkspaceEntityType,
  type WorkspaceFixture,
  type WorkspaceListItem
} from "./workspace_fixture.js";
import { renderWorkspacePreviewResult } from "./workspace_preview.js";
import { buildGroupOpsWorkspaceStatusModel, workspaceCanRenderGlobalPass } from "./workspace_status.js";
import {
  createWorkspaceViewState,
  selectEntityInViewState,
  selectionFromViewState,
  toggleWorkspaceCanvasLane,
  updateWorkspaceViewState,
  type WorkspaceCanvasLaneId,
  type WorkspacePanelMode,
  type WorkspaceViewState
} from "./workspace_view_state.js";

function isSelectedListItem(item: WorkspaceListItem, viewState: WorkspaceViewState): boolean {
  return item.entityType === viewState.selectedEntityType && item.detailId === viewState.selectedEntityId;
}

function renderOption(value: string, currentValue: string): string {
  return `<option value="${escapeHtml(value)}"${value === currentValue ? " selected" : ""}>${escapeHtml(value)}</option>`;
}

function renderFilterToolbar(viewState: WorkspaceViewState, filtered: FilteredWorkspaceView): string {
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

function renderStateBanner(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
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

function renderLeftRailItem(item: WorkspaceListItem, viewState: WorkspaceViewState): string {
  const meta = statusMeta(item.status);
  const selectedClass = isSelectedListItem(item, viewState) ? " p1-workspace-list-item--selected" : "";
  const multiSelected = isEntityMultiSelected(viewState, item.entityType, item.detailId);
  return `
    <button type="button" class="p1-workspace-list-item p1-workspace-list-item--${meta.tone}${selectedClass}" data-kind="${escapeHtml(item.kind)}" data-status="${escapeHtml(item.status)}" data-multi-selected="${multiSelected ? "true" : "false"}" data-workspace-select-type="${escapeHtml(item.entityType)}" data-workspace-select-id="${escapeHtml(item.detailId)}">
      <div class="p1-workspace-list-item__head">
        <span>${escapeHtml(item.kind)}</span>
        ${renderStatusBadge(item.status)}
      </div>
      <strong>${escapeHtml(item.label)}</strong>
      <p>${escapeHtml(item.summary)}</p>
      <span class="p1-workspace-multi-select-affordance" role="checkbox" aria-checked="${multiSelected ? "true" : "false"}" tabindex="0" data-workspace-multi-toggle="true" data-workspace-multi-type="${escapeHtml(item.entityType)}" data-workspace-multi-id="${escapeHtml(item.detailId)}">
        ${multiSelected ? "Selected for preview bundle" : "Select for preview bundle"}
      </span>
    </button>
  `;
}

function renderWorkspaceHeader(fixture: WorkspaceFixture): string {
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

function renderSafePreviewBanner(): string {
  return `
    <section class="p1-workspace-safe-preview-banner" aria-label="Read-only safety state" data-safe-preview-affordance="true" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <strong>Safe preview only</strong>
      <span>不会发送、不审批、不写生产；preview 不等于已执行，sent evidence 不等于 governance complete。</span>
    </section>
  `;
}

function renderSafePreviewFooter(): string {
  return `
    <section class="p1-workspace-safe-preview-footer" aria-label="Fixed safe preview summary" data-safe-preview-footer="true" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <strong>Safety summary</strong>
      <p>preview-only=true；production_write=false；real_external_call=false；can_claim_pass_90_plus=false。Requires approval / allowlist / gray-window 的项目仍需运营治理证据。</p>
    </section>
  `;
}

function renderLeftRail(filtered: FilteredWorkspaceView): string {
  const rows = filtered.visibleLeftRailItems.length > 0
    ? filtered.visibleLeftRailItems.map((item) => renderLeftRailItem(item, filtered.viewState)).join("")
    : `<section class="p1-workspace-empty-state" data-empty-search-result="true"><strong>No matching item</strong><p>${escapeHtml(filtered.emptyReason)}</p></section>`;
  return `
    <aside class="p1-workspace-left" aria-label="计划、人群、任务列表">
      <div class="p1-workspace-panel-head">
        <h2>计划 / 人群 / 任务</h2>
        <p>点击计划、人群、节点、执行或 Push Center 项只会更新本地只读 detail selection。</p>
      </div>
      <div class="p1-workspace-bulk-actions" data-multi-select-memory-only="true">
        <button type="button" data-workspace-select-visible="true">Select visible filtered results</button>
        <button type="button" data-workspace-clear-selection="true">Clear selection</button>
      </div>
      <div class="p1-workspace-list">${rows}</div>
    </aside>
  `;
}

function renderBundleSummary(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  const bundle = buildWorkspacePreviewBundle(fixture, filtered, filtered.viewState);
  const textSummary = buildCopySafeBundleText(bundle, { finalVerdict: fixture.payload.finalVerdict });
  const jsonSummary = buildCopySafeBundleJson(bundle, { finalVerdict: fixture.payload.finalVerdict });
  const previewOutput = filtered.viewState.copyPreviewFormat === "json" ? jsonSummary : textSummary;
  const copyStatusClass = filtered.viewState.copyStatus === "copy_failed"
    ? " p1-workspace-copy-status--danger"
    : filtered.viewState.copyStatus === "copied"
      ? " p1-workspace-copy-status--success"
      : "";
  const countRows = Object.entries(bundle.countsByEntityType).map(([entityType, count]) => `
    <div><dt>${escapeHtml(entityType)}</dt><dd>${count}</dd></div>
  `).join("");
  const selectedRows = bundle.items.length > 0
    ? bundle.items.map((item) => `
      <button type="button" class="p1-workspace-bundle-item" data-workspace-select-type="${escapeHtml(item.entityType)}" data-workspace-select-id="${escapeHtml(item.detailId)}" data-visible-in-filter="${item.isVisible ? "true" : "false"}">
        <span>${escapeHtml(item.entityType)}</span>
        <strong>${escapeHtml(item.title)}</strong>
        ${renderStatusBadge(item.status)}
        <em>${item.isVisible ? "visible" : "not currently visible"}</em>
      </button>
    `).join("")
    : `<section class="p1-workspace-empty-state" data-empty-preview-bundle="true"><strong>No selected item</strong><p>Use Select for preview bundle; selection remains memory-only and clears on refresh.</p></section>`;
  return `
    <section class="p1-workspace-preview-bundle" aria-live="polite" data-preview-bundle-id="${escapeHtml(bundle.bundleId)}" data-selected-count="${bundle.selectedCount}" data-can-execute="false" data-preview-only="${bundle.previewOnly ? "true" : "false"}" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>${escapeHtml(bundle.title)}</h2>
        <p>Multi-select preview is memory-only. Hidden filtered-out selected items remain in the bundle and are marked as not currently visible.</p>
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>selected</dt><dd>${bundle.selectedCount}</dd></div>
        <div><dt>blocked</dt><dd>${bundle.blockedCount}</dd></div>
        <div><dt>action_required</dt><dd>${bundle.actionRequiredCount}</dd></div>
        <div><dt>governance_missing</dt><dd>${bundle.governanceMissingCount}</dd></div>
        <div><dt>push_center_pending</dt><dd>${bundle.pushCenterPendingCount}</dd></div>
        <div><dt>evidence_incomplete</dt><dd>${bundle.evidenceIncompleteCount}</dd></div>
        <div><dt>hidden_selected</dt><dd>${bundle.hiddenSelectedCount}</dd></div>
        <div><dt>preview-only</dt><dd>true</dd></div>
        <div><dt>can_claim_pass90</dt><dd>false</dd></div>
      </dl>
      <dl class="p1-workspace-mini-fields">${countRows}</dl>
      <p class="p1-workspace-guardrails">${bundle.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ")}</p>
      <section class="p1-workspace-copy-export" data-copy-safe-export="true" data-copy-preview-visible="${filtered.viewState.copyPreviewVisible ? "true" : "false"}" data-copy-preview-format="${escapeHtml(filtered.viewState.copyPreviewFormat)}">
        <div class="p1-workspace-copy-actions" aria-label="只读复制安全摘要">
          <button type="button" data-workspace-copy-bundle="text">复制安全摘要</button>
          <button type="button" data-workspace-copy-bundle="json">复制脱敏 JSON</button>
          <button type="button" data-workspace-toggle-copy-preview="true">查看复制内容预览</button>
        </div>
        <p class="p1-workspace-copy-note">只读复制，不会发送；复制内容不保存后端、不下载文件、不写浏览器持久存储。</p>
        <p class="p1-workspace-copy-status${copyStatusClass}" aria-live="polite" data-copy-status="${escapeHtml(filtered.viewState.copyStatus)}">${escapeHtml(filtered.viewState.copyStatusMessage)}</p>
        ${filtered.viewState.copyPreviewVisible ? `<pre class="p1-workspace-copy-preview" tabindex="0" data-copy-preview="true">${escapeHtml(previewOutput)}</pre>` : ""}
      </section>
      <div class="p1-workspace-bundle-list">${selectedRows}</div>
    </section>
  `;
}

function draftStatusTone(status: WorkspaceViewState["draftSaveStatus"]): string {
  if (status === "saved" || status === "archived") return "success";
  if (status === "failed" || status === "conflict") return "danger";
  if (status === "saving") return "info";
  return "neutral";
}

function renderDraftPersistencePanel(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  const draftPayload = buildWorkspaceDraftPayload(fixture, filtered, filtered.viewState);
  const hasDraft = Boolean(filtered.viewState.currentDraftId);
  const tone = draftStatusTone(filtered.viewState.draftSaveStatus);
  return `
    <section class="p1-workspace-draft-save" aria-label="Save sanitized workspace draft" data-draft-persistence="frontend_save_only" data-preview-only="true" data-real-external-call-executed="false" data-push-center-job-created="false" data-external-effect-job-created="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>Draft persistence</h2>
        <p>保存草稿只写 draft 表；不会发送、不会审批、不会创建 Push Center job、不会创建 external_effect_job。</p>
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>draft_id</dt><dd>${escapeHtml(filtered.viewState.currentDraftId || "not_saved")}</dd></div>
        <div><dt>version</dt><dd>${filtered.viewState.currentDraftVersion || 0}</dd></div>
        <div><dt>items</dt><dd>${draftPayload.items.length}</dd></div>
        <div><dt>preview_only</dt><dd>true</dd></div>
        <div><dt>real_external_call</dt><dd>false</dd></div>
        <div><dt>can_claim_pass90</dt><dd>false</dd></div>
      </dl>
      <div class="p1-workspace-draft-actions" aria-label="草稿保存操作">
        <button type="button" data-workspace-save-draft="true">${hasDraft ? "Save draft update" : "Save draft"}</button>
        <button type="button" data-workspace-save-as-new-draft="true">Save as new draft</button>
        <button type="button" data-workspace-archive-draft="true"${hasDraft && filtered.viewState.draftSaveStatus !== "archived" ? "" : " disabled"}>Archive draft</button>
      </div>
      <p class="p1-workspace-draft-status p1-workspace-draft-status--${tone}" aria-live="polite" data-draft-save-status="${escapeHtml(filtered.viewState.draftSaveStatus)}">${escapeHtml(filtered.viewState.draftSaveMessage)}</p>
      <p class="p1-workspace-draft-guardrail">Draft persistence is not execution. request-review、approval bridge、Push Center bridge 均未接入；草稿不等于 sent/completed，也不等于 PASS_90_PLUS。</p>
    </section>
  `;
}

function renderPropertyPanel(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  const selection = selectionFromViewState(fixture, filtered.viewState);
  const multiSelectedCount = countMultiSelected(filtered.viewState);
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
      ${renderDraftPersistencePanel(fixture, filtered)}
      ${filtered.viewState.activeSelectionMode === "multi" && multiSelectedCount > 0 ? renderBundleSummary(fixture, filtered) : renderWorkspaceDetailPanel(fixture, selection)}
      <div class="p1-workspace-status-stack">${cards}</div>
    </aside>
  `;
}

function attachSelectionHandlers(
  root: HTMLElement,
  fixture: WorkspaceFixture,
  viewState: WorkspaceViewState
): void {
  if (typeof root.querySelectorAll !== "function") return;
  const nodes = root.querySelectorAll<HTMLElement>("[data-workspace-select-type][data-workspace-select-id]");
  nodes.forEach((node) => {
    node.addEventListener("click", () => {
      const entityType = node.dataset.workspaceSelectType as WorkspaceEntityType | undefined;
      const detailId = node.dataset.workspaceSelectId;
      if (!entityType || !detailId) return;
      renderP1GroupOpsWorkspace(root, fixture, selectEntityInViewState(viewState, entityType, detailId));
    });
  });
}

function attachFilterHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const nodes = root.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-workspace-filter]");
  nodes.forEach((node) => {
    const eventName = node.tagName === "INPUT" ? "input" : "change";
    node.addEventListener(eventName, () => {
      const key = node.dataset.workspaceFilter as keyof WorkspaceViewState | undefined;
      if (!key) return;
      renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
        [key]: node.value
      } as Partial<WorkspaceViewState>));
    });
  });
}

function attachCanvasLaneHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const nodes = root.querySelectorAll<HTMLElement>("[data-workspace-lane-toggle]");
  nodes.forEach((node) => {
    node.addEventListener("click", () => {
      const laneId = node.dataset.workspaceLaneToggle;
      if (!laneId) return;
      renderP1GroupOpsWorkspace(root, fixture, toggleWorkspaceCanvasLane(viewState, laneId as WorkspaceCanvasLaneId));
    });
  });
}

function entityTypeForLane(laneId: string): WorkspaceEntityType | null {
  if (laneId === "plans") return "plan";
  if (laneId === "groups") return "group";
  if (laneId === "nodes") return "node";
  if (laneId === "executions") return "execution";
  if (laneId === "push_center") return "push_center";
  if (laneId === "evidence") return "evidence";
  return null;
}

function attachMultiSelectHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  root.querySelectorAll<HTMLElement>("[data-workspace-multi-toggle]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const entityType = node.dataset.workspaceMultiType as WorkspaceEntityType | undefined;
      const detailId = node.dataset.workspaceMultiId;
      if (!entityType || !detailId) return;
      renderP1GroupOpsWorkspace(root, fixture, toggleMultiSelectedEntity(viewState, entityType, detailId));
    });
    node.addEventListener("keydown", (event) => {
      if (event.key !== " " && event.key !== "Enter") return;
      event.preventDefault();
      event.stopPropagation();
      const entityType = node.dataset.workspaceMultiType as WorkspaceEntityType | undefined;
      const detailId = node.dataset.workspaceMultiId;
      if (!entityType || !detailId) return;
      renderP1GroupOpsWorkspace(root, fixture, toggleMultiSelectedEntity(viewState, entityType, detailId));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-clear-selection]").forEach((node) => {
    node.addEventListener("click", () => {
      renderP1GroupOpsWorkspace(root, fixture, clearMultiSelection(viewState));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-select-visible]").forEach((node) => {
    node.addEventListener("click", () => {
      const filtered = filterWorkspaceView(fixture, viewState);
      renderP1GroupOpsWorkspace(root, fixture, selectVisibleItems(filtered.viewState, filtered.visibleLeftRailItems));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-select-lane]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const entityType = entityTypeForLane(node.dataset.workspaceSelectLane || "");
      if (!entityType) return;
      const filtered = filterWorkspaceView(fixture, viewState);
      renderP1GroupOpsWorkspace(root, fixture, selectVisibleLaneItems(filtered.viewState, filtered.visibleLeftRailItems, entityType));
    });
  });
}

function copyStatusUpdate(result: CopySafeResult): Pick<WorkspaceViewState, "copyStatus" | "copyStatusMessage"> {
  return {
    copyStatus: result.status,
    copyStatusMessage: result.ok
      ? "复制成功：只读脱敏摘要已进入剪贴板，不会发送。"
      : `复制失败：${result.message}`
  };
}

function attachBundleExportHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  root.querySelectorAll<HTMLElement>("[data-workspace-toggle-copy-preview]").forEach((node) => {
    node.addEventListener("click", () => {
      const nextFormat = viewState.copyPreviewFormat === "text" ? "json" : "text";
      renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
        copyPreviewVisible: !viewState.copyPreviewVisible || viewState.copyPreviewFormat !== nextFormat,
        copyPreviewFormat: nextFormat,
        copyStatus: "idle",
        copyStatusMessage: "只读复制预览已更新；不会发送。"
      }));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-copy-bundle]").forEach((node) => {
    node.addEventListener("click", () => {
      const format = node.dataset.workspaceCopyBundle === "json" ? "json" : "text";
      const filtered = filterWorkspaceView(fixture, viewState);
      const bundle = buildWorkspacePreviewBundle(fixture, filtered, filtered.viewState);
      const output = format === "json"
        ? buildCopySafeBundleJson(bundle, { finalVerdict: fixture.payload.finalVerdict })
        : buildCopySafeBundleText(bundle, { finalVerdict: fixture.payload.finalVerdict });
      copyBundleSummaryToClipboard(output).then((result) => {
        renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
          copyPreviewVisible: true,
          copyPreviewFormat: format,
          ...copyStatusUpdate(result)
        }));
      });
    });
  });
}

function draftStateFromResponse(
  viewState: WorkspaceViewState,
  payload: WorkspaceDraftResponse,
  message: string
): Partial<WorkspaceViewState> {
  return {
    currentDraftId: payload.draft_id || viewState.currentDraftId,
    currentDraftVersion: Number(payload.version || viewState.currentDraftVersion || 0),
    currentDraftSnapshotHash: String(payload.snapshot_hash || viewState.currentDraftSnapshotHash || ""),
    currentDraftIdempotencyKey: viewState.currentDraftIdempotencyKey,
    draftSaveStatus: payload.draft_status === "archived" ? "archived" : "saved",
    draftSaveMessage: message
  };
}

function attachDraftPersistenceHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const renderWithDraftUpdates = (updates: Partial<WorkspaceViewState>) => {
    renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, updates));
  };
  root.querySelectorAll<HTMLElement>("[data-workspace-save-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      const filtered = filterWorkspaceView(fixture, viewState);
      const basePayload = buildWorkspaceDraftPayload(fixture, filtered, filtered.viewState, {
        version: filtered.viewState.currentDraftVersion || undefined
      });
      const idempotencyKey = filtered.viewState.currentDraftIdempotencyKey || basePayload.idempotency_key;
      renderWithDraftUpdates({
        currentDraftIdempotencyKey: idempotencyKey,
        draftSaveStatus: "saving",
        draftSaveMessage: "正在保存脱敏草稿；不会发送、不审批、不创建 Push Center job。"
      });
      const request = filtered.viewState.currentDraftId && filtered.viewState.currentDraftVersion > 0
        ? updateDraft(filtered.viewState.currentDraftId, { ...basePayload, idempotency_key: idempotencyKey, version: filtered.viewState.currentDraftVersion })
        : createDraft({ ...basePayload, idempotency_key: idempotencyKey });
      request
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            ...draftStateFromResponse(filtered.viewState, response, "草稿已保存；仍为 preview-only，不可执行。"),
            currentDraftIdempotencyKey: idempotencyKey
          }));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            currentDraftIdempotencyKey: idempotencyKey,
            draftSaveStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftSaveMessage: isDraftConflictError(error)
              ? "保存冲突：服务端版本更新了，请重新加载草稿或另存为新草稿；不会自动覆盖。"
              : "保存失败：草稿未写入；不会发送、不审批、不创建外部任务。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-save-as-new-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      const filtered = filterWorkspaceView(fixture, viewState);
      const idempotencyKey = `p1-gow-draft-new:${Date.now()}`;
      const payload = buildWorkspaceDraftPayload(fixture, filtered, filtered.viewState, { idempotencyKeyOverride: idempotencyKey });
      renderWithDraftUpdates({
        currentDraftId: "",
        currentDraftVersion: 0,
        currentDraftSnapshotHash: "",
        currentDraftIdempotencyKey: idempotencyKey,
        draftSaveStatus: "saving",
        draftSaveMessage: "正在另存为新脱敏草稿；不会执行。"
      });
      createDraft(payload)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            ...draftStateFromResponse(filtered.viewState, response, "已另存为新草稿；仍不可执行。"),
            currentDraftIdempotencyKey: idempotencyKey
          }));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            currentDraftIdempotencyKey: idempotencyKey,
            draftSaveStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftSaveMessage: "另存失败：未写入草稿表，不会发送。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-archive-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      if (!viewState.currentDraftId || viewState.currentDraftVersion <= 0) return;
      const filtered = filterWorkspaceView(fixture, viewState);
      renderWithDraftUpdates({
        draftSaveStatus: "saving",
        draftSaveMessage: "正在归档草稿；只更新 draft 状态，不删除 audit，不执行任务。"
      });
      archiveDraft(viewState.currentDraftId, viewState.currentDraftVersion)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, draftStateFromResponse(filtered.viewState, response, "草稿已归档；不会执行。")));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            draftSaveStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftSaveMessage: isDraftConflictError(error)
              ? "归档冲突：请重新加载草稿版本。"
              : "归档失败：未执行任何发送或外呼。"
          }));
        });
    });
  });
}

function attachKeyboardHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelector !== "function") return;
  const canvas = root.querySelector<HTMLElement>("[data-keyboard-navigation]");
  if (!canvas) return;
  canvas.addEventListener("keydown", (event) => {
    const allowedKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", " ", "Escape"];
    if (!allowedKeys.includes(event.key)) return;
    event.preventDefault();
    const filtered = filterWorkspaceView(fixture, viewState);
    const lanes = buildWorkspaceCanvasLanes(fixture, filtered, filtered.viewState);
    if (event.key === " ") {
      renderP1GroupOpsWorkspace(root, fixture, toggleMultiSelectedEntity(filtered.viewState, filtered.viewState.selectedEntityType, filtered.viewState.selectedEntityId));
      return;
    }
    renderP1GroupOpsWorkspace(root, fixture, moveWorkspaceCanvasSelection(lanes, filtered.viewState, event.key as WorkspaceKeyboardKey));
  });
}

export function renderP1GroupOpsWorkspace(
  root: HTMLElement,
  fixture: WorkspaceFixture = P1_GROUP_OPS_WORKSPACE_FIXTURE,
  viewState: WorkspaceViewState = createWorkspaceViewState(fixture)
): void {
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
  attachMultiSelectHandlers(root, fixture, filtered.viewState);
  attachBundleExportHandlers(root, fixture, filtered.viewState);
  attachDraftPersistenceHandlers(root, fixture, filtered.viewState);
  attachKeyboardHandlers(root, fixture, filtered.viewState);
}

function boot(): void {
  const root = document.getElementById("p1GroupOpsWorkspaceApp");
  if (!root) return;
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
  } else {
    boot();
  }
}
