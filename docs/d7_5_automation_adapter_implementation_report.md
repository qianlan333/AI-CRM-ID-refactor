# D7.5 Automation Adapter Implementation Report

## Summary

D7.5 adds formal fake/staging-disabled adapter boundaries for Automation writes, activation webhook receipt, OpenClaw push, workflow runtime, and agent runtime. The implementation preserves existing Automation fixture behavior and records deterministic adapter results through integration gateway contracts.

## Implemented Files

- `aicrm_next/integration_gateway/automation_contracts.py`
- `aicrm_next/integration_gateway/automation_adapters.py`
- `aicrm_next/automation_engine/application.py`
- `tools/automation_readonly_gray_smoke.py`
- `tools/compare_automation_conversion_parity.py`
- `tools/check_d7_5_automation_adapter_contract.py`
- `tests/test_d7_5_automation_adapter_contract.py`
- `tests/fixtures/old_automation_conversion/*.json`

## Adapter Coverage

| adapter | status | notes |
| --- | --- | --- |
| AutomationWriteGateway | fake_contract_ready | manual override, confirm conversion, enter silent, exit marketing, preview, audit |
| AutomationActivationGateway | fake_contract_ready | activation event receipt, payload normalization, preview, audit |
| OpenClawWebhookAdapter | fake_contract_ready | member/workflow context preview and fake push audit |
| AutomationWorkflowRuntimeAdapter | fake_contract_ready | enqueue/node/due workflow runtime intents only |
| AutomationAgentRuntimeAdapter | fake_contract_ready | run/generate/review agent runtime intents only |

## Mode Guards

Defaults are fake. Disabled mode returns `adapter_disabled`. Production mode without explicit enable flags returns `production_guard_failed`. Production mode with explicit flags still returns `production_not_implemented` in this slice.

## Idempotency And Audit

D7.5 reuses `aicrm_next/integration_gateway/idempotency.py` and `aicrm_next/integration_gateway/audit.py`. Repeated fake calls with the same idempotency key return the same fake result. Every adapter call creates an audit event, including disabled and guarded production calls.

## Automation Application Wiring

- Manual override uses `AutomationWriteGateway.override_followup_type`.
- Confirm conversion uses `AutomationWriteGateway.confirm_conversion`.
- Enter silent uses `AutomationWriteGateway.enter_silent`.
- Exit marketing uses `AutomationWriteGateway.exit_marketing`.
- Activation webhook fake path uses `AutomationActivationGateway.receive_activation_event`.
- OpenClaw fake push path uses `OpenClawWebhookAdapter.push_member_context`.
- Workflow runtime command wrappers use `AutomationWorkflowRuntimeAdapter`.
- Agent runtime command wrappers use `AutomationAgentRuntimeAdapter`.

Existing API outputs remain compatible. New fields are additive: `adapter_contract` and `side_effect_safety`.

## Side-Effect Safety

D7.5 did not execute:

- real automation write
- real activation webhook side effect
- real OpenClaw push
- real workflow runtime
- real agent runtime
- real external webhook
- WeCom call

No production, deploy, nginx, systemd, or traffic configuration was changed.

## Compatibility Evidence

Expected verification:

- `tools/check_d7_5_automation_adapter_contract.py`
- `tools/automation_readonly_gray_smoke.py`
- `tools/compare_automation_conversion_parity.py`
- `tests/test_d7_5_automation_adapter_contract.py`

Automation parity remains fixture/TestClient based and does not call old write endpoints.

## Not Implemented In D7.5

- real OpenClaw webhook delivery
- real workflow runtime execution
- real agent runtime execution
- real activation webhook side effects
- production automation write execution
- production credential loading
- production traffic cutover

## Risk Notes

- Workflow idempotency requires a future persistent dedupe key before real enqueue.
- Duplicated agent outputs require output-level idempotency and review state locking.
- OpenClaw webhook retry needs dead-letter and retry classification before real calls.
- Callback replay needs signature and replay windows before real activation senders.
- Execution records need transactional consistency before runtime execution.
- Manual override audit trail must preserve operator, reason, idempotency key, and audit id.

## Rollback

Set adapter modes to `disabled` or revert the D7.5 wiring. Legacy automation fallback remains retained for real writes, callbacks, runtime, agent, OpenClaw, and dispatch behavior.

## Next Step

Proceed to D7.5 validation review after checker, tests, smoke, and parity pass.
