import { type WorkspaceEntityType, type WorkspaceFixture, type WorkspaceSelectionState } from "./workspace_fixture.js";
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
export declare function createWorkspaceViewState(fixture: WorkspaceFixture): WorkspaceViewState;
export declare function selectEntityInViewState(viewState: WorkspaceViewState, selectedEntityType: WorkspaceEntityType, selectedEntityId: string): WorkspaceViewState;
export declare function updateWorkspaceViewState(viewState: WorkspaceViewState, updates: Partial<WorkspaceViewState>): WorkspaceViewState;
export declare function selectionFromViewState(fixture: WorkspaceFixture, viewState: WorkspaceViewState): WorkspaceSelectionState;
