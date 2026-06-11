# Legacy Package Test Archive

## Background

Production runtime, startup, deploy services, external push worker, and active background jobs are now Next-native. The maintenance script allowlist is empty, and the primary business test families have been migrated to Next-native fixtures and services.

The remaining executable tests that imported `wecom_ability_service` directly were legacy package/domain unit tests. They no longer protect the current production runtime and should not continue to block package archive work. The temporary legacy test fixture bridge has also been removed, so pytest fixtures and schema setup now use Next-native fixtures plus the test-only Next baseline bootstrap and Alembic migrations instead of legacy Flask app setup or `schema_postgres.sql`.

## Retired Executable Legacy Tests

| file | former coverage | reason retired | Next replacement / current protection | risk |
| --- | --- | --- | --- | --- |
| `tests/contract/test_crm_contract.py` | legacy CRM contract, MCP adapter, materialized batches | executable legacy package contract | Next route registry, MCP, background job, and customer read-model tests | medium |
| `tests/integration/test_pg_compat_smoke.py` | legacy PG compatibility smoke, campaigns, broadcast, cloud orchestrator | legacy integration smoke against retired package internals | Next background jobs, campaign, broadcast, route registry, and production contract tests | medium |
| `tests/test_admin_audit_write_paths.py` | legacy admin audit domain writes | legacy domain unit coverage | Next admin/write-path no-real-side-effect guards | low |
| `tests/test_admin_config.py` | legacy admin config app/service behavior | legacy Flask/config package behavior | Next admin config and post-closeout production contracts | medium |
| `tests/test_admin_console_phase4.py` | legacy admin console phase behavior | legacy Flask admin console fixture | Next admin shell/page native tests | low |
| `tests/test_admin_console_shell.py` | legacy admin shell DB-backed rendering | legacy Flask admin console fixture | Next admin shell native tests | low |
| `tests/test_admin_governance_phase6.py` | legacy governance/admin DB behavior | legacy package governance test | Next post-closeout production and admin page tests | low |
| `tests/test_admin_hxc_dashboard.py` | legacy HXC dashboard service/pages | legacy user-ops/HXC domain fixture | Next HXC dashboard API/page/native tests | medium |
| `tests/test_admin_jobs_console.py` | legacy admin jobs console and job actions | legacy Flask/admin jobs internals | Next active background jobs and production contract tests | medium |
| `tests/test_admin_navigation_groups.py` | legacy admin dashboard navigation group helpers | legacy admin dashboard/http helpers | Next admin shell navigation tests | low |
| `tests/test_admin_rbac_navigation.py` | legacy admin auth/RBAC navigation | legacy admin auth/http helpers | Next admin auth and route-owner tests | low |
| `tests/test_admin_slim_phase1.py` | legacy admin slim/auth flows | legacy Flask admin/auth fixture | Next admin auth/login route tests | medium |
| `tests/test_attachment_library.py` | legacy attachment library and media limits | legacy media package internals | Next media library and attachment route contracts | medium |
| `tests/test_background_job_observability.py` | legacy observability filter and route dispatcher | legacy routes/observability internals | Next active deploy/background job tests | low |
| `tests/test_common_operation_members.py` | legacy common operation members route/helper | legacy HTTP/domain helper | Next operation/member picker and user-ops native tests | low |
| `tests/test_config_schema.py` | legacy config schema and settings helpers | legacy infra/config internals | Next config/admin closeout checks | low |
| `tests/test_conversion_service.py` | legacy conversion/service database behavior | legacy service/domain unit test | Next automation, questionnaire, campaign, and background job tests | medium |
| `tests/test_error_codes.py` | legacy error code and WeCom client error helpers | legacy infra/client helper test | Next integration gateway structured-error tests | low |
| `tests/test_hxc_dashboard_snapshot.py` | legacy HXC snapshot service/phone helpers | legacy user-ops domain test | Next HXC dashboard snapshot/API tests | medium |
| `tests/test_outbound_webhook_repo.py` | legacy outbound webhook row serialization | legacy repo helper test | Next external push/outbox tests | low |
| `tests/test_postgres_schema_retry.py` | legacy schema runner retry helpers | legacy DB migration helper test | Alembic/deploy workflow contract tests | low |
| `tests/integration/conftest.py` | shared fixture for retired legacy PG integration tests | legacy integration fixture bridge outside explicit root bridge | Next-native integration fixtures and route/service tests | low |
| `tests/test_observability.py` | legacy Flask request id, favicon, temporary webhook receiver, logger context | legacy Flask route/observability behavior | Next post-closeout production and no-real-side-effect route contracts | low |
| `tests/test_service_layer_layout.py` | legacy domain package layout | legacy package architecture guard | Next source consolidation and legacy exit guardrails | low |
| `tests/test_sprint_infra.py` | legacy infra cache/http/outbox/task queue/settings | legacy infra package unit tests | Next no-real-external-call and background job tests | medium |
| `tests/test_sql_sandbox.py` | legacy segment SQL sandbox helper | legacy domain helper test | Next customer/read-model query tests | low |
| `tests/test_system_health.py` | legacy system health routes and callbacks repo | legacy Flask/system health test | Next post-closeout production and route registry tests | medium |
| `tests/test_value_segment_service.py` | legacy value segment service/config | legacy service/db unit test | Next customer read-model and segmentation contracts | medium |
| `tests/test_wechat_oauth.py` | legacy WeChat OAuth infra helper | legacy OAuth helper test | Next OAuth adapter/security tests | low |

## Removed Temporary Bridge

The temporary executable bridge has been removed:

- `tests/conftest.py`
- `tests/test_test_fixture_boundaries.py`

`tests/conftest.py` now exposes only Next-native fixtures (`next_app`, `next_client`, `next_pg_schema`, `app`, and `client`) and runs test database setup through a test-only Next baseline bootstrap followed by Alembic. `tests/test_test_fixture_boundaries.py` now protects the absence of legacy fixtures, legacy runtime imports, and legacy schema setup.

## Archived Legacy HTTP Runtime Package

The legacy Flask HTTP/runtime package surface has been archived after tests stopped importing it:

- `wecom_ability_service/__init__.py` is now an archived package marker and no longer exposes `create_app`.
- `wecom_ability_service/http/**`, the legacy route registry, and blueprint runtime files have been removed.
- Package-local legacy templates/static and request-observability runtime files have been removed.
- Current route/runtime ownership is `aicrm_next`.
- `wecom_ability_service/domains/**`, `wecom_ability_service/db/**`, `wecom_ability_service/infra/**`, and `wecom_ability_service/schema_postgres.sql` have since been retired.

## Removed Legacy Domains DB Infra Package

The executable legacy package body has been removed after the tests layer and HTTP runtime were disconnected:

- `wecom_ability_service/domains/**`
- `wecom_ability_service/db/**`
- `wecom_ability_service/infra/**`
- `wecom_ability_service/schema_postgres.sql`
- orphaned root-level package helpers such as legacy service, callback, archive, and WeCom client modules

Only the archived package marker remains temporarily. New code and tests must not import `wecom_ability_service.domains`, `wecom_ability_service.db`, or `wecom_ability_service.infra`; old capabilities must be rebuilt under `aicrm_next/**`.

New executable tests must not reintroduce `wecom_ability_service.http`, `from wecom_ability_service import create_app`, legacy route owner headers, or Flask app factory coverage.

## Rule

New executable tests must not runtime import `wecom_ability_service` or use legacy Flask fixture names. If an old capability is needed again, rebuild the behavior under `aicrm_next/**` and test it with Next-native fixtures, repositories, or fakes. Historical references may live in docs or tools, but Python tests under `tests/` must not reintroduce legacy package/domain unit coverage.
