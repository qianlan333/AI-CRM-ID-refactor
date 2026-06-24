import assert from "node:assert/strict";

import { renderP1GroupOpsWorkspace } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_layout.js";
import {
  DEFAULT_WORKSPACE_API_CONFIG,
  loadGroupOpsWorkspaceData
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_api.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_fixture.js";
import {
  buildGroupOpsWorkspaceStatusModel,
  workspaceCanRenderGlobalPass
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_status.js";

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
assert.equal(root.innerHTML.includes("编排预览区 / draft-only canvas shell"), true);
assert.equal(root.innerHTML.includes("属性面板 / guardrail / evidence state"), true);
assert.equal(root.innerHTML.includes("Preview result / blocked reason"), true);
assert.equal(root.innerHTML.includes("data-p1-native-workspace=\"group_ops\""), true);
assert.equal(root.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(root.innerHTML.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(root.innerHTML.includes("data-production-write-executed=\"false\""), true);
assert.equal(root.innerHTML.includes("sent evidence 不等于 governance complete"), true);
assert.equal(root.innerHTML.includes("P1_READY_WITH_EXCEPTIONS 不等于 PASS_90_PLUS"), true);
assert.equal(root.innerHTML.includes("data-can-render-pass90=\"true\""), false);
assertNoSensitiveFixtureStrings(root.innerHTML);

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
      items: [],
      total: 0
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

const realRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realRoot, fixture);
assert.equal(realRoot.innerHTML.includes("真实群运营计划"), true);
assert.equal(realRoot.innerHTML.includes("real_data_bound"), true);
assert.equal(realRoot.innerHTML.includes("external_effect_job:97"), true);
assert.equal(realRoot.innerHTML.includes("wrOgAAA001"), false);
assert.equal(realRoot.innerHTML.includes("owner_001"), false);
assert.equal(realRoot.innerHTML.includes("不可渲染群名"), false);
assert.equal(realRoot.innerHTML.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(realRoot.innerHTML.includes("data-production-write-executed=\"false\""), true);
assert.equal(realRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assertNoSensitiveFixtureStrings(realRoot.innerHTML);

console.log("p1 native group ops workspace OK");
