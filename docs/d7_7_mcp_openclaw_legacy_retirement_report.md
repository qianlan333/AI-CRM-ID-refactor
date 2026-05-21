# D7.7 MCP / OpenClaw Legacy Adapter Retirement Report

## Summary

D7.7 adds formal fake/staging-disabled contracts for MCP and OpenClaw legacy compatibility. The work moves MCP customer context, recent messages, automation context, legacy tool-name compatibility, and OpenClaw context push preview into the AI-CRM Next adapter boundary.

This report is a retirement gate, not physical deletion. `openclaw_service/` still exists and remains retained.

## Implemented Boundaries

- `McpToolGateway`: lists, validates, previews, invokes, and audits MCP tool requests.
- `CustomerContextToolAdapter`: wraps customer resolution, customer context, timeline, and recent messages context.
- `AutomationContextToolAdapter`: wraps automation member context, pool summary, and execution-record context.
- `OpenClawLegacyBridgeAdapter`: builds fake OpenClaw payload previews and fake delivery records.
- `McpCompatibilityGateway`: maps legacy tool names and payloads and normalizes fake responses.

## Mode Guard

Default mode is fake. Disabled mode returns `adapter_disabled`. Production mode requires explicit flags and still fails closed in D7.7 with `production_guard_failed` or `production_not_implemented`.

Guard flags:

- `AICRM_NEXT_ENABLE_REAL_MCP_TOOLS`
- `AICRM_NEXT_ENABLE_REAL_OPENCLAW_BRIDGE`
- `AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK`

## Idempotency And Audit

The D7.7 adapters reuse the existing in-memory idempotency and audit helpers. Repeated fake calls with the same key return stable fake results. Audit records include adapter, operation, mode, key, side-effect flag, status, error code, and timestamp.

## Side-Effect Safety

D7.7 keeps these false:

- real OpenClaw call executed
- real MCP external call executed
- real external webhook executed
- real customer context write executed
- real traffic cutover executed

No production DB write, WeCom call, OAuth call, payment call, cloud call, or webhook delivery is implemented.

## Integration Notes

The MCP dispatcher now routes tool compatibility, validation, invocation, customer context, recent messages, and automation context through D7.7 boundaries. The Automation OpenClaw fake push path keeps the D7.5 `OpenClawWebhookAdapter` and adds the D7.7 `OpenClawLegacyBridgeAdapter` as a legacy compatibility gate.

Existing Customer and Automation parity shapes remain protected by fixture parity tests.

## Risk Notes

- Legacy tool-name drift is isolated by `McpCompatibilityGateway`.
- Stale customer context and stale automation context remain future staging concerns.
- Duplicate OpenClaw push risk is mitigated only by fake idempotency in this slice.
- MCP bearer token and OpenClaw token safety depends on target scrubbing in this fake boundary.
- Webhook replay protection remains a future real-call requirement.

## openclaw_service Gate

`openclaw_service/` is still present. It is not cleared for physical deletion. Any later deletion requires:

- D7.7 acceptance PASS
- live compatibility evidence
- rollback proof
- explicit human approval
- no stale import from AI-CRM Next runtime

## Rollback

Rollback is to disable the D7.7 modes or revert the D7.7 adapter-boundary patch. No real external state is changed by this slice.

## Next Steps

Run D7.7 validation. If accepted, continue with the next legacy adapter retirement planning step; do not enable real MCP/OpenClaw calls without a separate approved slice.
