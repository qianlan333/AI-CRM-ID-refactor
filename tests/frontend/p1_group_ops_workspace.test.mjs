import assert from "node:assert/strict";

import { renderP1GroupOpsWorkspace } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_layout.js";
import {
  DEFAULT_WORKSPACE_API_CONFIG,
  loadGroupOpsWorkspaceData
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_api.js";
import {
  filterWorkspaceView
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_filters.js";
import {
  buildWorkspaceCanvasLanes
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_grouping.js";
import {
  sortCanvasCards
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_sorting.js";
import {
  createWorkspaceSelectionState,
  findWorkspaceDetail,
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_detail.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_fixture.js";
import {
  buildGroupOpsWorkspaceStatusModel,
  workspaceCanRenderGlobalPass
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_status.js";
import {
  createWorkspaceViewState,
  selectEntityInViewState,
  toggleWorkspaceCanvasLane,
  updateWorkspaceViewState
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_view_state.js";

function assertNoSensitiveFixtureStrings(value) {
  for (const forbidden of [
    "raw_external_userid",
    "receiver_plaintext",
    "wrOgAAA001",
    "owner_001",
    "raw_callback_body",
    "raw_target_list",
    "raw_member_id",
    "openid",
    "unionid",
    "Authorization",
    "access_token",
    "corpsecret",
    "suite secret",
    "fixture text",
    "13800138000",
    "secret",
    "token"
  ]) {
    assert.equal(value.includes(forbidden), false, `unexpected sensitive fixture string: ${forbidden}`);
  }
}

const model = buildGroupOpsWorkspaceStatusModel(P1_GROUP_OPS_WORKSPACE_FIXTURE);
assert.deepEqual(model.originalStatuses, [
  "sent",
  "governance-missing",
  "downstream-pending",
  "external-config-blocked"
]);
assert.deepEqual(model.originalStatuses.slice().sort(), model.previewStatuses.slice().sort());
assert.equal(model.canClaimPass90Plus, false);
assert.equal(model.sentBypassesGovernance, false);
assert.equal(workspaceCanRenderGlobalPass(P1_GROUP_OPS_WORKSPACE_FIXTURE.payload), false);

for (const row of model.validations) {
  assert.equal(row.dropAllowed, false);
  assert.equal(row.statusAfterDrop, row.status);
  assert.ok(row.blockedReason.length > 0);
}

const governanceRow = model.validations.find((row) => row.status === "governance-missing");
assert.ok(governanceRow);
assert.ok(governanceRow.guardrails.includes("requires_approval"));
assert.ok(governanceRow.guardrails.includes("requires_allowlist"));
assert.ok(governanceRow.guardrails.includes("requires_gray_window"));

const sentRow = model.validations.find((row) => row.status === "sent");
assert.ok(sentRow);
assert.ok(sentRow.guardrails.includes("requires_push_center"));
assert.ok(sentRow.guardrails.includes("no_direct_send"));
assert.ok(sentRow.guardrails.includes("no_external_call"));
assert.ok(sentRow.guardrails.includes("no_production_write"));

const root = { innerHTML: "" };
renderP1GroupOpsWorkspace(root, P1_GROUP_OPS_WORKSPACE_FIXTURE);
assert.equal(root.innerHTML.includes("P1 Native workspace preview"), true);
assert.equal(root.innerHTML.includes("draft-only / preview-only"), true);
assert.equal(root.innerHTML.includes("计划 / 人群 / 任务"), true);
assert.equal(root.innerHTML.includes("Read-only grouped canvas"), true);
assert.equal(root.innerHTML.includes("Plans"), true);
assert.equal(root.innerHTML.includes("Audiences / Groups"), true);
assert.equal(root.innerHTML.includes("Tasks / Nodes"), true);
assert.equal(root.innerHTML.includes("Executions"), true);
assert.equal(root.innerHTML.includes("Push Center"), true);
assert.equal(root.innerHTML.includes("Evidence / Guardrails"), true);
assert.equal(root.innerHTML.includes("属性面板 / guardrail / evidence state"), true);
assert.equal(root.innerHTML.includes("Search / filters"), true);
assert.equal(root.innerHTML.includes("data-view-state-memory-only=\"true\""), true);
assert.equal(root.innerHTML.includes("data-canvas-local-state=\"true\""), true);
assert.equal(root.innerHTML.includes("data-canvas-sort-mode=\"default\""), true);
assert.equal(root.innerHTML.includes("data-canvas-group-mode=\"entity_lane\""), true);
assert.equal(root.innerHTML.includes("Plan detail"), true);
assert.equal(root.innerHTML.includes("Selected preview result"), true);
assert.equal(root.innerHTML.includes("Preview result / blocked reason"), true);
assert.equal(root.innerHTML.includes("data-p1-native-workspace=\"group_ops\""), true);
assert.equal(root.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(root.innerHTML.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(root.innerHTML.includes("data-production-write-executed=\"false\""), true);
assert.equal(root.innerHTML.includes("sent evidence 不等于 governance complete"), true);
assert.equal(root.innerHTML.includes("Push Center pending 不等于 completed"), true);
assert.equal(root.innerHTML.includes("evidence-incomplete 不等于 success"), true);
assert.equal(root.innerHTML.includes("P1_READY_WITH_EXCEPTIONS 不等于 PASS_90_PLUS"), true);
assert.equal(root.innerHTML.includes("data-selected-entity-type=\"plan\""), true);
assert.equal(root.innerHTML.includes("data-can-render-pass90=\"true\""), false);
assertNoSensitiveFixtureStrings(root.innerHTML);

const defaultSelection = createWorkspaceSelectionState(P1_GROUP_OPS_WORKSPACE_FIXTURE);
const selectedPlan = findWorkspaceDetail(P1_GROUP_OPS_WORKSPACE_FIXTURE, defaultSelection);
assert.equal(selectedPlan.entityType, "plan");

const defaultViewState = createWorkspaceViewState(P1_GROUP_OPS_WORKSPACE_FIXTURE);
const selectedNode = selectEntityInViewState(defaultViewState, "node", "node-preview-task");
const nodeRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(nodeRoot, P1_GROUP_OPS_WORKSPACE_FIXTURE, selectedNode);
assert.equal(nodeRoot.innerHTML.includes("data-selected-entity-type=\"node\""), true);
assert.equal(nodeRoot.innerHTML.includes("Node / task summary"), true);
assert.equal(nodeRoot.innerHTML.includes("preview-only"), true);
assertNoSensitiveFixtureStrings(nodeRoot.innerHTML);

const selectedExecution = selectEntityInViewState(defaultViewState, "execution", "execution-preview-empty");
const executionRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(executionRoot, P1_GROUP_OPS_WORKSPACE_FIXTURE, selectedExecution);
assert.equal(executionRoot.innerHTML.includes("data-selected-entity-type=\"execution\""), true);
assert.equal(executionRoot.innerHTML.includes("Execution summary"), true);
assert.equal(model.originalStatuses.includes("sent"), true);
assert.equal(buildGroupOpsWorkspaceStatusModel(P1_GROUP_OPS_WORKSPACE_FIXTURE).originalStatuses[0], "sent");
assertNoSensitiveFixtureStrings(executionRoot.innerHTML);

const requests = [];
const fixture = await loadGroupOpsWorkspaceData(DEFAULT_WORKSPACE_API_CONFIG, async (url) => {
  requests.push(url);
  if (url.includes("/plans?")) {
    return {
      ok: true,
      source_status: "fixture_local_contract",
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [
        {
          id: 7,
          plan_name: "真实群运营计划",
          plan_type: "standard",
          status: "active",
          bound_group_count: 2,
          today_estimated_reach: 42,
          owner_userid: "owner_001"
        }
      ],
      total: 1
    };
  }
  if (url.endsWith("/7")) {
    return {
      ok: true,
      source_status: "fixture_local_contract",
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      plan: { id: 7, plan_name: "真实群运营计划", status: "active" },
      groups_summary: { bound_group_count: 2, estimated_reach: 42, internal_member_count: 3, external_member_count: 39 },
      nodes: [{ id: 1, action_title: "welcome", text_content: "fixture text" }]
    };
  }
  if (url.endsWith("/7/groups")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [{ chat_id: "wrOgAAA001", group_name_snapshot: "不可渲染群名" }],
      summary: { bound_group_count: 2, estimated_reach: 42 },
      total: 2
    };
  }
  if (url.endsWith("/7/nodes")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [{ id: 1, action_title: "welcome", text_content: "fixture text" }],
      total: 1
    };
  }
  if (url.includes("/7/executions")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [{ id: 11, status: "pending", raw_external_userid: "wrOgAAA001", phone: "13800138000" }],
      total: 1
    };
  }
  if (url.includes("/push-center/jobs")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      real_external_call_executed: false,
      items: [
        {
          projection_id: "external_effect_job:97",
          effective_status: "sent",
          retryable: false,
          operator_action_required: false
        }
      ],
      total: 1
    };
  }
  throw new Error(`Unexpected URL: ${url}`);
});

assert.equal(requests.length, 6);
assert.equal(fixture.dataBindingStatus, "real_data_bound");
assert.equal(fixture.dataSourceLabel, "fixture_local_contract");
assert.equal(fixture.realExternalCallExecuted, false);
assert.equal(fixture.productionWriteExecuted, false);
assert.equal(fixture.payload.canClaimPass90Plus, false);
assert.equal(fixture.leftRailItems.some((item) => item.label === "真实群运营计划"), true);
assert.equal(fixture.leftRailItems.some((item) => item.summary.includes("2 个绑定群")), true);
assert.equal(fixture.payload.scenarios.some((scenario) => scenario.status === "governance-missing"), true);
assert.equal(fixture.payload.scenarios.some((scenario) => scenario.status === "sent"), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "plan" && item.title === "真实群运营计划"), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "group" && item.fields.some((field) => field.label === "bound_group_count" && field.value === "2")), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "node"), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "execution" && item.fields.some((field) => field.value === "11")), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "push_center" && item.fields.some((field) => field.value === "external_effect_job:97")), true);

const realViewState = createWorkspaceViewState(fixture);
const keywordFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { keyword: "真实群运营" }));
assert.equal(keywordFiltered.visibleLeftRailItems.length, 1);
assert.equal(keywordFiltered.visibleLeftRailItems[0].entityType, "plan");
assert.equal(keywordFiltered.viewState.selectedEntityType, "plan");

const planStatusFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { planStatusFilter: "ready" }));
assert.equal(planStatusFiltered.visibleLeftRailItems.length, 1);
assert.equal(planStatusFiltered.visibleLeftRailItems[0].status, "ready");

const executionFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "execution", executionStatusFilter: "pending" }));
assert.equal(executionFiltered.visibleLeftRailItems.length, 1);
assert.equal(executionFiltered.visibleLeftRailItems[0].entityType, "execution");
assert.equal(executionFiltered.viewState.selectedEntityType, "execution");

const pushFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "push_center", pushCenterStatusFilter: "sent" }));
assert.equal(pushFiltered.visibleLeftRailItems.length, 1);
assert.equal(pushFiltered.visibleLeftRailItems[0].entityType, "push_center");

const evidenceFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "evidence" }));
assert.equal(evidenceFiltered.visibleLeftRailItems.length, 1);
assert.equal(evidenceFiltered.visibleLeftRailItems[0].entityType, "evidence");

const selectedPushThenPlanOnly = filterWorkspaceView(
  fixture,
  updateWorkspaceViewState(selectEntityInViewState(realViewState, "push_center", "push_center-external_effect_job:97"), { entityTypeFilter: "plan" })
);
assert.equal(selectedPushThenPlanOnly.viewState.selectedEntityType, "plan");
assert.equal(selectedPushThenPlanOnly.viewState.selectedEntityId, "plan-7");

const emptyFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { keyword: "no matching redacted item" }));
assert.equal(emptyFiltered.isEmpty, true);
assert.equal(emptyFiltered.viewState.panelMode, "summary");

const realRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realRoot, fixture);
assert.equal(realRoot.innerHTML.includes("真实群运营计划"), true);
assert.equal(realRoot.innerHTML.includes("real_data_bound"), true);
assert.equal(realRoot.innerHTML.includes("Search / filters"), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"plans\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"groups\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"nodes\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"executions\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"push_center\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"evidence\""), true);
assert.equal(realRoot.innerHTML.includes("Read-only data loaded"), true);
assert.equal(realRoot.innerHTML.includes("external_effect_job:97"), true);
assert.equal(realRoot.innerHTML.includes("wrOgAAA001"), false);
assert.equal(realRoot.innerHTML.includes("owner_001"), false);
assert.equal(realRoot.innerHTML.includes("不可渲染群名"), false);
assert.equal(realRoot.innerHTML.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(realRoot.innerHTML.includes("data-production-write-executed=\"false\""), true);
assert.equal(realRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assertNoSensitiveFixtureStrings(realRoot.innerHTML);

const lanes = buildWorkspaceCanvasLanes(fixture, filterWorkspaceView(fixture, realViewState), realViewState);
assert.deepEqual(lanes.map((lane) => lane.id), ["plans", "groups", "nodes", "executions", "push_center", "evidence"]);
assert.equal(lanes.every((lane) => lane.cards.length === 1), true);

const statusSorted = sortCanvasCards([
  { originalIndex: 0, status: "sent", entityType: "push_center", updatedOrCreatedTime: "" },
  { originalIndex: 1, status: "governance-missing", entityType: "evidence", updatedOrCreatedTime: "" },
  { originalIndex: 2, status: "pending", entityType: "execution", updatedOrCreatedTime: "" }
], "blocked_first");
assert.deepEqual(statusSorted.map((card) => card.status), ["governance-missing", "pending", "sent"]);

const collapsedViewState = toggleWorkspaceCanvasLane(realViewState, "push_center");
const collapsedLanes = buildWorkspaceCanvasLanes(fixture, filterWorkspaceView(fixture, collapsedViewState), collapsedViewState);
assert.equal(collapsedLanes.find((lane) => lane.id === "push_center").isCollapsed, true);
const collapsedRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(collapsedRoot, fixture, collapsedViewState);
assert.equal(collapsedRoot.innerHTML.includes("data-canvas-lane-id=\"push_center\" data-lane-collapsed=\"true\""), true);
assertNoSensitiveFixtureStrings(collapsedRoot.innerHTML);

const executionCanvasFilter = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "execution" }));
const executionLanes = buildWorkspaceCanvasLanes(fixture, executionCanvasFilter, executionCanvasFilter.viewState);
assert.equal(executionLanes.find((lane) => lane.id === "executions").cards.length, 1);
assert.equal(executionLanes.find((lane) => lane.id === "plans").cards.length, 0);

const realSelection = createWorkspaceViewState(fixture);
const realExecutionSelection = selectEntityInViewState(realSelection, "execution", "execution-plan-7");
const realExecutionRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realExecutionRoot, fixture, realExecutionSelection);
assert.equal(realExecutionRoot.innerHTML.includes("data-selected-entity-type=\"execution\""), true);
assert.equal(realExecutionRoot.innerHTML.includes("Execution summary"), true);
assert.equal(realExecutionRoot.innerHTML.includes("pending"), true);
assert.equal(realExecutionRoot.innerHTML.includes("wrOgAAA001"), false);
assert.equal(realExecutionRoot.innerHTML.includes("13800138000"), false);
assertNoSensitiveFixtureStrings(realExecutionRoot.innerHTML);

const realPushSelection = selectEntityInViewState(realSelection, "push_center", "push_center-external_effect_job:97");
const realPushRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realPushRoot, fixture, realPushSelection);
assert.equal(realPushRoot.innerHTML.includes("data-selected-entity-type=\"push_center\""), true);
assert.equal(realPushRoot.innerHTML.includes("Push Center projection summary"), true);
assert.equal(realPushRoot.innerHTML.includes("governance complete"), true);
assertNoSensitiveFixtureStrings(realPushRoot.innerHTML);

const emptyFixture = await loadGroupOpsWorkspaceData(DEFAULT_WORKSPACE_API_CONFIG, async (url) => {
  if (url.includes("/plans?")) {
    return { ok: true, source_status: "fixture_empty", items: [], total: 0 };
  }
  throw new Error(`Unexpected URL for empty fixture: ${url}`);
});
const emptyRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(emptyRoot, emptyFixture);
assert.equal(emptyFixture.dataBindingStatus, "real_data_unavailable");
assert.equal(emptyRoot.innerHTML.includes("Read-only API unavailable"), true);
assert.equal(emptyRoot.innerHTML.includes("data-real-data-unavailable=\"true\""), true);
assert.equal(emptyRoot.innerHTML.includes("PASS_90_PLUS"), true);
assert.equal(emptyRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assertNoSensitiveFixtureStrings(emptyRoot.innerHTML);

const filteredRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(filteredRoot, fixture, updateWorkspaceViewState(realViewState, { keyword: "no matching redacted item" }));
assert.equal(filteredRoot.innerHTML.includes("Empty search result"), true);
assert.equal(filteredRoot.innerHTML.includes("data-empty-search-result=\"true\""), true);
assert.equal(filteredRoot.innerHTML.includes("external_effect_job:97"), true);
assertNoSensitiveFixtureStrings(filteredRoot.innerHTML);

console.log("p1 native group ops workspace OK");
