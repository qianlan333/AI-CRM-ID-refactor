# Legacy Replacement Backlog

Status: Final cleanup frozen. Historical planning entries are archived; restoring production compatibility runtime requires a new explicit gated PR.

## Replacement Principles

1. read-only first
2. internal write second
3. external side-effect third
4. timer / automation execution last

## Business Continuity

- Do not interrupt current production daily use.
- Do not restore production compatibility fallback.
- Production compatibility routes have been removed; do not reintroduce them.
- Do not enable real external calls.
- Do not let fixture/local_contract data enter production success paths.
- Every daily-business-critical replacement must keep locked owner until parity, checker, smoke, and rollback conditions are satisfied.

## Summary By Capability Owner

- `aicrm_next.admin_jobs`: 2 routes; P3=2
- `aicrm_next.ai_assist`: 1 routes; P3=1
- `aicrm_next.automation_engine`: 30 routes; P0=2, P1=19, P2=5, P3=4
- `aicrm_next.commerce`: 15 routes; P2=15
- `aicrm_next.customer_read_model`: 13 routes; P0=8, P1=4, P2=1
- `aicrm_next.customer_tags`: 2 routes; P2=2
- `aicrm_next.frontend_compat`: 4 routes; P0=2, P1=1, P2=1
- `aicrm_next.identity_contact`: 1 routes; P0=1
- `aicrm_next.integration_gateway`: 4 routes; P1=1, P2=3
- `aicrm_next.media_library`: 7 routes; P2=7
- `aicrm_next.platform_foundation`: 2 routes; P0=2
- `aicrm_next.questionnaire`: 10 routes; P0=1, P1=5, P2=4

## Summary By Replacement Phase

- `keep_guarded_until_adapter_ready`: 1 routes; blocked_or_guarded=1
- `phase_3_readonly`: 16 routes; readonly=12, shell_or_navigation=4
- `phase_4_internal_write`: 30 routes; internal_write=23, readonly=4, shell_or_navigation=3
- `phase_5_external_adapter`: 37 routes; adapter_contract=11, external_side_effect=26
- `phase_6_timer_automation`: 7 routes; timer_or_automation_execution=7

## Top 10 Suggested First Replacements

### 1. `/admin`

- owner: `aicrm_next.frontend_compat`
- priority: `P0` / `phase_3_readonly` / `shell_or_navigation`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_admin_ui_data_parity.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 2. `/admin/customers`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `shell_or_navigation`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 3. `/admin/questionnaires`

- owner: `aicrm_next.questionnaire`
- priority: `P0` / `phase_3_readonly` / `shell_or_navigation`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 4. `/api/admin/customers/profile`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 5. `/api/admin/customers/profile/tags`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 6. `/api/customers`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 7. `/api/customers/{external_userid}`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 8. `/api/customers/{external_userid}/timeline`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_next_production_runtime_gaps.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 9. `/api/sidebar/contact-binding-status`

- owner: `aicrm_next.identity_contact`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; legacy fallback rollback check

### 10. `/api/sidebar/customer-context`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: During replacement, do not interrupt the current production path. Keep the locked Next owner until Next native parity, checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data false success, or accidental external side effects.
- locked owner until: Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete.
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
- `LRB-010` `/admin/jobs`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.admin_jobs`
- `LRB-011` `/admin/broadcast-jobs`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.admin_jobs`
- `LRB-012` `/admin/wechat-pay/products`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-013` `/admin/wechat-pay/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-014` `/admin/wechat-pay/transactions`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-015` `/admin/image-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-016` `/admin/miniprogram-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-017` `/admin/attachment-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-018` `/api/customers`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-019` `/api/customers/{external_userid}`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-020` `/api/customers/{external_userid}/timeline`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-021` `/api/messages/{external_userid}/recent`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-022` `/api/messages*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.message_archive` / deleted locked
- `LRB-023` `/api/admin/questionnaires*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.questionnaire`
- `LRB-024` `/api/h5/questionnaires*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-025` `/api/h5/questionnaires/{slug}/submit`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.questionnaire`
- `LRB-026` `/api/h5/questionnaires/{slug}/client-diagnostics`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.questionnaire`
- `LRB-027` `/s/{slug}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-028` `/api/h5/wechat/oauth*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-029` `/api/admin/wecom/tags*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-030` `/api/admin/wecom/tag-groups*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-031` `/auth/wecom*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-032` `/api/admin/automation-conversion/reply-monitor*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-033` `/api/admin/automation-conversion/jobs/run-due*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-034` `/api/admin/cloud-orchestrator/campaigns/run-due*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.ai_assist`
- `LRB-035` `/api/admin/automation-conversion/programs*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-036` `/api/admin/automation-conversion/profile-segment-templates*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-037` `/api/admin/automation-conversion/agents*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-038` `/api/admin/automation-conversion/agent-outputs*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-039` `/api/admin/automation-conversion/agent-runs*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-040` `/api/admin/automation-conversion/agent-replay`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-041` `/api/admin/automation-conversion/agent-orchestration*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-042` `/api/admin/automation-conversion/action-templates*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-043` `/api/admin/automation-conversion/task-groups*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-044` `/api/admin/automation-conversion/tasks*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-045` `/api/admin/automation-conversion/workflows*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-046` `/api/admin/automation-conversion/workflow-nodes*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-047` `/api/admin/automation-conversion/dashboard`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-048` `/api/admin/automation-conversion/executions*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-049` `/api/admin/automation-conversion/execution-items*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-050` `/api/admin/automation-conversion*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-051` `/api/customer-automation*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-052` `/api/customers/automation/signup-conversion/batches*`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-053` `/api/customers/automation/activation-webhook`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-054` `/api/customers/automation/webhook-deliveries`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-055` `/api/customers/automation/webhook-deliveries/{delivery_id}/retry`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-056` `/api/customers/automation/webhook-deliveries/retry-due`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-057` `/api/admin/wechat-pay/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-058` `/api/admin/wechat-pay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-059` `/api/admin/alipay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-060` `/api/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-061` `/p/{page_slug}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-062` `/pay/{product_code}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-063` `/api/orders*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-064` `/api/checkout*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-065` `/api/wechat-pay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-066` `/api/alipay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-067` `/api/h5/wechat-pay*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-068` `/api/h5/alipay*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-069` `/api/admin/image-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-070` `/api/admin/image-library/upload`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-071` `/api/admin/attachment-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-072` `/api/admin/miniprogram-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-073` `/sidebar/bind-mobile`: `P0` / `phase_3_readonly` / `shell_or_navigation` / owner `aicrm_next.frontend_compat`
- `LRB-074` `/api/sidebar/contact-binding-status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.identity_contact`
- `LRB-075` `/api/sidebar/customer-context`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-076` `/api/admin/customers/profile`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-077` `/api/admin/customers/profile/tags`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-078` `/api/sidebar/bind-mobile`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.frontend_compat`
- `LRB-079` `/api/sidebar/jssdk-config`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.frontend_compat`
- `LRB-080` `/api/sidebar/lead-pool/status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-081` `/api/sidebar/lead-pool/upsert-class-term`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-082` `/api/sidebar/signup-tags/status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-083` `/api/sidebar/signup-tags/mark`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.customer_read_model`
- `LRB-084` `/api/sidebar/marketing-status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-085` `/api/sidebar/marketing-status*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-086` `/api/sidebar/v2*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_read_model`
- `LRB-087` `/api/sidebar/v2/profile`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.customer_read_model`
- `LRB-088` `/api/sidebar/v2/materials/send`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.customer_read_model`
- `LRB-089` `/wecom/external-contact/callback`: `P2` / `retired` / `channel_entry` / owner `aicrm_next.channel_entry`
- `LRB-090` `/api/wecom/events`: `P2` / `retired` / `channel_entry` / owner `aicrm_next.channel_entry`
- `LRB-091` `/mcp`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.integration_gateway`
