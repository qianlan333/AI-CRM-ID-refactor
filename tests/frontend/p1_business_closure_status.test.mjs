import assert from "node:assert/strict";

import {
  canRenderGlobalPass,
  normalizeEvidenceStatus,
  scenarioNeedsOperatorAction,
  statusMeta
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/business_closure/status_model.js";

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

console.log("p1 business closure status model OK");
