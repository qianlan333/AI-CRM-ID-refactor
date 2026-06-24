import assert from "node:assert/strict";

import { renderP1GroupOpsWorkspace } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_layout.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_fixture.js";
import {
  buildGroupOpsWorkspaceStatusModel,
  workspaceCanRenderGlobalPass
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_status.js";

function assertNoSensitiveFixtureStrings(value) {
  for (const forbidden of [
    "raw_external_userid",
    "receiver_plaintext",
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

console.log("p1 native group ops workspace OK");
