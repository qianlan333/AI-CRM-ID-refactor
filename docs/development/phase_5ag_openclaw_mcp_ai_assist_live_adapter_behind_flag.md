# Phase 5AG OpenClaw / MCP / AI Assist Live Adapter Behind Explicit Flag

## Status

- phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag
- live adapter boundary implemented behind explicit flags
- live call disabled by default
- no real MCP call by default
- no real OpenClaw call by default
- no real LLM / DeepSeek call by default
- no outbound send
- no timer / run-due / automation execution
- no prompt or credential leakage
- no production owner switch
- no fallback removal
- no production_compat change
- delete_ready false

## Live Adapter Gates

The live adapter boundary requires all gates before any gateway path can be invoked:

- `AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_ADAPTER_ENABLED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_CALL_APPROVED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_CONFIG_REVIEWED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_ENDPOINT_REVIEWED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_CREDENTIAL_SOURCE_REVIEWED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_PROMPT_REDACTION_CONFIRMED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_NO_OUTBOUND_SEND_CONFIRMED=1`
- `AICRM_OPENCLAW_MCP_AI_ASSIST_NO_AUTOMATION_EXECUTION_CONFIRMED=1`
- idempotency key present
- explicit runner confirm flags

The default gateway is disabled and returns blocked evidence. This bundle adds the boundary and evidence gates only; it does not connect to a live MCP, OpenClaw, LLM, DeepSeek, or outbound-send provider.

## Implemented Methods

- `call_mcp_tool_live`
- `push_openclaw_context_live`
- `run_ai_assist_completion_live`

All responses include `request_hash`, `idempotency_key`, redaction flags, and `side_effect_safety`.

## Staging Evidence

The staging runner supports:

- `--dry-run-live-gate`
- `--execute-staging-live`
- `--confirm-live-call`
- `--confirm-staging-only`
- `--confirm-redaction`
- `--confirm-no-outbound-send`
- `--confirm-no-automation-execution`

It defaults blocked and never prints raw prompt, raw context, token, or credential values.

## Production Dry-Run Gate

The production runner is readiness-only. It requires `--dry-run`, `--confirm-no-production-live-call`, `--confirm-no-outbound-send`, and `--confirm-no-automation-execution`. It never executes a production provider call.

## Phase 5AH Recommendation

Next: `phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence_bundle`.

That bundle should provide staging-only canary evidence for one approved test prompt/tool call, with redacted evidence and no outbound send, automation execution, owner switch, fallback removal, or production_compat change.
