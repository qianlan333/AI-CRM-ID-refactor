# WeCom Tag Read Route Inventory

Scope: Legacy Exit group 12 moves WeCom tag and tag-group read surfaces to a Next-native tag catalog read model. This group does not delete the write/sync legacy fallback, does not create/update/delete tags or groups, does not execute real WeCom sync, and does not mutate customer or questionnaire tags.

Search command:

```bash
grep -R "/api/admin/wecom/tags\|/api/admin/wecom/tag-groups\|signup-tags/status" -n \
  aicrm_next docs tests scripts wecom_ability_service 2>/dev/null
```

| route | method | caller | current owner | expected owner | read/write | data source | external side effect risk | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/wecom/tags` | `GET` | WeCom tag management page, questionnaire editor tag picker, channel admission tag picker, automation agent tag picker | legacy-forwarded when production facade is enabled | `aicrm_next.customer_tags` | read | Next tag catalog read model over `wecom_corp_tag_groups` / `wecom_corp_tags`; local contract probe outside production | none | Add exact Next read route before production_compat; keep response shape compatible with existing frontend | `next_primary_with_legacy_rollback` | `tests/test_wecom_tag_read_next_native.py`, `tests/test_wecom_tag_read_selectors.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tag-groups` | `GET` | WeCom tag management page group endpoint; smoke and selector-compatible group catalog | legacy-forwarded when production facade is enabled | `aicrm_next.customer_tags` | read | Next tag catalog read model over `wecom_corp_tag_groups` / `wecom_corp_tags`; local contract probe outside production | none | Add exact Next read route before production_compat; return groups as first-class items | `next_primary_with_legacy_rollback` | `tests/test_wecom_tag_read_next_native.py`, `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tags/{path:path}` | `GET` | No confirmed active read subpath in Next frontend; wildcard exists for legacy CRUD/sync subpaths | production_compat | production_compat | read probe / subpath fallback | legacy fallback only | guarded | Out of scope unless a real read subpath is found and inventoried as exact Next route | keep active, not deletion locked | `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/admin/wecom/tag-groups/{path:path}` | `GET` | No confirmed active read subpath in Next frontend; group create/update/delete uses method-specific paths | production_compat | production_compat | read probe / subpath fallback | legacy fallback only | guarded | Out of scope unless a real read subpath is found and inventoried as exact Next route | keep active, not deletion locked | `tests/test_wecom_tag_read_registry_lifecycle.py` |
| `/api/sidebar/signup-tags/status` | `GET` | Sidebar signup status surface | `aicrm_next.customer_read_model` | unchanged | read | customer read model status, not tag catalog selector | none | Not a tag catalog selector; no route change in this group | already locked by sidebar readonly group | `tests/test_sidebar_readonly_next_native.py` |
| `/api/admin/wecom/tags` | `POST` | Create tag / sync-compatible form actions | production_compat | production_compat | write | legacy WeCom adapter | guarded / real_blocked | Out of scope | keep active, not deletion locked | existing legacy tests |
| `/api/admin/wecom/tags/sync` | `POST` | Sync real WeCom tags | production_compat | production_compat | external sync | legacy WeCom adapter | real_blocked | Out of scope; no real sync in this group | keep active, not deletion locked | `tests/test_wecom_tag_read_no_real_side_effects.py` |
| `/api/admin/wecom/tags/sync-due` | `POST` | Scheduled sync trigger | production_compat | production_compat | external sync | legacy WeCom adapter | real_blocked | Out of scope; no real sync in this group | keep active, not deletion locked | `tests/test_wecom_tag_read_no_real_side_effects.py` |
| `/api/admin/wecom/tag-groups` | `POST` | Create tag group | production_compat | production_compat | write | legacy WeCom adapter | guarded / real_blocked | Out of scope | keep active, not deletion locked | existing legacy tests |
| `/api/admin/wecom/tag-groups/{group_id}` | `PUT`, `DELETE` | Update/delete tag group | production_compat | production_compat | write | legacy WeCom adapter | guarded / real_blocked | Out of scope | keep active, not deletion locked | existing legacy tests |
| `/api/admin/wecom/tags/{tag_id}` | `PUT`, `DELETE` | Update/delete tag | production_compat | production_compat | write | legacy WeCom adapter | guarded / real_blocked | Out of scope | keep active, not deletion locked | existing legacy tests |

## A. Read Routes

- `/api/admin/wecom/tags` and `/api/admin/wecom/tag-groups` are exact Next read routes.
- Both routes return `ok`, `groups`, `tags`, `items`, `count`, `source_status`, `read_model_status`, `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed=false`.
- Local/test mode uses `local_contract_probe`; production mode uses the PostgreSQL projection tables and returns `production_unavailable` if the projection is not available.

## B. Selector Surfaces

- Questionnaire editor, channel admission, automation agent config, and WeCom tag management selectors already read `/api/admin/wecom/tags`.
- No separate sidebar tag catalog selector route was found. `/api/sidebar/signup-tags/status` is a customer read-model status route and remains unchanged.

## C. Write Out Of Scope

- Tag create/update/delete, tag-group create/update/delete, and sync endpoints remain production_compat rollback paths.
- These write/sync routes are not deletion locked in this group.
- Manifest wildcard families `/api/admin/wecom/tags*` and `/api/admin/wecom/tag-groups*` stay production_compat out of scope until follow-up deletion validation.

## D. External Side Effects Out Of Scope

- This group does not call WeCom, does not sync tags, does not mutate customer tags, and does not execute questionnaire tag side effects.
