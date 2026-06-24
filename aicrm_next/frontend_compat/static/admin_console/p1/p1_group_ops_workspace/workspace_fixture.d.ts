import { type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";
export interface WorkspaceListItem {
    id: string;
    label: string;
    kind: "plan" | "audience" | "task";
    status: ScenarioEvidence["status"];
    summary: string;
}
export interface WorkspaceFixture {
    payload: BusinessClosurePayload;
    leftRailItems: WorkspaceListItem[];
    workspaceMode: "draft_only_preview_only";
    dataSourceLabel: string;
    dataBindingStatus: "fixture_fallback" | "real_data_bound" | "real_data_unavailable";
    realExternalCallExecuted: false;
    productionWriteExecuted: false;
}
export declare const GROUP_OPS_WORKSPACE_SCENARIOS: ScenarioEvidence[];
export declare const P1_GROUP_OPS_WORKSPACE_FIXTURE: WorkspaceFixture;
