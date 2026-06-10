# Legacy Maintenance Archive Plan

AI-CRM production startup is Next-only. `app.py` starts `aicrm_next.main:app`, deploy runs Alembic migrations, and legacy startup commands are removed-command hard errors. The remaining `wecom_ability_service` package is frozen as non-startup maintenance/reference code until it is migrated or archived in separate PRs.

## Freeze Policy

- `aicrm_next/**`, `app.py`, `.github/**`, and `deploy/**` must not import or directly reference `wecom_ability_service`.
- `scripts/**/*.py` must not import `wecom_ability_service`; `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST` must remain empty.
- Tests must not runtime import `wecom_ability_service`; docs, tools, experiments, and `wecom_ability_service/**` historical references are tracked but do not block this freeze checker.
- Existing maintenance scripts are migration targets, not precedent for new legacy dependencies.
- The active external push worker has been migrated to `aicrm_next.external_push`; `scripts/run_external_push_worker.py` must remain outside the legacy maintenance allowlist.

## Allowlisted Maintenance Scripts

Current allowlist count: 0. No active deploy-backed script may import `wecom_ability_service`.

| script | usage | state | migration phase | risk |
|---|---|---|---|---|
| none | none | cleared | complete | none |

## Migrated Active Deploy Services

These deploy-backed capabilities now keep their existing script paths and systemd service/timer commands while running through `aicrm_next.background_jobs` implementations:

- Automation member backfill: `scripts/run_automation_member_backfill.py`
- Automation ops scheduler: `scripts/run_automation_ops_scheduler.py`
- Broadcast queue worker: `scripts/run_broadcast_queue_worker.py`
- External contact sync/full sync: `scripts/run_external_contact_sync.py`

The deploy service and timer unit files remain in place with the same `ExecStart` commands. The script internals are Next-native and must not import `wecom_ability_service`. Where a legacy-only sub-capability has no safe Next owner yet, the job returns structured `skipped` output instead of using a legacy fallback.

## Retired Legacy Flask HTTP Tests

The legacy Flask HTTP route registry is no longer a production protection boundary. These tests have been retired:

- `tests/test_http_registration_contract.py`
- `tests/test_route_owner_headers.py`
- legacy Flask-only assertions from `tests/test_legacy_channel_entry_retired.py`
- legacy Flask-only assertions from `tests/test_post_legacy_cloud_orchestrator_legacy_handlers_removed.py`
- `tests/test_user_ops_admin_retirement.py`

Current route ownership is protected by Next-native route registry and production route resolution tests, including `tests/test_channel_entry_next_retirement_contract.py`, `tests/test_production_route_resolution.py`, and `tests/test_route_registry_final_freeze.py`. Future legacy package archive work must not be blocked by Flask blueprint, HTTP route registry, or legacy route-owner header tests.

## Retired Historical Helpers

- `scripts/export_flask_routes.py` - retired after frontend_compat/runtime route closeout; route inventory now owned by Next route registry tests.
- `scripts/run_build.py` - retired after app.py became Next-only and deploy/build smoke moved to pytest + Alembic checks.
- `scripts/seed_automation_conversion_demo.py` - retired as legacy demo seed; future demo fixtures must be Next-native and explicit.

## Bulk Retired Non-deploy Maintenance Scripts

These non-deploy direct-connect legacy maintenance scripts are retired:

- `scripts/audit_operation_task_runtime_contract.py`
- `scripts/backfill_questionnaire_submission_identity.py`
- `scripts/repair_automation_member_projection.py`
- `scripts/repair_invalid_operation_tasks.py`
- `scripts/replay_operation_task_audience_entered.py`
- `scripts/replay_questionnaire_sidebar_profile.py`
- `scripts/run_automation_agent_reply_backfill.py`
- `scripts/run_campaign_scheduler.py`
- `scripts/run_cloud_orchestrator_scan.py`
- `scripts/run_hxc_dashboard_refresh.py`
- `scripts/run_marketing_automation_backfill.py`
- `scripts/run_owner_lead_pool_backfill.py`
- `scripts/run_pool_signup_tag_backfill.py`

Future repair, backfill, or scheduler capability must be rebuilt through Next-native repository/service boundaries. Do not reintroduce `wecom_ability_service` imports into new scripts.

## Removed Temporary Legacy Test Fixture Bridge

The temporary legacy Flask test fixture bridge has been removed from `tests/conftest.py`. Default test fixtures now point to the Next application and FastAPI test client only:

- `next_app`
- `next_client`
- `app`
- `client`

Test database schema setup now runs Alembic migrations from the Next schema source instead of reading `wecom_ability_service/schema_postgres.sql` or importing the legacy schema runner. Tests under `tests/**` must not runtime import `wecom_ability_service` or use legacy fixture names such as `legacy_app`, `legacy_client`, or `build_legacy_pg_test_app`.

## Archive Phases

### Phase B: External push worker Next-native migration

Status: complete for the active worker. `scripts/run_external_push_worker.py` now calls `aicrm_next.external_push` directly, while the systemd command remains unchanged.

Exit criteria:

- Worker imports no `wecom_ability_service`.
- Systemd service command remains stable.
- External push tests prove no new real external call path is enabled.

### Phase C: Maintenance scripts migration inventory

Status: complete. Non-deploy maintenance scripts are retired, and active deploy-backed services have Next-native script implementations.

Keep the script path/systemd contract stable while the internal implementation remains Next-native.

Exit criteria:

- `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST` is empty.
- Active deploy service targets exist and import no `wecom_ability_service`.
- Production repair docs point to the Next-native replacement where the capability remains necessary.

### Phase D: Tests off legacy fixtures

Status: complete. Tests have been moved away from legacy Flask app fixtures, legacy HTTP monkeypatch seams, direct legacy domain imports, and the temporary legacy fixture bridge.

Exit criteria:

- `tests/conftest.py` exposes only Next-native app/client fixtures.
- `tests/**` no longer runtime imports `wecom_ability_service`.
- Test schema setup uses Alembic/Next schema sources.

### Phase E: Legacy HTTP/runtime archive

Delete or archive obsolete `wecom_ability_service/http/**`, route registry shims, package-local templates/static, and legacy Flask runtime files after scripts/tests stop importing them.

Exit criteria:

- No production deploy, worker, startup, or active test imports the legacy HTTP/runtime surface.
- Strict route and startup closeout checkers remain green.

### Phase F: Domain package removal

Remove or archive the remaining `wecom_ability_service` domain/db/infra package only after all maintenance scripts and historical tests have a Next-native replacement or are explicitly retired.

Exit criteria:

- `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST` is empty.
- `tests/**` legacy imports are historical-only or removed.
- Production smoke and route registry checks pass after package removal.

## Recommended Next Step

Archive legacy HTTP/runtime package.
