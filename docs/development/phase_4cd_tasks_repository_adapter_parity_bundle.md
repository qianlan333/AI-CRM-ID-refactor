# Phase 4CD Tasks Repository Adapter Parity Bundle

## Bundle Type

Repository adapter parity bundle.

## Included Stages

- Repository adapter plan for `/api/admin/automation-conversion/tasks*`.
- SQLAlchemy metadata adapter behind `AICRM_TASKS_REPO_BACKEND`.
- Route-specific test/staging database flags: `AICRM_TASKS_TEST_DATABASE_URL` and `AICRM_TASKS_STAGING_DATABASE_URL`.
- Test DB parity harness with production-looking URL refusal.
- Idempotency, audit, and rollback scaffolding for task metadata create.
- Checker, tests, and phase state update.

## Excluded Stages

- Production route owner switch.
- Production repository enablement.
- Production write.
- `DATABASE_URL` fallback.
- Legacy fallback removal or narrowing.
- Run-due, task execution, workflow execution, timers, or outbound sends.
- Live external calls, WeCom calls, OpenClaw/MCP calls, or LLM calls.
- Destructive migrations, canary approval, or `delete_ready=true`.

## Route Family

`/api/admin/automation-conversion/tasks*`

## Runtime Behavior

The bundle adds a task metadata SQLAlchemy adapter for list/create parity in explicit test or staging DB contexts only. The default automation repository remains fixture/local. Create operations keep task execution disabled, produce an idempotent response snapshot, write an audit event, and include a rollback payload that only records later approved archive intent.

## Production Behavior

Production owner is unchanged. No production DB fallback is available, and the adapter cannot be selected without explicit route-specific DB configuration. The bundle does not authorize production writes or live task execution.

## Fallback Behavior

Legacy fallback remains available and unchanged. No fallback deletion, narrowing, or route-owner switch is included.

## Verification

- `python3 tools/check_phase4cd_tasks_repository_adapter_parity_bundle.py --output-md /tmp/phase4cd_tasks_repository_adapter_parity_bundle.md --output-json /tmp/phase4cd_tasks_repository_adapter_parity_bundle.json`
- `python3 tools/run_phase4cd_tasks_adapter_parity.py --output-md /tmp/phase4cd_tasks_adapter_parity.md --output-json /tmp/phase4cd_tasks_adapter_parity.json`
- `python3 -m pytest tests/test_phase4cd_tasks_repository_adapter_parity_bundle.py -q`
- Required autonomous loop, automerge, runtime contract, legacy facade freeze, backlog, and diff checks.

## Risk / Rollback

Risk is limited to disabled-by-default test/staging adapter code and repository factory wiring. Rollback is a normal revert of this bundle; because the fixture/local backend remains the default, reverting does not require production data recovery.

## Next Bundle Recommendation

`phase_4ce_agents_repository_adapter_parity_bundle` should apply the same repository-adapter parity pattern to `/api/admin/automation-conversion/agents*` without agent-run execution or LLM/external calls.
