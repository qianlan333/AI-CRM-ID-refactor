# D8.5 Legacy DB / Maintenance Command Retirement Plan

## Goal

D8.5 plans the retirement of legacy database initialization and maintenance commands. This round does not remove commands, does not execute production database migration, does not clean production data, does not modify production config, and does not change traffic routing.

The intended D8.5 state is:

| field | value |
| --- | --- |
| `legacy_maintenance_command_status` | `retirement_planning_ready` |
| `legacy_commands_deleted` | false |
| `production_db_migration_executed` | false |
| `production_config_modified` | false |
| deletion readiness | false |

## Command Categories

| category | description | examples | D8.5 action |
| --- | --- | --- | --- |
| `legacy_db_init` | legacy command or helper that initializes schema | `python3 app.py init-db-legacy`, `python3 legacy_flask_app.py init-db`, Flask `init-db` | inventory and retain |
| `legacy_schema_migration` | old bootstrap SQL or compatibility migration helper | `wecom_ability_service/schema_postgres.sql`, `_init_postgres(db)` | inventory and retain |
| `legacy_cleanup_command` | command that can delete or mutate data | questionnaire submission delete helper | inventory, require human signoff |
| `legacy_diagnostic_command` | build, smoke, integration, or local diagnostic helper | `scripts/run_build.py`, PG integration tests | inventory and keep non-production |
| `next_migration_command` | intended replacement migration path | Alembic migration runner | planned primary path, not auto-production |
| `rollback_command` | command kept for emergency fallback | `run-legacy`, legacy Flask app factory | retain until rollback no longer needs it |
| `needs_manual_review` | any command with production data or destructive risk | old cleanup, backfill, demo seed with writes | block automatic production use |

## Replacement Strategy

- AI-CRM Next should use Alembic or a Next-owned migration runner as the primary migration path.
- Legacy `init-db` remains an emergency fallback until production migration evidence and rollback evidence are complete.
- Destructive cleanup commands require manual signoff, backup evidence, a dry-run path, and an audit trail before production use.
- Production migration requires backup and restore evidence, a rollback plan, dry-run or staging evidence, and human signoff.
- Schema drift must be handled by a separate schema comparison report before any command is retired.
- Demo seed and backfill helpers must remain non-production by default unless a later reviewed operator command provides explicit safeguards.

## Delete Gates

Legacy maintenance command removal is blocked until all of the following are true:

- Production AI-CRM Next migration has run successfully with archived evidence.
- Legacy DB init is no longer referenced by deploy scripts, CI, runbooks, or rollback instructions.
- All rollback plans no longer require legacy DB init or legacy cleanup helpers.
- Backup and restore evidence exists for production database operations.
- Human signoff is recorded for migration, cleanup, and rollback readiness.
- No production incidents require legacy DB init or legacy maintenance fallback during the agreed observation window.
- Replacement commands have dry-run, audit, and operator approval behavior where relevant.

## Rollback

- D8.5 changes no runtime behavior.
- D8.5 does not run production migrations.
- Future removal of commands must be reversible with `git revert`.
- Production DB rollback is never automatic in this plan.
- Destructive rollback or cleanup requires manual approval, backup verification, and a written incident or maintenance ticket.

## Next Steps

After D8.5 acceptance, a later implementation stage may add guarded Next-owned migration and maintenance commands. Removal of legacy commands remains blocked until the delete gates above are met.
