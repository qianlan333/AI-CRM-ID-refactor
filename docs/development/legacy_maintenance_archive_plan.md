# Legacy Maintenance Archive Plan

AI-CRM production startup is Next-only. `app.py` starts `aicrm_next.main:app`, deploy runs Alembic migrations, and legacy startup commands are removed-command hard errors. The remaining `wecom_ability_service` package is frozen as non-startup maintenance/reference code until it is migrated or archived in separate PRs.

## Freeze Policy

- `aicrm_next/**`, `app.py`, `.github/**`, and `deploy/**` must not import or directly reference `wecom_ability_service`.
- `scripts/**/*.py` may import `wecom_ability_service` only when explicitly listed in `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST` in `scripts/check_no_new_legacy.py`.
- Tests, docs, tools, experiments, and `wecom_ability_service/**` historical references are tracked but do not block this freeze checker.
- Existing maintenance scripts are migration targets, not precedent for new legacy dependencies.
- The active external push worker is intentionally unchanged in this freeze step and is the first Phase B migration target.

## Allowlisted Maintenance Scripts

| script | usage | state | migration phase | risk |
|---|---|---|---|---|
| `scripts/audit_operation_task_runtime_contract.py` | operation-task runtime audit | on-demand | Phase B | medium |
| `scripts/backfill_questionnaire_submission_identity.py` | questionnaire identity backfill | on-demand | Phase B | high |
| `scripts/export_flask_routes.py` | legacy route inventory export | historical | Phase D | low |
| `scripts/repair_automation_member_projection.py` | automation projection repair | on-demand | Phase B | high |
| `scripts/repair_invalid_operation_tasks.py` | operation-task repair | on-demand | Phase B | high |
| `scripts/replay_operation_task_audience_entered.py` | operation-task replay | on-demand | Phase B | high |
| `scripts/replay_questionnaire_sidebar_profile.py` | questionnaire sidebar replay | on-demand | Phase B | high |
| `scripts/run_automation_agent_reply_backfill.py` | automation reply backfill | on-demand | Phase B | medium |
| `scripts/run_automation_member_backfill.py` | automation member backfill | on-demand | Phase B | high |
| `scripts/run_automation_ops_scheduler.py` | automation ops scheduler | on-demand | Phase B | high |
| `scripts/run_broadcast_queue_worker.py` | broadcast queue worker | on-demand | Phase B | high |
| `scripts/run_build.py` | legacy bootstrap/build helper | historical | Phase C/D | medium |
| `scripts/run_campaign_scheduler.py` | campaign scheduler | on-demand | Phase B | high |
| `scripts/run_cloud_orchestrator_scan.py` | cloud orchestrator scan | on-demand | Phase B | medium |
| `scripts/run_external_contact_sync.py` | external contact sync | on-demand | Phase B | high |
| `scripts/run_external_push_worker.py` | external push outbox worker | active | Phase B | high |
| `scripts/run_hxc_dashboard_refresh.py` | HXC dashboard refresh | on-demand | Phase B | medium |
| `scripts/run_marketing_automation_backfill.py` | marketing automation backfill | on-demand | Phase B | high |
| `scripts/run_owner_lead_pool_backfill.py` | owner lead-pool backfill | on-demand | Phase B | high |
| `scripts/run_pool_signup_tag_backfill.py` | pool signup tag backfill | on-demand | Phase B | high |
| `scripts/seed_automation_conversion_demo.py` | historical demo seed | historical | Phase C/D | low |

## Archive Phases

### Phase B: External push worker Next-native migration

Move `scripts/run_external_push_worker.py` to a Next-native repository/service boundary. Preserve timer behavior and keep real external calls governed by the existing outbox safety contract.

Exit criteria:

- Worker imports no `wecom_ability_service`.
- Systemd service command remains stable or is updated in a deploy-specific PR.
- External push tests prove no new real external call path is enabled.

### Phase C: Maintenance scripts migration inventory

Classify each allowlisted script as active, on-demand repair, or historical. Migrate active and high-risk repair scripts to `aicrm_next` one group at a time.

Exit criteria:

- Each migrated script is removed from `LEGACY_MAINTENANCE_SCRIPT_ALLOWLIST`.
- Production repair docs point to the Next-native replacement.

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

Start with Phase B: external push worker Next-native migration. It is the only currently deployed production worker that still enters `wecom_ability_service.create_app`, so it should move before broad script cleanup or HTTP/runtime archive work.
