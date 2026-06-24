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
        panelMode: "detail"
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
        keyword: updates.keyword !== undefined ? updates.keyword.trim() : viewState.keyword
    };
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
