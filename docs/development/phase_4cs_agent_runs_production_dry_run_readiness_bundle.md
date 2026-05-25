# Phase 4CS Agent Runs Production Read-Only Dry-Run Readiness Bundle

## Summary

Phase 4CS adds a disabled-by-default production read-only dry-run readiness runner for `/api/admin/automation-conversion/agent-runs*`. The runner emits blocked evidence by default and only attempts a read-only count and redacted shape summary when approval, config review, backend, route-specific DB URL, and no-write flags are all present.

## Bundle type

production_readonly_dry_run_readiness_bundle

## Included stages

- production read-only dry-run runner
- blocked evidence output
- evidence gate
- package checker and tests
- autopilot allowlist updates
- phase execution state update
- PR lifecycle tracking

## Excluded stages

- production route owner switch
- production write enablement
- fallback removal or narrowing
- production_compat behavior change
- real external calls
- timer, run-due, or automation execution
- workflow, task, or agent execution
- replay or orchestration execution
- outbound send
- LLM, DeepSeek, OpenClaw, or MCP behavior
- destructive migration
- canary approval
- delete readiness

## Route family

`/api/admin/automation-conversion/agent-runs*`

## Runtime behavior

`tools/run_phase4cs_agent_runs_production_readonly_dry_run.py` defaults to blocked evidence without connecting to a database. It requires:

- `AICRM_PHASE4CS_PRODUCTION_READONLY_DRY_RUN_APPROVED=1`
- `AICRM_PHASE4CS_PRODUCTION_CONFIG_REVIEWED=1`
- `AICRM_AGENT_RUNS_REPO_BACKEND=sqlalchemy`
- `AICRM_AGENT_RUNS_READONLY_DRY_RUN_DATABASE_URL`
- `--read-only`
- `--confirm-no-writes`

When all gates are present, the runner emits only counts, redacted field presence, and shape keys. It does not export raw rows or PII.

## Production behavior

Production owner remains unchanged. The runner is not enabled by default and does not perform production writes. Missing approval, missing config review, missing backend, missing route-specific DB URL, or missing read-only flags returns `ok: true` blocked evidence with no DB connection.

## Fallback behavior

Legacy fallback is retained. The runner never falls back to shared database configuration, test DB configuration, staging DB configuration, fixture/local/demo data, or production_compat routes.

## Verification

- `python3 tools/check_phase4cs_agent_runs_production_dry_run_readiness_bundle.py --output-md /tmp/phase4cs_agent_runs_production_dry_run.md --output-json /tmp/phase4cs_agent_runs_production_dry_run.json`
- `python3 -m pytest tests/test_phase4cs_agent_runs_production_dry_run_readiness_bundle.py -q`
- `python3 tools/run_phase4cs_agent_runs_production_readonly_dry_run.py --output-json /tmp/phase4cs_runner_default.json --output-md /tmp/phase4cs_runner_default.md`
- `python3 -m py_compile ...`
- global autonomous loop, automerge, backlog, and diff checks

## Risk / rollback

Rollback is removal of the Phase 4CS docs, checker, test, state update, and disabled-by-default runner. No production route owner, fallback, production_compat, migration, or runtime execution behavior changes are made.

## Business continuity

Agent-run metadata readiness can be checked without changing live traffic or starting any run. Existing legacy behavior remains available, and the default result is blocked evidence rather than fake production success.

## Business value

This bundle moves agent-runs from staging readiness toward production read-only dry-run readiness while preserving the Phase 4 safety boundary for internal metadata route families.

## Architecture boundary

This is canonical Phase 4 only: internal write route-family replacement readiness. It does not enter Phase 5 external adapters, Phase 6 production_compat narrowing/removal, or Phase 7 legacy retirement.

## Safety / non-goals

The runner does not create, update, delete, run due tasks, start agent runs, execute replay, execute tasks or workflows, send outbound messages, call external systems, generate LLM output, switch owners, or remove fallback.

## Autopilot decision

Autopilot-deliverable when the package checker passes, global checks pass or report only existing baseline blockers, no forbidden files are changed, and GitHub checks are green.

## Next bundle recommendation

`phase_4ct_agent_outputs_production_dry_run_readiness_bundle` for `/api/admin/automation-conversion/agent-outputs*`.

## Smaller PRs replaced / estimated PR-count reduction

This compressed bundle replaces separate runner, blocked evidence, checker, tests, allowlist, and phase-state PRs, reducing the expected PR count by roughly 40-60 percent for this route family and risk boundary.

## Baseline blockers

Known main-branch baseline checker blockers, if any, are not addressed here. This PR does not touch runtime, production_compat, deploy, nginx, systemd, migrations, or external-adapter paths.

## PR lifecycle

PR number, final PR state, merge commit, main containment, or exact blocker will be recorded in the PR body and end-of-run report after GitHub lifecycle tracking completes.
