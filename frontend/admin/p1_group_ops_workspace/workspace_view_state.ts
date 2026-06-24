import {
  type WorkspaceEntityType,
  type WorkspaceFixture,
  type WorkspaceSelectionState
} from "./workspace_fixture.js";

export type WorkspacePanelMode = "summary" | "detail" | "guardrail";
export type WorkspaceFilterValue = "all" | string;

export interface WorkspaceViewState {
  keyword: string;
  planStatusFilter: WorkspaceFilterValue;
  entityTypeFilter: "all" | WorkspaceEntityType;
  executionStatusFilter: WorkspaceFilterValue;
  pushCenterStatusFilter: WorkspaceFilterValue;
  selectedEntityType: WorkspaceEntityType;
  selectedEntityId: string;
  panelMode: WorkspacePanelMode;
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
    panelMode: "detail"
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
    panelMode: selectedEntityType === "evidence" ? "guardrail" : "detail"
  };
}

export function updateWorkspaceViewState(
  viewState: WorkspaceViewState,
  updates: Partial<WorkspaceViewState>
): WorkspaceViewState {
  return {
    ...viewState,
    ...updates,
    keyword: updates.keyword !== undefined ? updates.keyword.trim() : viewState.keyword
  };
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
