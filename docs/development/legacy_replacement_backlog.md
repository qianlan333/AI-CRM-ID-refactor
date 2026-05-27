# Legacy Replacement Backlog

Status: Phase 2 planning only. This document does not change runtime behavior, remove fallback, narrow production_compat, enable timers, or open real external calls.

## Replacement Principles

1. read-only first
2. internal write second
3. external side-effect third
4. timer / automation execution last

## Business Continuity

- Do not interrupt current production daily use.
- Do not delete current fallback.
- Do not remove current production_compat routes.
- Do not enable real external calls.
- Do not let fixture/local_contract data enter production success paths.
- Every daily-business-critical replacement must keep fallback until parity, checker, smoke, and rollback conditions are satisfied.

## Summary By Capability Owner

- `aicrm_next.ai_assist`: 1 routes; P3=1
- `aicrm_next.automation_engine`: 24 routes; P1=17, P2=4, P3=3
- `aicrm_next.commerce`: 15 routes; P2=15
- `aicrm_next.customer_read_model`: 9 routes; P0=7, P1=2
- `aicrm_next.customer_tags`: 2 routes; P2=2
- `aicrm_next.frontend_compat`: 4 routes; P0=2, P1=2
- `aicrm_next.identity_contact`: 1 routes; P0=1
- `aicrm_next.integration_gateway`: 4 routes; P1=1, P2=3
- `aicrm_next.media_library`: 7 routes; P2=7
- `aicrm_next.platform_foundation`: 3 routes; P0=2, P3=1
- `aicrm_next.questionnaire`: 10 routes; P0=1, P1=5, P2=4

## Summary By Replacement Phase

- `keep_guarded_until_adapter_ready`: 1 routes; blocked_or_guarded=1
- `phase_3_readonly`: 13 routes; readonly=9, shell_or_navigation=4
- `phase_4_internal_write`: 27 routes; internal_write=21, readonly=3, shell_or_navigation=3
- `phase_5_external_adapter`: 34 routes; adapter_contract=10, external_side_effect=24
- `phase_6_timer_automation`: 5 routes; timer_or_automation_execution=5

## Top 10 Suggested First Replacements

### 1. `/admin`

- owner: `aicrm_next.frontend_compat`
- priority: `P0` / `phase_3_readonly` / `shell_or_navigation`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_admin_ui_data_parity.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 2. `/admin/customers`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `shell_or_navigation`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 3. `/admin/questionnaires`

- owner: `aicrm_next.questionnaire`
- priority: `P0` / `phase_3_readonly` / `shell_or_navigation`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 4. `/api/admin/customers/profile`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 5. `/api/admin/customers/profile/tags`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 6. `/api/customers`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 7. `/api/customers/{external_userid}`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 8. `/api/customers/{external_userid}/timeline`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 9. `/api/sidebar/contact-binding-status`

- owner: `aicrm_next.identity_contact`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 10. `/api/sidebar/customer-context`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- fallback until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

## Full Backlog Index

- `LRB-001` `/health`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.platform_foundation`
- `LRB-002` `/api/system/health`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.platform_foundation`
- `LRB-003` `/admin`: `P0` / `phase_3_readonly` / `shell_or_navigation` / owner `aicrm_next.frontend_compat`
- `LRB-004` `/admin/customers`: `P0` / `phase_3_readonly` / `shell_or_navigation` / owner `aicrm_next.customer_read_model`
- `LRB-005` `/admin/questionnaires`: `P0` / `phase_3_readonly` / `shell_or_navigation` / owner `aicrm_next.questionnaire`
- `LRB-006` `/admin/questionnaires/new`: `P1` / `phase_4_internal_write` / `shell_or_navigation` / owner `aicrm_next.questionnaire`
- `LRB-007` `/admin/questionnaires/{questionnaire_id}`: `P1` / `phase_4_internal_write` / `shell_or_navigation` / owner `aicrm_next.questionnaire`
- `LRB-008` `/admin/automation-conversion`: `P1` / `phase_4_internal_write` / `shell_or_navigation` / owner `aicrm_next.automation_engine`
- `LRB-009` `/admin/automation-conversion/{path:path}`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-010` `/admin/jobs`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.platform_foundation`
- `LRB-011` `/admin/wechat-pay/products`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-012` `/admin/wechat-pay/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-013` `/admin/wechat-pay/transactions`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-014` `/admin/image-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-015` `/admin/miniprogram-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-016` `/admin/attachment-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-017` `/api/customers`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-018` `/api/customers/{external_userid}`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-019` `/api/customers/{external_userid}/timeline`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-020` `/api/messages/{external_userid}/recent`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-021` `/api/messages*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.integration_gateway`
- `LRB-022` `/api/admin/questionnaires*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.questionnaire`
- `LRB-023` `/api/h5/questionnaires*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-024` `/api/h5/questionnaires/{slug}/submit`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.questionnaire`
- `LRB-025` `/api/h5/questionnaires/{slug}/client-diagnostics`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.questionnaire`
- `LRB-026` `/s/{slug}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-027` `/api/h5/wechat/oauth*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-028` `/api/admin/wecom/tags*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-029` `/api/admin/wecom/tag-groups*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-030` `/auth/wecom*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-031` `/api/admin/automation-conversion/reply-monitor*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-032` `/api/admin/automation-conversion/jobs/run-due*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-033` `/api/admin/cloud-orchestrator/campaigns/run-due*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.ai_assist`
- `LRB-034` `/api/admin/automation-conversion/programs*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-035` `/api/admin/automation-conversion/settings*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-036` `/api/admin/automation-conversion/default-channel-settings*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-037` `/api/admin/automation-conversion/profile-segment-templates*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-038` `/api/admin/automation-conversion/agents*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-039` `/api/admin/automation-conversion/agent-outputs*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-040` `/api/admin/automation-conversion/agent-runs*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-041` `/api/admin/automation-conversion/agent-replay`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-042` `/api/admin/automation-conversion/agent-orchestration*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-043` `/api/admin/automation-conversion/action-templates*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-044` `/api/admin/automation-conversion/task-groups*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-045` `/api/admin/automation-conversion/tasks*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-046` `/api/admin/automation-conversion/workflows*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-047` `/api/admin/automation-conversion/workflow-nodes*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-048` `/api/admin/automation-conversion/dashboard`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-049` `/api/admin/automation-conversion/executions*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-050` `/api/admin/automation-conversion/execution-items*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-051` `/api/admin/automation-conversion*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-052` `/api/customer-automation*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-053` `/api/customers/automation*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-054` `/api/admin/wechat-pay/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-055` `/api/admin/wechat-pay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-056` `/api/admin/alipay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-057` `/api/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-058` `/p/{page_slug}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-059` `/pay/{product_code}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-060` `/api/orders*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-061` `/api/checkout*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-062` `/api/wechat-pay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-063` `/api/alipay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-064` `/api/h5/wechat-pay*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-065` `/api/h5/alipay*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-066` `/api/admin/image-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-067` `/api/admin/image-library/upload`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-068` `/api/admin/attachment-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-069` `/api/admin/miniprogram-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-070` `/sidebar/bind-mobile`: `P0` / `phase_3_readonly` / `shell_or_navigation` / owner `aicrm_next.frontend_compat`
- `LRB-071` `/api/sidebar/contact-binding-status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.identity_contact`
- `LRB-072` `/api/sidebar/customer-context`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-073` `/api/admin/customers/profile`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-074` `/api/admin/customers/profile/tags`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-075` `/sidebar*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.frontend_compat`
- `LRB-076` `/api/sidebar*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.frontend_compat`
- `LRB-077` `/api/admin/customers/profile*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.customer_read_model`
- `LRB-078` `/wecom/external-contact/callback`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.integration_gateway`
- `LRB-079` `/api/wecom/events`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.integration_gateway`
- `LRB-080` `/mcp`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.integration_gateway`
