# D8.5 Maintenance Command Replacement Matrix

| legacy_command | legacy_location | next_replacement_command | replacement_status | can_run_in_ci | can_run_in_staging | can_run_in_production | requires_backup | requires_human_signoff | delete_gate | risk | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `python3 app.py init-db-legacy` | `app.py` | Alembic / Next migration runner | planned | false | true | false | true | true | production migration evidence, rollback evidence, runbook cleanup | schema drift / accidental DDL | retained as emergency fallback |
| `python3 app.py init-db` | `app.py` | `python3 app.py init-db-legacy`, then Alembic / Next migration runner | planned | false | true | false | true | true | deprecated alias no longer referenced | operator confusion | retained compatibility alias |
| `python3 legacy_flask_app.py init-db` | `legacy_flask_app.py` | Alembic / Next migration runner | planned | false | true | false | true | true | legacy fallback no longer needed for rollback | schema drift / accidental DDL | retained |
| `flask init-db` | `wecom_ability_service/db/__init__.py` | Alembic / Next migration runner | planned | false | true | false | true | true | Flask CLI not referenced by deploy/runbook/rollback | schema drift | retained through legacy app factory |
| `POST /api/init-db` | `wecom_ability_service/http/ops.py` | operator-only CLI or Next maintenance command | needs_manual_review | false | false | false | true | true | no production logs, no runbook references, replacement accepted | accidental DDL through HTTP | later phase may block or remove route after signoff |
| `wecom_ability_service.db.init_db()` | `wecom_ability_service/db/__init__.py` | Alembic migration service / Next migration facade | planned | true | true | false | true | true | import graph and scripts migrated to replacement | schema drift | retained helper |
| `_init_postgres(db)` | `wecom_ability_service/db/migrations/postgres_migrations.py` | Alembic revision chain | planned | true | true | false | true | true | schema parity and migration coverage accepted | partial migration drift | retained |
| `wecom_ability_service/schema_postgres.sql` | `wecom_ability_service/schema_postgres.sql` | Alembic baseline and generated schema reference | planned | true | true | false | true | true | baseline no longer required by fallback | schema drift | retained as fallback reference |
| Alembic migration runner | `migrations/env.py`, `migrations/versions/*` | primary Next migration command | available | true | true | false | true | true | production runbook, backup, dry-run, signoff | migration failure | replacement candidate, not auto-production |
| PostgreSQL integration test runner | `tests/integration/` | continue as isolated PG validation | available | true | true | false | false | false | not a deletion target | accidental production DB target | must use isolated DB |
| `python3 scripts/run_build.py` | `scripts/run_build.py` | Next build smoke plus explicit legacy fallback smoke | planned | true | true | false | false | false | build smoke no longer needs legacy init | accidental DB init if env mispointed | keep CI/build only |
| `python3 scripts/seed_automation_conversion_demo.py --init-db` | `scripts/seed_automation_conversion_demo.py` | Next fixture/demo seed command | needs_manual_review | false | true | false | true | true | replacement has dry-run, non-production guard, audit | data pollution | local/staging only |
| `python3 scripts/run_marketing_automation_backfill.py` | `scripts/run_marketing_automation_backfill.py` | reviewed Next backfill command | needs_manual_review | false | true | false | true | true | dry-run, audit trail, backup, human signoff | bulk data mutation | production use blocked by default |
| `python3 app.py delete-questionnaire-submissions-legacy <slug>` | `app.py` | reviewed Next operator cleanup command | needs_manual_review | false | false | false | true | true | replacement has dry-run, backup, audit, signoff | data loss | destructive |
| `python3 app.py delete-questionnaire-submissions <slug>` | `app.py` | explicit legacy cleanup command, then Next operator cleanup | needs_manual_review | false | false | false | true | true | deprecated alias no longer referenced | data loss / operator confusion | destructive alias |
| `python3 legacy_flask_app.py delete-questionnaire-submissions <slug>` | `legacy_flask_app.py` | reviewed Next operator cleanup command | needs_manual_review | false | false | false | true | true | replacement has dry-run, backup, audit, signoff | data loss | destructive |
| `python3 app.py run-legacy` | `app.py` | no replacement until rollback retired | blocked | false | true | false | false | true | production observation window and rollback signoff | rollback loss if removed early | fallback runtime command |
| `python3 legacy_flask_app.py run` | `legacy_flask_app.py` | no replacement until rollback retired | blocked | false | true | false | false | true | production observation window and rollback signoff | rollback loss if removed early | fallback runtime command |

## Matrix Rules

- `can_run_in_production=false` means no automatic production execution is approved by D8.5.
- Destructive commands require backup and human signoff.
- Replacement status values are limited to `available`, `planned`, `needs_manual_review`, and `blocked`.
- This matrix does not approve command deletion.
