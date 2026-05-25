# Phase 4CF Agent Outputs Repository Adapter Parity Bundle

## Bundle type

Repository adapter parity bundle.

## Included stages

- SQLAlchemy repository adapter planning and implementation for `/api/admin/automation-conversion/agent-outputs*`.
- Route-specific test/staging DB flags.
- Local test DB parity harness.
- Checker and tests for adapter safety, URL safety, and phase state.
- `phase_execution_state.yaml` update for the next Phase 4 bundle.

## Excluded stages

- Production route owner switch.
- Production repository enablement.
- Production write.
- Legacy fallback narrowing or removal.
- Export job creation.
- File download runtime.
- Agent-output generation.
- Agent-run, workflow, or task execution.
- LLM, DeepSeek, OpenClaw, MCP, WeCom, Payment, OAuth, or other live external calls.
- Timer or outbound send behavior.
- Canary approval or `delete_ready=true`.

## Route family

`/api/admin/automation-conversion/agent-outputs*`

## Runtime behavior

This bundle adds an explicit SQLAlchemy read/detail repository adapter for agent-output metadata. It is only selected when `AICRM_AGENT_OUTPUTS_REPO_BACKEND` is set to a SQL backend and a route-specific test or staging DB URL is provided.

The default backend remains fixture/local. Agent-output list/detail behavior remains metadata-only and does not create exports, downloads, generated output, or external side effects.

## Production behavior

Production owner is unchanged. The adapter has no `DATABASE_URL` fallback and requires `AICRM_AGENT_OUTPUTS_TEST_DATABASE_URL` or `AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL` when enabled. The package does not authorize production DB access, production writes, production route owner switch, or production repository route enablement.

## Fallback behavior

Legacy production fallback remains available. This bundle does not narrow or remove `production_compat`, legacy forwards, or wildcard fallback behavior.

## Verification

- `python3 tools/check_phase4cf_agent_outputs_repository_adapter_parity_bundle.py --output-md /tmp/phase4cf_agent_outputs_repository_adapter_parity_bundle.md --output-json /tmp/phase4cf_agent_outputs_repository_adapter_parity_bundle.json`
- `python3 tools/run_phase4cf_agent_outputs_adapter_parity.py --output-md /tmp/phase4cf_agent_outputs_adapter_parity.md --output-json /tmp/phase4cf_agent_outputs_adapter_parity.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4cf_agent_outputs_repository_adapter_parity_bundle.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to a disabled-by-default test/staging adapter path. Rollback is to revert this PR; the default fixture/local backend and production legacy fallback remain unchanged.

## Business continuity

Current production users continue on the existing production-compatible route owner and legacy fallback. This bundle only prepares a test/staging parity path for internal-write replacement evidence.

## Business value

This gives operators a safer path to validate agent-output metadata reads from a real table shape before any production route switch is considered. It keeps export/download/generation and external behavior out of scope, reducing migration risk while moving Phase 4 beyond planning.

## Architecture boundary

Capability owner: `aicrm_next.automation_engine`. The adapter stays in the repository layer and returns the existing application/domain projections. It does not change API routing, production compatibility behavior, external adapters, deployment config, schema migrations, or legacy fallback ownership.

## Safety / non-goals

This is a canonical Phase 4 internal-write preparation bundle. It is not Phase 5 external adapter replacement, not Phase 6 `production_compat` narrowing/removal, and not Phase 7 legacy retirement.

## Autopilot decision

Autopilot can classify this as deliverable when the package checker passes, required checks are green, and no forbidden live production/external behavior is enabled by default.

## Next bundle recommendation

Proceed to `phase_4cg_agent_runs_repository_adapter_parity_bundle` for `/api/admin/automation-conversion/agent-runs*`, keeping it read/detail metadata-only with route-specific test/staging DB flags.

## PR lifecycle

Create as a compressed Phase 4 bundle, wait for checks, then admin-merge only if the eligibility gate is true and GitHub required checks are green.

## Smaller PRs replaced / estimated PR-count reduction

This replaces separate PRs for adapter planning, adapter implementation, test DB harness, checker/test updates, and phase-state handoff. Estimated PR-count reduction: 60 percent.
