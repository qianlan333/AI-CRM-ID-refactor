# WeCom Tag Read Route Inventory

Scope: Legacy Exit group 12 moves WeCom tag and tag-group read surfaces to a Next-native tag catalog read model and locks the read legacy rollback after validation. Group 13 later deleted the exact write/sync production_compat rollback and locked those exact routes on Next CommandBus. Real WeCom sync/mutation, customer/questionnaire tag mutation, payment, storage, OpenClaw, and automation runtime remain out of scope unless separately noted.

| route | method | caller | current owner | expected owner | read/write | data source | external side effect risk | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/wecom/tags` | `GET` | WeCom tag management page, questionnaire editor tag picker, channel admission tag picker, automation agent tag picker | `aicrm_next.customer_tags` | `aicrm_next.customer_tags` | read | Next tag catalog read model over `wecom_corp_tag_groups` / `wecom_corp_tags`; local contract probe outside production | none | Exact Next read route before production_compat; keep response shape compatible with existing frontend; no legacy rollback | `deletion_locked` | `tests/test_wecom_tag_read_next_native.py`, `tests/test_wecom_tag_read_selectors.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tags/{tag_id}` | `GET` | Optional direct tag detail read | `aicrm_next.customer_tags` | `aicrm_next.customer_tags` | read | Same tag catalog read model | none | Exact Next detail filter over catalog; no legacy rollback | `deletion_locked` | `tests/test_wecom_tag_read_next_native.py` |
| `/api/admin/wecom/tag-groups` | `GET` | WeCom tag management page group endpoint; smoke and selector-compatible group catalog | `aicrm_next.customer_tags` | `aicrm_next.customer_tags` | read | Same tag catalog read model | none | Exact Next read route before production_compat; return groups as first-class items; no legacy rollback | `deletion_locked` | `tests/test_wecom_tag_read_next_native.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tag-groups/{group_id}` | `GET` | Optional direct tag-group detail read | `aicrm_next.customer_tags` | `aicrm_next.customer_tags` | read | Same tag catalog read model | none | Exact Next group detail filter over catalog; no legacy rollback | `deletion_locked` | `tests/test_wecom_tag_read_next_native.py` |
| `/api/admin/wecom/tags/live/gate` | `GET` | Existing live adapter gate check | `aicrm_next.customer_tags` | out of scope | gated external adapter read | explicit live adapter gate | high | Not handled in group 12; remains blocked unless explicit live flags are set | active; not deletion_locked | `tests/test_wecom_tag_read_no_real_side_effects.py` |
| `/api/sidebar/signup-tags/status` | `GET` | Sidebar signup status surface | `aicrm_next.customer_read_model` | unchanged | read | customer read model status, not tag catalog selector | none | Not a tag catalog selector; no route change in this group | already locked by sidebar readonly group | `tests/test_sidebar_readonly_next_native.py` |
| `/api/admin/wecom/tags*` | `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | fake-stub write, live mark/unmark, and future auxiliary subpaths | `aicrm_next.customer_tags` | `aicrm_next.customer_tags` | auxiliary write/gated side effects | Next auxiliary routes or existing adapter gates | high | Exact CRUD/sync rollback removed in group 13; auxiliary live/fake subpaths remain out of scope | active; not deletion_locked | `tests/test_wecom_tag_read_inventory.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tag-groups*` | `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | future auxiliary tag-group subpaths | `aicrm_next.customer_tags` | `aicrm_next.customer_tags` | auxiliary write | no production_compat fallback | high | Exact tag-group CRUD rollback removed in group 13 | active; not deletion_locked | `tests/test_wecom_tag_read_inventory.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |

## A. Read Routes

- `/api/admin/wecom/tags`, `/api/admin/wecom/tags/{tag_id}`, `/api/admin/wecom/tag-groups`, and `/api/admin/wecom/tag-groups/{group_id}` are exact Next read routes.
- These routes return `ok`, `groups`, `tags`, `items`, `count`, `source_status`, `read_model_status`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`, and `sync_executed=false`.
- The read legacy rollback is removed and locked: registry `legacy_fallback_allowed=false`, `delete_status=deletion_locked`, `replacement_status=locked`.
- Local/test mode uses `local_contract_probe`; production mode uses the PostgreSQL projection tables and returns `production_unavailable` if the projection is not available.
- Empty production projection tables return an empty catalog rather than fixture data.

## B. Frontend API Backend Contract Matrix

| product entry | frontend file | frontend API URL | backend exact route | handler / service / repo | required response fields | registry / manifest item | smoke URL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/wecom-tags` | `aicrm_next/frontend_compat/templates/admin_console/config_wecom_tags.html`; `aicrm_next/frontend_compat/static/admin_console/wecom_tag_management.js` | `data-api-tags="/api/admin/wecom/tags"`; `data-api-groups="/api/admin/wecom/tag-groups"` | `GET /api/admin/wecom/tags`; `GET /api/admin/wecom/tag-groups`; optional detail routes | `list_admin_wecom_tags_read_model`; `list_admin_wecom_tag_groups_read_model`; `_read_catalog_payload`; `TagCatalogRepository`; `PostgresTagCatalogRepository`; production unavailable uses `_production_unavailable` with controlled empty catalog | `items`, `groups`, `tags`, `tag_id`, `tag_name`, `group_id`, `group_name`, `count`, `route_owner`, `fallback_used`, `real_external_call_executed`, `sync_executed` | `wecom_tags_read_next_native`; `wecom_tag_groups_read_next_native`; manifest `/api/admin/wecom/tags`, `/api/admin/wecom/tag-groups` | `/admin/wecom-tags`; `/api/admin/wecom/tags`; `/api/admin/wecom/tag-groups` |
| `/admin/questionnaires/new` | `aicrm_next/frontend_compat/templates/admin_questionnaires.html` | `fetchJson('/api/admin/wecom/tags')` | `GET /api/admin/wecom/tags` | same Next tag catalog read model; no production_compat fallback | same selector fields; degraded empty catalog is shown as a warning and manual `tag_id` entry remains available | `wecom_tags_read_next_native`; manifest `/api/admin/wecom/tags` | `/admin/questionnaires/new`; `/api/admin/wecom/tags` |
| `/admin/questionnaires/{questionnaire_id}` | `aicrm_next/frontend_compat/templates/admin_questionnaires.html` | `fetchJson('/api/admin/wecom/tags')` | `GET /api/admin/wecom/tags` | same Next tag catalog read model; no questionnaire mutation in this group | same selector fields | `wecom_tags_read_next_native`; manifest `/api/admin/wecom/tags` | `/admin/questionnaires/1`; `/api/admin/wecom/tags` |
| `/admin/channels` | `aicrm_next/frontend_compat/templates/admin_console/channel_code_center.html`; no tag selector on list page | none on list page | none | channel list is not a tag catalog caller | not applicable | not applicable | `/admin/channels` |
| `/admin/channels/{channel_id}/edit` | `aicrm_next/frontend_compat/templates/admin_console/channel_code_form.html`; `aicrm_next/frontend_compat/static/admin_console/channel_admission_pages.js`; context from `_channel_form_payload` | `(bootstrap.api_urls || {}).wecom_tags || "/api/admin/wecom/tags"` | `GET /api/admin/wecom/tags` | same Next tag catalog read model; no channel mutation in this group | same selector fields | `wecom_tags_read_next_native`; manifest `/api/admin/wecom/tags` | `/admin/channels/1/edit`; `/api/admin/wecom/tags` |
| `/admin/automation-conversion` | `aicrm_next/frontend_compat/templates/admin_console/automation_program_list.html`; no tag selector on overview page | none on overview page | none | automation overview is not a tag catalog caller | not applicable | not applicable | `/admin/automation-conversion` |
| `/admin/automation-conversion/programs/{program_id}/setup` | `aicrm_next/frontend_compat/static/admin_console/automation_agent_config_channel_model.js`; `aicrm_next/frontend_compat/static/admin_console/automation_agent_config_tag_picker.js`; setup workspace bootstrap `apiUrls.wecom_tags` | `apiUrls.wecom_tags` pointing to `/api/admin/wecom/tags` | `GET /api/admin/wecom/tags` | same Next tag catalog read model; no automation runtime mutation in this group | same selector fields | `wecom_tags_read_next_native`; manifest `/api/admin/wecom/tags` | `/admin/automation-conversion/programs/1/setup`; `/api/admin/wecom/tags` |

## C. Selector Surfaces

- Questionnaire editor, channel admission, automation agent config, and WeCom tag management selectors already read `/api/admin/wecom/tags`.
- No separate sidebar tag catalog selector route was found. `/api/sidebar/signup-tags/status` is a customer read-model status route and remains unchanged.

## D. Write Out Of Scope

- Exact tag create/update/delete, tag-group create/update/delete, and sync endpoints were locked to Next CommandBus in group 13 and no longer have production_compat rollback.
- Fake-stub writes, live mark/unmark, customer mutation, and questionnaire tag mutation remain out of scope for the read closeout and the write rollback deletion.
- Manifest wildcard families `/api/admin/wecom/tags*` and `/api/admin/wecom/tag-groups*` now document Next auxiliary/out-of-scope subpaths rather than production_compat fallback.

## E. External Side Effects Out Of Scope

- This group does not call WeCom, does not sync tags, does not mutate customer tags, and does not execute questionnaire tag side effects.
