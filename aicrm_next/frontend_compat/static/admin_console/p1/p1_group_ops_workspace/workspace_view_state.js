export const WORKSPACE_CANVAS_LANE_IDS = [
    "plans",
    "groups",
    "nodes",
    "executions",
    "push_center",
    "evidence"
];
export const WORKSPACE_CANVAS_SORT_MODES = [
    "default",
    "status",
    "entity_type",
    "updated_or_created_time",
    "blocked_first",
    "action_required_first"
];
export const WORKSPACE_CANVAS_GROUP_MODES = ["entity_lane"];
function defaultLaneCollapsedState() {
    return {
        plans: false,
        groups: false,
        nodes: false,
        executions: false,
        push_center: false,
        evidence: false
    };
}
function selectedIdFromSelection(selection) {
    if (selection.selectedEntityType === "plan")
        return selection.selectedPlanId;
    if (selection.selectedEntityType === "group")
        return selection.selectedGroupId;
    if (selection.selectedEntityType === "node")
        return selection.selectedNodeId;
    if (selection.selectedEntityType === "execution")
        return selection.selectedExecutionId;
    if (selection.selectedEntityType === "push_center")
        return selection.selectedPushCenterJobId;
    return "evidence";
}
export function createWorkspaceViewState(fixture) {
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
        visibleLaneIds: [...WORKSPACE_CANVAS_LANE_IDS]
    };
}
export function selectEntityInViewState(viewState, selectedEntityType, selectedEntityId) {
    return {
        ...viewState,
        selectedEntityType,
        selectedEntityId,
        panelMode: selectedEntityType === "evidence" ? "guardrail" : "detail"
    };
}
export function updateWorkspaceViewState(viewState, updates) {
    return {
        ...viewState,
        ...updates,
        keyword: updates.keyword !== undefined ? updates.keyword.trim() : viewState.keyword,
        laneCollapsedState: updates.laneCollapsedState
            ? { ...viewState.laneCollapsedState, ...updates.laneCollapsedState }
            : viewState.laneCollapsedState,
        visibleLaneIds: updates.visibleLaneIds ? [...updates.visibleLaneIds] : viewState.visibleLaneIds
    };
}
export function toggleWorkspaceCanvasLane(viewState, laneId) {
    return updateWorkspaceViewState(viewState, {
        laneCollapsedState: {
            ...viewState.laneCollapsedState,
            [laneId]: !viewState.laneCollapsedState[laneId]
        }
    });
}
export function selectionFromViewState(fixture, viewState) {
    const selection = { ...fixture.defaultSelection, selectedEntityType: viewState.selectedEntityType };
    if (viewState.selectedEntityType === "plan")
        selection.selectedPlanId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "group")
        selection.selectedGroupId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "node")
        selection.selectedNodeId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "execution")
        selection.selectedExecutionId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "push_center")
        selection.selectedPushCenterJobId = viewState.selectedEntityId;
    return selection;
}
