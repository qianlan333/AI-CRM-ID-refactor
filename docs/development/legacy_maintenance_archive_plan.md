# Legacy Maintenance Archive Plan

AI-CRM production startup is Next-only. `app.py` starts `aicrm_next.main:app`, deploy runs Alembic migrations, and legacy startup commands are removed-command hard errors. The remaining `wecom_ability_service` package is frozen as non-startup maintenance/reference code until it is migrated or archived in separate PRs.

## Freeze Policy

- `aicrm_next/**`, `app.py`, `.github/**`, and `deploy/**` must not import or directly reference `wecom_ability_service`.
- `scripts/**/*.py` may import `wecom_ability_service` only when explicitly listed in `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST` in `scripts/check_no_new_legacy.py`.
- Tests, docs, tools, experiments, and `wecom_ability_service/**` historical references are tracked but do not block this freeze checker.
- Existing maintenance scripts are migration targets, not precedent for new legacy dependencies.
- The active external push worker has been migrated to `aicrm_next.external_push`; `scripts/run_external_push_worker.py` must remain outside the legacy maintenance allowlist.

## Allowlisted Maintenance Scripts

Current allowlist count: 4. Only active deploy-backed legacy scripts remain in `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST`.

| script | usage | state | migration phase | risk |
|---|---|---|---|---|
| `scripts/run_automation_member_backfill.py` | automation member backfill | active deploy service | Phase C | high |
| `scripts/run_automation_ops_scheduler.py` | automation ops scheduler | active deploy service | Phase C | high |
| `scripts/run_broadcast_queue_worker.py` | broadcast queue worker | active deploy service | Phase C | high |
| `scripts/run_external_contact_sync.py` | external contact sync/full sync | active deploy service | Phase C | high |

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

Future repair, backfill, or scheduler capability must be rebuilt through Next-native repository/service boundaries. Do not reintroduce `wecom_ability_service` imports into new scripts. The four remaining active deploy scripts are the next migration or decommission targets.

## Archive Phases

### Phase B: External push worker Next-native migration

Status: complete for the active worker. `scripts/run_external_push_worker.py` now calls `aicrm_next.external_push` directly, while the systemd command remains unchanged.

Exit criteria:

- Worker imports no `wecom_ability_service`.
- Systemd service command remains stable.
- External push tests prove no new real external call path is enabled.

### Phase C: Maintenance scripts migration inventory

Status: non-deploy maintenance script retirement complete; the maintenance script allowlist now contains only active deploy-backed legacy services.

Migrate or decommission active deploy services one group at a time.

Exit criteria:

- Each active deploy-backed script is removed from `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST` only after its service migrates or decommissions.
- Production repair docs point to the Next-native replacement where the capability remains necessary.

### Phase D: Tests off legacy fixtures

Move tests away from legacy Flask app fixtures, legacy HTTP monkeypatch seams, and direct legacy domain imports where the behavior has a Next owner.

Exit criteria:

- `tests/conftest.py` no longer needs default legacy app setup for current-route tests.
- Remaining legacy tests are explicitly historical/archive tests.

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

Active deploy legacy services migration/decommission plan.
