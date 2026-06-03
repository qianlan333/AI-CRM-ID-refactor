# WeCom Tag Read Route Inventory

Scope: Legacy Exit group 12 moves WeCom tag and tag-group read surfaces to a Next-native tag catalog read model. This group does not delete the write/sync legacy fallback, does not create/update/delete tags or groups, does not execute real WeCom sync, and does not mutate customer or questionnaire tags. Payment, storage, OpenClaw, and automation runtime remain out of scope.

| route | method | caller | current owner | expected owner | read/write | data source | external side effect risk | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/wecom/tags` | `GET` | WeCom tag management page, questionnaire editor tag picker, channel admission tag picker, automation agent tag picker | legacy-forwarded when production facade is enabled | `aicrm_next.customer_tags` | read | Next tag catalog read model over `wecom_corp_tag_groups` / `wecom_corp_tags`; local contract probe outside production | none | Exact Next read route before production_compat; keep response shape compatible with existing frontend | `next_primary_with_legacy_rollback` | `tests/test_wecom_tag_read_next_native.py`, `tests/test_wecom_tag_read_selectors.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tags/{tag_id}` | `GET` | Optional direct tag detail read | legacy wildcard if facade is enabled | `aicrm_next.customer_tags` | read | Same tag catalog read model | none | Exact Next detail filter over catalog | `next_primary_with_legacy_rollback` | `tests/test_wecom_tag_read_next_native.py` |
| `/api/admin/wecom/tag-groups` | `GET` | WeCom tag management page group endpoint; smoke and selector-compatible group catalog | legacy-forwarded when production facade is enabled | `aicrm_next.customer_tags` | read | Same tag catalog read model | none | Exact Next read route before production_compat; return groups as first-class items | `next_primary_with_legacy_rollback` | `tests/test_wecom_tag_read_next_native.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tag-groups/{group_id}` | `GET` | Optional direct tag-group detail read | legacy wildcard if facade is enabled | `aicrm_next.customer_tags` | read | Same tag catalog read model | none | Exact Next group detail filter over catalog | `next_primary_with_legacy_rollback` | `tests/test_wecom_tag_read_next_native.py` |
| `/api/admin/wecom/tags/live/gate` | `GET` | Existing live adapter gate check | `aicrm_next.customer_tags` | out of scope | gated external adapter read | explicit live adapter gate | high | Not handled in group 12; remains blocked unless explicit live flags are set | active; not deletion_locked | `tests/test_wecom_tag_read_no_real_side_effects.py` |
| `/api/sidebar/signup-tags/status` | `GET` | Sidebar signup status surface | `aicrm_next.customer_read_model` | unchanged | read | customer read model status, not tag catalog selector | none | Not a tag catalog selector; no route change in this group | already locked by sidebar readonly group | `tests/test_sidebar_readonly_next_native.py` |
| `/api/admin/wecom/tags*` | `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | tag CRUD, sync, fake-stub write, live mark/unmark subpaths | production_compat | production_compat | write/sync | legacy guarded route or existing adapter gates | high | Out of scope; no real sync in this group | active; not deletion_locked | `tests/test_wecom_tag_read_inventory.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tag-groups*` | `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | tag group CRUD | production_compat | production_compat | write | legacy guarded route | guarded | Out of scope | active; not deletion_locked | `tests/test_wecom_tag_read_inventory.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |

## A. Read Routes

- `/api/admin/wecom/tags`, `/api/admin/wecom/tags/{tag_id}`, `/api/admin/wecom/tag-groups`, and `/api/admin/wecom/tag-groups/{group_id}` are exact Next read routes.
- These routes return `ok`, `groups`, `tags`, `items`, `count`, `source_status`, `read_model_status`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`, and `sync_executed=false`.
- Local/test mode uses `local_contract_probe`; production mode uses the PostgreSQL projection tables and returns `production_unavailable` if the projection is not available.
- Empty production projection tables return an empty catalog rather than fixture data.

## B. Selector Surfaces

- Questionnaire editor, channel admission, automation agent config, and WeCom tag management selectors already read `/api/admin/wecom/tags`.
- No separate sidebar tag catalog selector route was found. `/api/sidebar/signup-tags/status` is a customer read-model status route and remains unchanged.

## C. Write Out Of Scope

- Tag create/update/delete, tag-group create/update/delete, fake-stub writes, live mark/unmark, and sync endpoints remain production_compat rollback paths.
- These write/sync routes are not deletion locked in this group.
- Manifest wildcard families `/api/admin/wecom/tags*` and `/api/admin/wecom/tag-groups*` stay production_compat out of scope until follow-up deletion validation.

## D. External Side Effects Out Of Scope

- This group does not call WeCom, does not sync tags, does not mutate customer tags, and does not execute questionnaire tag side effects.
