import {
  type WorkspaceEntityType,
  type WorkspaceFixture,
  type WorkspaceSelectionState
} from "./workspace_fixture.js";

export type WorkspacePanelMode = "summary" | "detail" | "guardrail";
export type WorkspaceFilterValue = "all" | string;
export type WorkspaceCanvasLaneId = "plans" | "groups" | "nodes" | "executions" | "push_center" | "evidence";
export type WorkspaceCanvasSortMode =
  | "default"
  | "status"
  | "entity_type"
  | "updated_or_created_time"
  | "blocked_first"
  | "action_required_first";
export type WorkspaceCanvasGroupMode = "entity_lane";
export type WorkspaceDensity = "compact" | "comfortable";

export const WORKSPACE_CANVAS_LANE_IDS: WorkspaceCanvasLaneId[] = [
  "plans",
  "groups",
  "nodes",
  "executions",
  "push_center",
  "evidence"
];

export const WORKSPACE_CANVAS_SORT_MODES: WorkspaceCanvasSortMode[] = [
  "default",
  "status",
  "entity_type",
  "updated_or_created_time",
  "blocked_first",
  "action_required_first"
];

export const WORKSPACE_CANVAS_GROUP_MODES: WorkspaceCanvasGroupMode[] = ["entity_lane"];

export type WorkspaceLaneCollapsedState = Record<WorkspaceCanvasLaneId, boolean>;

export interface WorkspaceViewState {
  keyword: string;
  planStatusFilter: WorkspaceFilterValue;
  entityTypeFilter: "all" | WorkspaceEntityType;
  executionStatusFilter: WorkspaceFilterValue;
  pushCenterStatusFilter: WorkspaceFilterValue;
  selectedEntityType: WorkspaceEntityType;
  selectedEntityId: string;
  panelMode: WorkspacePanelMode;
  laneCollapsedState: WorkspaceLaneCollapsedState;
  canvasSortMode: WorkspaceCanvasSortMode;
  canvasGroupMode: WorkspaceCanvasGroupMode;
  visibleLaneIds: WorkspaceCanvasLaneId[];
  density: WorkspaceDensity;
  focusedCanvasLaneId: WorkspaceCanvasLaneId;
  focusedCanvasCardId: string;
}

function defaultLaneCollapsedState(): WorkspaceLaneCollapsedState {
  return {
    plans: false,
    groups: false,
    nodes: false,
    executions: false,
    push_center: false,
    evidence: false
  };
}

function selectedIdFromSelection(selection: WorkspaceSelectionState): string {
  if (selection.selectedEntityType === "plan") return selection.selectedPlanId;
  if (selection.selectedEntityType === "group") return selection.selectedGroupId;
  if (selection.selectedEntityType === "node") return selection.selectedNodeId;
  if (selection.selectedEntityType === "execution") return selection.selectedExecutionId;
  if (selection.selectedEntityType === "push_center") return selection.selectedPushCenterJobId;
  return "evidence";
}

export function createWorkspaceViewState(fixture: WorkspaceFixture): WorkspaceViewState {
  return {
    keyword: "",
    planStatusFilter: "all",
    entityTypeFilter: "all",
    executionStatusFilter: "all",
    pushCenterStatusFilter: "all",
    selectedEntityType: fixture.defaultSelection.selectedEntityType,
    selectedEntityId: selectedIdFromSelection(fixture.defaultSelection),
    panelMode: "detail",
    laneCollapsedState: defaultLaneCollapsedState(),
    canvasSortMode: "default",
    canvasGroupMode: "entity_lane",
    visibleLaneIds: [...WORKSPACE_CANVAS_LANE_IDS],
    density: "comfortable",
    focusedCanvasLaneId: "plans",
    focusedCanvasCardId: selectedIdFromSelection(fixture.defaultSelection)
  };
}

export function selectEntityInViewState(
  viewState: WorkspaceViewState,
  selectedEntityType: WorkspaceEntityType,
  selectedEntityId: string
): WorkspaceViewState {
  return {
    ...viewState,
    selectedEntityType,
    selectedEntityId,
    panelMode: selectedEntityType === "evidence" ? "guardrail" : "detail",
    focusedCanvasLaneId: selectedEntityType === "plan"
      ? "plans"
      : selectedEntityType === "group"
        ? "groups"
        : selectedEntityType === "node"
          ? "nodes"
          : selectedEntityType === "execution"
            ? "executions"
            : selectedEntityType === "push_center"
              ? "push_center"
              : "evidence",
    focusedCanvasCardId: selectedEntityId
  };
}

export function updateWorkspaceViewState(
  viewState: WorkspaceViewState,
  updates: Partial<WorkspaceViewState>
): WorkspaceViewState {
  return {
    ...viewState,
    ...updates,
    keyword: updates.keyword !== undefined ? updates.keyword.trim() : viewState.keyword,
    laneCollapsedState: updates.laneCollapsedState
      ? { ...viewState.laneCollapsedState, ...updates.laneCollapsedState }
      : viewState.laneCollapsedState,
    visibleLaneIds: updates.visibleLaneIds ? [...updates.visibleLaneIds] : viewState.visibleLaneIds,
    focusedCanvasLaneId: updates.focusedCanvasLaneId || viewState.focusedCanvasLaneId,
    focusedCanvasCardId: updates.focusedCanvasCardId || viewState.focusedCanvasCardId
  };
}

export function toggleWorkspaceCanvasLane(
  viewState: WorkspaceViewState,
  laneId: WorkspaceCanvasLaneId
): WorkspaceViewState {
  return updateWorkspaceViewState(viewState, {
    laneCollapsedState: {
      ...viewState.laneCollapsedState,
      [laneId]: !viewState.laneCollapsedState[laneId]
    }
  });
}

export function selectionFromViewState(
  fixture: WorkspaceFixture,
  viewState: WorkspaceViewState
): WorkspaceSelectionState {
  const selection = { ...fixture.defaultSelection, selectedEntityType: viewState.selectedEntityType };
  if (viewState.selectedEntityType === "plan") selection.selectedPlanId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "group") selection.selectedGroupId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "node") selection.selectedNodeId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "execution") selection.selectedExecutionId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "push_center") selection.selectedPushCenterJobId = viewState.selectedEntityId;
  return selection;
}
