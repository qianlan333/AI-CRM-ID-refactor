# Phase 4BY Agent Replay Discovery Contract Bundle

## Summary

Phase 4BY compresses the remaining safe `/api/admin/automation-conversion/agent-replay` discovery work into one docs/tools/tests/state bundle. It carries forward Phase 4BQ metadata planning, confirms the route and schema surface, records the fixture/native contract for read-only replay metadata, and pauses replay runtime because replay/orchestration/generation behavior is outside the safe autopilot lane.

This package does not implement runtime behavior. It does not create or execute replay jobs, create or execute agent runs, call orchestration, generate outputs, call LLM/DeepSeek/OpenClaw/MCP, connect to production data, write production, switch route owner, modify `production_compat`, remove fallback, enable timers, or send outbound messages.

## Bundle Type

Discovery contract bundle.

## Included Stages

- Metadata planning carry-forward from Phase 4BQ.
- Legacy route and schema surface confirmation for `GET /api/admin/automation-conversion/agent-replay`.
- Fixture/native contract planning for read-only replay metadata.
- Machine-readable YAML contract.
- Phase-specific checker and tests.
- `phase_execution_state.yaml` update.
- Deferral record for unsafe replay runtime behavior.

## Excluded Stages

- Runtime implementation.
- Replay creation or replay execution.
- Agent-run creation or execution.
- Agent orchestration or replay orchestration.
- Agent-output generation.
- LLM, DeepSeek, OpenClaw, or MCP runtime calls.
- WeCom, Payment, OAuth, or other live external calls.
- Workflow execution, task execution, timers, run-due, outbound send.
- Production DB connection, production write, production route owner switch.
- `production_compat` change.
- Legacy fallback narrowing or removal.
- Canary approval or `delete_ready=true`.

## Route Family

- `/api/admin/automation-conversion/agent-replay`
- Capability owner: `aicrm_next.automation_engine`
- Current production owner: `production_compat`
- Production behavior: `legacy_forward`
- Legacy fallback: retained
- Fixture allowed in production: false

The confirmed manifest route surface is:

- `GET /api/admin/automation-conversion/agent-replay`
- `OPTIONS /api/admin/automation-conversion/agent-replay`
- `HEAD /api/admin/automation-conversion/agent-replay`

Only the `GET` metadata contract is planned for fixture/native work. `OPTIONS` and `HEAD` remain framework/compatibility handling and do not imply replay execution.

## Runtime Behavior

No runtime behavior is implemented in this bundle.

The future fixture/native contract is limited to read-only metadata rows that describe replay requests without executing them. A fixture/local response may include:

- `ok`
- `source_status`
- `route_owner`
- `rows`
- `total`
- `filters`
- `side_effect_safety`

Each row must keep side effects disabled and may expose only masked or synthetic metadata:

- `replay_request_id`
- `source_run_id`
- `request_id`
- `agent_code`
- `trigger_source`
- `replay_status`
- `replay_mode`
- `requested_by`
- `requested_at`
- `updated_at`
- `duration_ms`
- `blocked_reason`
- `side_effects_enabled`
- `masked_input_ref`
- `masked_output_ref`

The contract explicitly rejects fixture/local success in production mode. Production remains legacy-forwarded until a separate approved parity and owner-switch path exists.

## Production Behavior

Production behavior is unchanged. The route remains `production_compat` / `legacy_forward`; no production DB connection, production write, route owner switch, fallback removal, canary approval, or production readiness claim is introduced.

## Fallback Behavior

Legacy fallback remains required. Rollback is to revert this docs/tools/tests/state bundle; runtime traffic stays on the existing production compatibility path.

## Business Continuity

Operators keep the current replay API behavior through the existing legacy-forwarded path. This bundle only documents and validates the future safe metadata boundary, so it cannot interrupt current automation operations or accidentally execute replay side effects.

## Business Value

Agent replay sits near run execution and generated output surfaces, where accidental side effects are expensive. Bundling discovery, schema confirmation, fixture contract, and deferral into one package reduces PR churn while preserving a clear boundary: the team gets a ready contract for safe read-only metadata work, and the unsafe replay runtime remains paused until explicit approval.

## Safety / Non-Goals

- Fixture/local metadata is not production evidence.
- No replay, run, orchestration, generation, timer, or outbound behavior is enabled.
- No external adapter is called.
- No schema, migration, deploy, nginx, systemd, or production compatibility file is changed.
- No fallback narrowing is authorized.

## Verification

- `python3 tools/check_phase4by_agent_replay_discovery_contract_bundle.py --output-md /tmp/phase4by_agent_replay_discovery_contract_bundle.md --output-json /tmp/phase4by_agent_replay_discovery_contract_bundle.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4by_agent_replay_discovery_contract_bundle.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is limited to contract or checker misclassification. Rollback is a normal revert of this PR. Because no runtime path changes, rollback does not affect production traffic or legacy fallback behavior.

## Autopilot Decision

Autopilot selected a compressed discovery contract bundle. It replaces separate schema confirmation, fixture/native contract planning, deferral/state update, checker, and test micro-PRs for agent replay.

## PR Lifecycle

This PR is autopilot-safe when the package checker and standard eligibility gate pass, the diff remains docs/tools/tests/state only, and GitHub required checks are green.

## Next Bundle Recommendation

Proceed to `phase_4ca_task_groups_repository_adapter_parity_bundle`. Agent replay runtime stays paused until explicit owner approval covers replay/orchestration/generation behavior.
