import { escapeHtml } from "../shared/dom.js";
import { renderStatusBadge } from "../shared/status_badge.js";
import { type FilteredWorkspaceView } from "./workspace_filters.js";
import { type WorkspaceFixture } from "./workspace_fixture.js";
import { buildWorkspaceCanvasLanes, type WorkspaceCanvasCard, type WorkspaceCanvasLane } from "./workspace_grouping.js";
import {
  WORKSPACE_CANVAS_GROUP_MODES,
  WORKSPACE_CANVAS_SORT_MODES,
  type WorkspaceCanvasGroupMode,
  type WorkspaceCanvasSortMode,
  type WorkspaceViewState
} from "./workspace_view_state.js";

function renderOption(value: string, currentValue: string): string {
  return `<option value="${escapeHtml(value)}"${value === currentValue ? " selected" : ""}>${escapeHtml(value)}</option>`;
}

function renderGuardrailChips(guardrail: string): string {
  return guardrail.split("/")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => `<code>${escapeHtml(item)}</code>`)
    .join(" ");
}

function selectedClass(card: WorkspaceCanvasCard, viewState: WorkspaceViewState): string {
  return card.entityType === viewState.selectedEntityType && card.detailId === viewState.selectedEntityId
    ? " p1-workspace-canvas-card--selected"
    : "";
}

function renderCanvasControls(viewState: WorkspaceViewState, lanes: WorkspaceCanvasLane[]): string {
  const laneToggles = lanes.map((lane) => `
    <button type="button" class="p1-workspace-lane-toggle" data-workspace-lane-toggle="${escapeHtml(lane.id)}" data-lane-collapsed="${lane.isCollapsed ? "true" : "false"}">
      ${escapeHtml(lane.title)}: ${lane.isCollapsed ? "collapsed" : "open"}
    </button>
  `).join("");
  return `
    <section class="p1-workspace-canvas-controls" data-canvas-local-state="true" data-visible-lane-ids="${escapeHtml(viewState.visibleLaneIds.join(","))}">
      <label>
        <span>Canvas sort</span>
        <select data-workspace-filter="canvasSortMode">
          ${WORKSPACE_CANVAS_SORT_MODES.map((mode: WorkspaceCanvasSortMode) => renderOption(mode, viewState.canvasSortMode)).join("")}
        </select>
      </label>
      <label>
        <span>Canvas group</span>
        <select data-workspace-filter="canvasGroupMode">
          ${WORKSPACE_CANVAS_GROUP_MODES.map((mode: WorkspaceCanvasGroupMode) => renderOption(mode, viewState.canvasGroupMode)).join("")}
        </select>
      </label>
      <div class="p1-workspace-lane-toggle-list" aria-label="Memory-only lane collapse controls">${laneToggles}</div>
    </section>
  `;
}

function renderCanvasCard(card: WorkspaceCanvasCard, viewState: WorkspaceViewState): string {
  return `
    <button type="button" class="p1-workspace-canvas-card${selectedClass(card, viewState)}" data-canvas-card-id="${escapeHtml(card.id)}" data-canvas-lane="${escapeHtml(card.laneId)}" data-entity-type="${escapeHtml(card.entityType)}" data-evidence-status="${escapeHtml(card.status)}" data-derived-status="${escapeHtml(card.derivedStatus)}" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false" data-workspace-select-type="${escapeHtml(card.entityType)}" data-workspace-select-id="${escapeHtml(card.detailId)}">
      <div class="p1-workspace-canvas-card__head">
        <span class="p1-drag-handle" aria-hidden="true">⋮⋮</span>
        <strong>${escapeHtml(card.title)}</strong>
        ${renderStatusBadge(card.status)}
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>Entity</dt><dd>${escapeHtml(card.entityType)}</dd></div>
        <div><dt>Evidence</dt><dd>${escapeHtml(card.evidenceStatus)}</dd></div>
        <div><dt>Derived</dt><dd>${escapeHtml(card.derivedStatus)}</dd></div>
      </dl>
      <p>${escapeHtml(card.summary)}</p>
      <p class="p1-workspace-guardrails">${renderGuardrailChips(card.guardrail)}</p>
      <p class="p1-drag-disabled-reason">Readonly grouped canvas: preview-only=true, production_write=false, real_external_call=false.</p>
    </button>
  `;
}

function renderCanvasLane(lane: WorkspaceCanvasLane, viewState: WorkspaceViewState): string {
  const cards = lane.cards.length > 0
    ? lane.cards.map((card) => renderCanvasCard(card, viewState)).join("")
    : `<section class="p1-workspace-empty-state" data-empty-lane="true" data-lane-id="${escapeHtml(lane.id)}"><strong>Empty lane</strong><p>${escapeHtml(lane.emptyReason)}</p></section>`;
  return `
    <section class="p1-workspace-canvas-lane" data-canvas-lane-id="${escapeHtml(lane.id)}" data-lane-collapsed="${lane.isCollapsed ? "true" : "false"}" data-card-count="${lane.cards.length}">
      <div class="p1-workspace-lane-head">
        <div>
          <h3>${escapeHtml(lane.title)}</h3>
          <p>${escapeHtml(lane.description)}</p>
        </div>
        ${renderStatusBadge(lane.cards.length > 0 ? lane.cards[0].status : "evidence-incomplete")}
      </div>
      ${lane.isCollapsed ? `<p class="p1-workspace-filter-summary">Lane collapsed in memory only; original evidence status is unchanged.</p>` : `<div class="p1-workspace-canvas-lane-grid">${cards}</div>`}
    </section>
  `;
}

export function renderGroupedWorkspaceCanvas(
  fixture: WorkspaceFixture,
  filtered: FilteredWorkspaceView,
  viewState: WorkspaceViewState
): string {
  const lanes = buildWorkspaceCanvasLanes(fixture, filtered, viewState);
  return `
    <section class="p1-workspace-canvas" aria-label="Read-only grouped canvas" data-draft-persistence="memory_only" data-canvas-group-mode="${escapeHtml(viewState.canvasGroupMode)}" data-canvas-sort-mode="${escapeHtml(viewState.canvasSortMode)}" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>Read-only grouped canvas</h2>
        <p>按 plan / audience / task / execution / Push Center / evidence 分 lane 展示；本地排序和折叠不保存、不执行、不外呼。</p>
      </div>
      ${renderCanvasControls(viewState, lanes)}
      <section class="p1-workspace-guardrail-summary" data-canvas-guardrail-summary="true">
        <strong>Canvas guardrails</strong>
        <p>preview-only；production_write=false；real_external_call=false；can_claim_pass_90_plus=false。</p>
        <p>sent evidence 不等于 governance complete；Push Center pending 不等于 completed；evidence-incomplete 不等于 success。</p>
      </section>
      <div class="p1-workspace-canvas-lanes">${lanes.map((lane) => renderCanvasLane(lane, viewState)).join("")}</div>
    </section>
  `;
}
