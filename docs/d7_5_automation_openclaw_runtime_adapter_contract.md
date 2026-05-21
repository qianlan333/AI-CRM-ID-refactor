# D7.5 Automation / OpenClaw / Runtime Adapter Contract

## Scope

D7.5 defines fake/staging-disabled adapter boundaries for Automation manual override, confirm conversion, activation webhook receipt, OpenClaw context push, workflow runtime, and agent runtime. This slice does not call OpenClaw, does not send external webhooks, does not execute workflow or agent runtime, does not call WeCom, and does not modify production configuration.

## Adapter Result Shape

Every D7.5 adapter method returns:

- `ok`
- `adapter`
- `mode`
- `operation`
- `idempotency_key`
- `target`
- `result`
- `audit_id`
- `side_effect_executed`
- `error_code`
- `error_message`

`target` may include `member_id`, `external_userid`, `program_id`, `workflow_id`, `node_id`, `execution_id`, `agent_task_id`, `openclaw_context_id`, and `activation_event_id`. Secret-like fields are scrubbed from targets and payload summaries.

## AutomationWriteGateway

Methods:

- `override_followup_type`
- `confirm_conversion`
- `enter_silent`
- `exit_marketing`
- `build_write_preview`
- `record_write_audit`

The gateway records a deterministic fake write result, idempotency key, and audit event. Existing Next automation fixture commands keep their response shape and add adapter metadata plus side-effect safety flags.

## AutomationActivationGateway

Methods:

- `receive_activation_event`
- `normalize_activation_payload`
- `build_activation_preview`
- `record_activation_audit`

The gateway records activation receipt and normalization previews. The existing fake activation endpoint remains fixture-only and adds adapter metadata; no activation webhook side effect is executed.

## OpenClawWebhookAdapter

Methods:

- `push_member_context`
- `push_workflow_context`
- `build_openclaw_payload_preview`
- `record_openclaw_audit`

The adapter builds safe payload previews and deterministic fake request ids. It never calls OpenClaw or any external webhook in D7.5.

## AutomationWorkflowRuntimeAdapter

Methods:

- `enqueue_workflow_run`
- `run_workflow_node`
- `run_due_workflows`
- `build_workflow_runtime_preview`
- `record_workflow_runtime_audit`

The adapter records fake workflow runtime intents only. It does not enqueue real workers, execute nodes, or run due workflows.

## AutomationAgentRuntimeAdapter

Methods:

- `run_agent_task`
- `generate_agent_output`
- `review_agent_output`
- `build_agent_runtime_preview`
- `record_agent_runtime_audit`

The adapter records fake agent runtime intents only. It does not invoke a model/tool runtime and does not create production agent outputs.

## Modes

| mode | behavior |
| --- | --- |
| `fake` | deterministic fake result, audit event, idempotency, no side effect |
| `disabled` | stable disabled error with audit event |
| `staging` | staging-shaped fake result, audit event, no side effect |
| `production` | requires explicit env guard; real behavior is not implemented in D7.5 and fails closed |

Default modes:

- `AICRM_NEXT_AUTOMATION_WRITE_MODE=fake`
- `AICRM_NEXT_AUTOMATION_ACTIVATION_MODE=fake`
- `AICRM_NEXT_OPENCLAW_WEBHOOK_MODE=fake`
- `AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME_MODE=fake`
- `AICRM_NEXT_AUTOMATION_AGENT_RUNTIME_MODE=fake`

Production guards:

- `AICRM_NEXT_ENABLE_REAL_AUTOMATION_WRITES=true`
- `AICRM_NEXT_ENABLE_REAL_AUTOMATION_ACTIVATION=true`
- `AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK=true`
- `AICRM_NEXT_ENABLE_REAL_AUTOMATION_WORKFLOW_RUNTIME=true`
- `AICRM_NEXT_ENABLE_REAL_AUTOMATION_AGENT_RUNTIME=true`

Without the explicit guard, production mode returns `production_guard_failed`. With the explicit guard, this D7.5 slice still returns `production_not_implemented`.

## Idempotency

Idempotency keys use `operation + canonical target/payload`. Repeated fake operations with the same key return the same deterministic fake result. This is required for manual override replay, activation callback replay, OpenClaw retry, workflow enqueue retry, and duplicated agent output prevention.

## Audit

All modes write an in-memory audit event with:

- `audit_id`
- `adapter`
- `operation`
- `mode`
- `idempotency_key`
- `side_effect_executed`
- `status`
- `error_code`
- `created_at`

The D7.5 slice does not connect audit events to a production database.

## Side-Effect Safety

The following flags remain false in fake, disabled, staging, and guarded production behavior:

- `real_automation_write_executed`
- `real_activation_webhook_executed`
- `real_openclaw_push_executed`
- `real_workflow_runtime_executed`
- `real_agent_runtime_executed`
- `real_external_webhook_executed`

## API Compatibility

Existing Automation readonly endpoints and fake write/stub endpoints keep their previous top-level response shape. D7.5 only adds additive `adapter_contract` and `side_effect_safety` metadata.

## Risk Notes

- Workflow idempotency: future real enqueue must dedupe by workflow/member/execution/node.
- Duplicated agent outputs: future real generation must require output idempotency and review state guards.
- OpenClaw webhook retry: future real push must separate transient retry from duplicate delivery.
- Callback replay: activation receipt must be replay-safe before real sender integration.
- Execution record consistency: fake records stay fixture-bound; future real records need transactional consistency.
- Manual override audit trail: every manual state change must retain operator, reason, idempotency key, and audit id.

## Rollback

Rollback is flag-disable first: set modes to `disabled` or revert D7.5 adapter wiring. Legacy automation fallback remains retained for real runtime/write/external capabilities.

## Next Steps

Run D7.5 checker, automation smoke, automation parity, and D7.5 tests. Real OpenClaw, workflow runtime, agent runtime, activation side effects, and production write behavior remain future work after separate approval.
