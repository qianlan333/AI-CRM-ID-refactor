# D7.7 MCP / OpenClaw Legacy Adapter Contract

## Scope

D7.7 establishes fake/staging-disabled adapter boundaries for MCP tool execution, customer context tools, automation context tools, OpenClaw legacy bridge compatibility, and legacy MCP tool-name compatibility. This slice does not physically remove `openclaw_service/`, does not call OpenClaw, does not call an external MCP service, does not send webhooks, does not write production data, and does not change production routing.

## Gateways

### McpToolGateway

Capabilities:

- `list_tools`
- `invoke_tool`
- `build_tool_preview`
- `validate_tool_request`
- `record_tool_audit`

### CustomerContextToolAdapter

Capabilities:

- `resolve_customer`
- `get_customer_context`
- `get_customer_timeline`
- `get_recent_messages`
- `build_customer_context_preview`
- `record_customer_context_audit`

### AutomationContextToolAdapter

Capabilities:

- `get_member_context`
- `get_pool_summary`
- `get_execution_records`
- `build_automation_context_preview`
- `record_automation_context_audit`

### OpenClawLegacyBridgeAdapter

Capabilities:

- `build_openclaw_context_payload`
- `push_context_to_openclaw`
- `resolve_legacy_skill_request`
- `build_legacy_bridge_preview`
- `record_openclaw_bridge_audit`

### McpCompatibilityGateway

Capabilities:

- `map_legacy_tool_name`
- `map_legacy_payload`
- `normalize_tool_response`
- `build_compatibility_preview`
- `record_compatibility_audit`

## Stable Result Shape

Every method returns:

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

Targets may include `external_userid`, `person_id`, `member_id`, `tool_name`, `skill_name`, `request_id`, `context_type`, and `openclaw_context_id`. Targets must not contain real secrets, MCP bearer tokens, OpenClaw tokens, or webhook tokens.

## Mode Behavior

- `fake`: deterministic fake result, in-memory audit, no external call.
- `disabled`: stable `adapter_disabled` error, in-memory audit, no external call.
- `staging`: staging-shaped fake result, in-memory audit, no external call.
- `production`: requires explicit env flag. In D7.7 it still fails closed with `production_guard_failed` or `production_not_implemented`.

## Env Flags

Mode env:

- `AICRM_NEXT_MCP_TOOL_MODE=fake`
- `AICRM_NEXT_OPENCLAW_LEGACY_MODE=fake`
- `AICRM_NEXT_CUSTOMER_CONTEXT_TOOL_MODE=fake`
- `AICRM_NEXT_AUTOMATION_CONTEXT_TOOL_MODE=fake`

Real-call guard env:

- `AICRM_NEXT_ENABLE_REAL_MCP_TOOLS=true`
- `AICRM_NEXT_ENABLE_REAL_OPENCLAW_BRIDGE=true`
- `AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK=true`

These flags are guard inputs only in D7.7. They do not enable real OpenClaw or external MCP execution in this slice.

## Idempotency And Audit

Idempotency keys are derived from operation plus tool, request, customer, member, or context identifiers. Repeated fake calls with the same idempotency key return the same fake result.

Audit records are in-memory and include:

- `audit_id`
- `adapter`
- `operation`
- `mode`
- `idempotency_key`
- `side_effect_executed`
- `status`
- `error_code`
- `created_at`

## Side-Effect Safety

All D7.7 methods report:

- `real_openclaw_call_executed=false`
- `real_mcp_external_call_executed=false`
- `real_external_webhook_executed=false`
- `real_customer_context_write_executed=false`
- `real_traffic_cutover_executed=false`

## API Compatibility

MCP `tools/list` keeps the existing tools list shape and adds adapter metadata. MCP `tools/call` continues to return `content` and `structuredContent`. Customer context and recent messages continue using the Customer Read Model shape. Automation context is exposed as a readonly context tool and does not execute automation writes, workflow runtime, agent runtime, or OpenClaw webhooks.

## OpenClaw / MCP Risk Notes

- Tool name compatibility is handled by `McpCompatibilityGateway`.
- Context payload drift is isolated behind preview builders and audit.
- Stale customer context remains a future staging risk.
- Duplicated OpenClaw pushes are blocked by idempotency keys and fake delivery ids.
- MCP bearer token safety is enforced by target scrubbing.
- Webhook replay remains pending for any future real webhook implementation.
- Legacy skill compatibility is fake-only in this slice.

## openclaw_service Retirement Gate

`openclaw_service/` remains present and retained as legacy reference/fallback. D7.7 only establishes a fake compatibility gate; physical deletion requires later evidence, rollback proof, and explicit approval.

## Rollback

Disable the D7.7 adapters by mode env, or revert this adapter-boundary slice. Because no real external call or production write is performed, rollback is code/config-only.

## Next Steps

Run D7.7 checker, targeted tests, Customer smoke/parity, Automation smoke/parity, and six parity checks before acceptance review. Real MCP/OpenClaw integration remains pending.
