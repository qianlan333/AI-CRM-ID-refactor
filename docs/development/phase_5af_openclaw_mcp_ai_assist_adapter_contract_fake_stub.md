# Phase 5AF OpenClaw / MCP / AI Assist Adapter Contract + Fake/Stub Readiness

## Status

- phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub
- contract and fake/stub readiness only
- no real MCP call
- no real OpenClaw call
- no real LLM or DeepSeek call
- no outbound send
- no prompt or credential leakage
- no production owner switch
- no fallback removal
- no production_compat change
- no timer / automation execution
- no delete_ready

## Contract Scope

This bundle covers the `/mcp` route family and related AI assist external capability surfaces as an external adapter boundary. It defines a contract-first fake/stub package for request/response shape, prompt/content redaction, idempotency, retry, timeout, error mapping, and evidence collection.

It does not implement a live MCP, OpenClaw, LLM, DeepSeek, outbound-send, timer, automation, or production owner cutover path. Existing AI assist and automation code remains reference-only for capability naming.

## Adapter Contract

The contract methods are:

- `plan_ai_assist_request(request, operator, idempotency_key)`: validates request shape, redacts prompt/context, computes `request_hash`, and returns fake/stub planning evidence.
- `redact_prompt_context(prompt, context)`: removes raw prompt, customer identifiers, credentials, and token-like values from evidence.
- `fake_stub_mcp_tool_call(tool_name, arguments, operator, idempotency_key)`: returns deterministic MCP tool-call evidence with `real_mcp_call_executed=false`.
- `fake_stub_openclaw_context_push(member_id, context, operator, idempotency_key)`: returns deterministic OpenClaw context-push evidence with `real_openclaw_call_executed=false`.
- `fake_stub_llm_completion(prompt, operator, idempotency_key)`: returns deterministic fake assistant text with `real_llm_call_executed=false` and `deepseek_call_executed=false`.
- `validate_idempotency_key(idempotency_key, request_hash)`: defines replay and conflict behavior.

Every method must return `side_effect_safety`, `request_hash`, `idempotency_key`, `result_status`, and timestamped evidence. Write-like dry-runs require an idempotency key. Same key plus same request hash returns replay evidence; same key plus a different request hash returns conflict evidence.

## Fake/Stub Behavior

Fake/stub mode returns deterministic responses only. It requires no MCP token, no OpenClaw credential, no LLM key, no DeepSeek key, no network, and no production environment. It does not print raw prompt text, raw context, customer identifiers, credentials, secrets, tokens, or provider responses. It never claims production success.

## Error Mapping

Required error codes:

- `mcp_config_missing`
- `openclaw_config_missing`
- `llm_config_missing`
- `prompt_required`
- `idempotency_key_required`
- `duplicate_idempotency_key`
- `request_hash_conflict`
- `real_mcp_call_not_enabled`
- `real_openclaw_call_not_enabled`
- `real_llm_call_not_enabled`
- `prompt_redaction_required`
- `credential_leak_risk`
- `adapter_unavailable`
- `forbidden_in_production_without_approval`

## Retry / Timeout / Idempotency Policy

Dry-run calls are retry safe because no external side effect is possible. Evidence records timeout policy as contract metadata only. Live retries, streaming, tool invocation, and provider backoff are not enabled in this bundle.

## Evidence Policy

Evidence must include:

- `adapter_mode`
- `real_mcp_call_executed=false`
- `real_openclaw_call_executed=false`
- `real_llm_call_executed=false`
- `deepseek_call_executed=false`
- `outbound_send_executed=false`
- `prompt_redacted=true`
- `credential_redacted=true`
- `operator`
- `idempotency_key`
- `request_hash`
- `result_status`
- `side_effect_safety`
- `timestamp`

## Production Behavior

Production behavior is unchanged. This bundle does not switch route ownership, remove fallback, narrow production_compat, enable wider rollout, or enable delete readiness.

## Phase 5AG Recommendation

Next: `phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag_bundle`.

That bundle must keep live MCP/OpenClaw/LLM calls disabled by default, require explicit owner approval and config review, and continue to forbid outbound send, prompt leakage, route owner switch, fallback removal, and production_compat changes.
