# Legacy Package Removal

## Status

The legacy Flask HTTP/runtime surface was retired in the previous archive step. This step removes the remaining executable legacy package body:

- `wecom_ability_service/domains/**`
- `wecom_ability_service/db/**`
- `wecom_ability_service/infra/**`
- `wecom_ability_service/schema_postgres.sql`
- orphaned root-level legacy support modules under `wecom_ability_service`

Production runtime, scripts, deploy units, and tests no longer runtime import the legacy package. Current runtime and replacement behavior live under `aicrm_next/**`.

## Temporary Remainder

`wecom_ability_service/__init__.py` remains as an archived marker until final dependency/reference cleanup. `wecom_ability_service/LEGACY_FROZEN.md` remains as a non-runtime historical note.

## Rule

Do not restore legacy package imports or schema setup. If an old domain, DB, infra, or helper capability is needed again, rebuild it under a Next-native owner in `aicrm_next/**` and cover it with Next-native tests.
