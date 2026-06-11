# Legacy Package Removal

## Status

Legacy package removal is complete. The legacy Flask HTTP/runtime surface was retired first; the remaining executable legacy package body was then removed:

- `wecom_ability_service/domains/**`
- `wecom_ability_service/db/**`
- `wecom_ability_service/infra/**`
- `wecom_ability_service/schema_postgres.sql`
- orphaned root-level legacy support modules under `wecom_ability_service`

Production runtime, scripts, deploy units, tools, and tests no longer runtime import the legacy package. Current runtime and replacement behavior live under `aicrm_next/**`.

## Final Package Deletion

The final archived marker and frozen note have been deleted:

- `wecom_ability_service/__init__.py`
- `wecom_ability_service/LEGACY_FROZEN.md`

There is no remaining `wecom_ability_service/` package directory. Old fallback commands are deleted historical references only; they are not available runtime paths.

## Rule

Do not restore legacy package imports, schema setup, or fallback commands. If an old domain, DB, infra, or helper capability is needed again, rebuild it under a Next-native owner in `aicrm_next/**` and cover it with Next-native tests.
