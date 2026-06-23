import assert from "node:assert/strict";

import {
  canRenderGlobalPass,
  normalizeEvidenceStatus,
  scenarioNeedsOperatorAction,
  statusMeta
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/business_closure/status_model.js";
import { renderBusinessClosure } from "../../aicrm_next/frontend_compat/static/admin_console/p1/business_closure/business_closure_overview.js";
import {
  canInteractionClaimPass90Plus,
  dragPreviewForScenario,
  executionModeForStatus,
  guardrailsForScenario,
  validateDropIntent
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/interaction_contract.js";

const blocked = normalizeEvidenceStatus("external_config_blocked");
assert.equal(blocked, "external-config-blocked");
assert.equal(statusMeta(blocked).isSuccessComplete, false);

const governanceMissing = normalizeEvidenceStatus("governance_missing");
assert.equal(governanceMissing, "governance-missing");
assert.equal(statusMeta(governanceMissing).isSuccessComplete, false);

const downstreamPending = normalizeEvidenceStatus("downstream_pending");
assert.equal(downstreamPending, "downstream-pending");
assert.equal(statusMeta(downstreamPending).isSuccessComplete, false);

assert.equal(
  canRenderGlobalPass({
    finalVerdict: "P1_READY_WITH_EXCEPTIONS",
    canClaimPass90Plus: false,
    scenarios: [
      {
        key: "wecom_auth",
        title: "WeCom",
        status: "external-config-blocked",
        evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
        derivedStatus: "external_config_exception",
        summary: "",
        guardrail: ""
      }
    ]
  }),
  false
);

assert.equal(
  canRenderGlobalPass({
    finalVerdict: "PASS_90_PLUS",
    canClaimPass90Plus: true,
    scenarios: [
      {
        key: "ops_plan_broadcast",
        title: "Ops Plan",
        status: "downstream-pending",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "push_center_pending",
        summary: "",
        guardrail: ""
      }
    ]
  }),
  false
);

assert.equal(
  scenarioNeedsOperatorAction({
    key: "group_ops",
    title: "Group Ops",
    status: "governance-missing",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "sent_with_governance_residual_risk",
    summary: "",
    guardrail: ""
  }),
  true
);

assert.equal(executionModeForStatus("external-config-blocked"), "external_config_blocked");
assert.equal(executionModeForStatus("governance-missing"), "requires_approval");
assert.equal(executionModeForStatus("downstream-pending"), "preview_only");
assert.equal(executionModeForStatus("blocked"), "blocked");

const groupOpsScenario = {
  key: "group_ops",
  title: "Group Ops",
  status: "governance-missing",
  evidenceStatus: "EVIDENCE_COLLECTED",
  derivedStatus: "sent_with_governance_residual_risk",
  summary: "sent but governance incomplete",
  guardrail: "governance required"
};
const groupOpsGuardrails = guardrailsForScenario(groupOpsScenario);
assert.deepEqual(
  ["requires_approval", "requires_allowlist", "requires_gray_window"].every((item) => groupOpsGuardrails.includes(item)),
  true
);

const blockedNoop = validateDropIntent(groupOpsScenario, "blocked_noop");
assert.equal(blockedNoop.allowed, false);
assert.equal(blockedNoop.statusAfterDrop, "governance-missing");
assert.equal(blockedNoop.executionMode, "requires_approval");

const preview = dragPreviewForScenario({
  key: "wecom_auth",
  title: "WeCom",
  status: "external-config-blocked",
  evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
  derivedStatus: "external_config_exception",
  summary: "",
  guardrail: ""
});
assert.equal(preview.entity, "config_card");
assert.equal(preview.executionMode, "external_config_blocked");
assert.equal(preview.guardrails.includes("requires_external_config"), true);

assert.equal(
  canInteractionClaimPass90Plus({
    finalVerdict: "P1_READY_WITH_EXCEPTIONS",
    canClaimPass90Plus: false,
    scenarios: [groupOpsScenario]
  }),
  false
);

const root = { innerHTML: "" };
renderBusinessClosure(root, {
  finalVerdict: "P1_READY_WITH_EXCEPTIONS",
  canClaimPass90Plus: false,
  scenarios: [
    groupOpsScenario,
    {
      key: "wecom_auth",
      title: "WeCom",
      status: "external-config-blocked",
      evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
      derivedStatus: "external_config_exception",
      summary: "blocked",
      guardrail: "config required"
    },
    {
      key: "ops_plan_broadcast",
      title: "Ops Plan",
      status: "downstream-pending",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "push_center_pending",
      summary: "pending",
      guardrail: "do not mark completed"
    }
  ]
});
assert.equal(root.innerHTML.includes("data-drop-intent=\"blocked_noop\""), true);
assert.equal(root.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
for (const forbidden of ["raw_external_userid", "external_userid=", "13800138000", "Authorization", "access_token", "corpsecret"]) {
  assert.equal(root.innerHTML.includes(forbidden), false);
}

console.log("p1 business closure status model OK");
