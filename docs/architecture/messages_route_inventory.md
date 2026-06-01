# Messages Route Inventory

Status: Legacy Exit group 3 inventory and exact-route replacement plan.

Scope: `/api/messages*` only. This inventory does not delete the broad production_compat wildcard; it narrows known callers to exact Next routes for one validation cycle.

| Path | Method | Caller | Current owner | Expected owner | Read/write | External side effect risk | Replacement decision | Delete decision | Test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/messages/{external_userid}/recent` | GET | `aicrm_next/customer_read_model/parity_spec.py`, `tests/test_api.py`, `tests/contract/test_crm_contract.py`, `docs/mcp_usage.md` | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model` | read | none | Already exact Next route; customer read model owns it and production errors return `production_unavailable` | customer read legacy deleted; broad `/api/messages*` still retained separately | `tests/test_customer_read_model_next_primary.py`, `tests/test_messages_registry_lifecycle.py` |
| `/api/messages/{external_userid}` | GET | `tests/test_api.py`, `tests/contract/test_crm_contract.py`, `docs/crm_sensitive_routes.md`, `tests/test_http_registration_contract.py` | production_compat wildcard | `aicrm_next.message_archive` | read | none | Add exact Next message archive list route | keep broad wildcard for one validation cycle | `tests/test_messages_exact_routes.py` |
| `/api/messages/search` | GET | `tests/test_api.py`, `tests/contract/test_crm_contract.py`, `docs/crm_sensitive_routes.md`, `tests/test_http_registration_contract.py` | production_compat wildcard | `aicrm_next.message_archive` | read | none | Add exact Next message archive search route | keep broad wildcard for one validation cycle | `tests/test_messages_exact_routes.py` |
| `/api/messages/archive` | GET | no active caller found; historical archive naming surface | production_compat wildcard | `aicrm_next.message_archive` | read | none | Add explicit deprecated response with replacement route | observe for one validation cycle; no legacy forward | `tests/test_messages_exact_routes.py` |
| `/api/messages/{external_userid}/archive` | GET | no active caller found; historical archive naming surface | production_compat wildcard | `aicrm_next.message_archive` | read | none | Add explicit deprecated response with replacement route | observe for one validation cycle; no legacy forward | `tests/test_messages_exact_routes.py` |
| `/api/messages/{external_userid}/history` | GET | no active caller found; historical history naming surface | production_compat wildcard | `aicrm_next.message_archive` | read | none | Add explicit deprecated response with replacement route | observe for one validation cycle; no legacy forward | `tests/test_messages_exact_routes.py` |
| `/api/messages/send` | GET/POST/OPTIONS | no active caller found; historical write/send naming surface | production_compat wildcard | `aicrm_next.message_archive` | write | real blocked | Add explicit blocked response with `side_effect_plan`; no real WeCom send | observe for one validation cycle; no legacy forward | `tests/test_messages_no_real_side_effects.py` |
| `/api/messages/broadcast` | GET/POST/OPTIONS | no active caller found; historical broadcast naming surface | production_compat wildcard | `aicrm_next.message_archive` | write | real blocked | Add explicit blocked response with `side_effect_plan`; no real WeCom send | observe for one validation cycle; no legacy forward | `tests/test_messages_no_real_side_effects.py` |
| `/api/messages/archive/sync` | GET/POST/OPTIONS | no active caller found; archive sync uses `/api/archive/sync`, not this route | production_compat wildcard | `aicrm_next.message_archive` | write/sync | real blocked | Add explicit blocked response with `side_effect_plan`; no real archive sync | observe for one validation cycle; no legacy forward | `tests/test_messages_no_real_side_effects.py` |
| `/api/messages*` | ALL | production_compat catch-all only | production_compat | production_compat for one validation cycle | mixed | guarded | Retain wildcard while exact routes collect validation evidence | deletion deferred to next专项测试 | `tests/test_messages_registry_lifecycle.py` |

Search evidence:

- `aicrm_next/customer_read_model/api.py` owns `GET /api/messages/{external_userid}/recent`.
- `aicrm_next/production_compat/api.py` still contains `@wildcard_router.api_route("/api/messages/{path:path}")`.
- `aicrm_next/message_archive/api.py` owns the new exact archive list/search routes plus explicit deprecated/blocked routes listed above.
- `aicrm_next/frontend_compat/api_docs_view_model.py` only groups `/api/messages/` paths for API docs display.
- `tests/test_api.py`, `tests/contract/test_crm_contract.py`, and `tests/test_http_registration_contract.py` reference `GET /api/messages/{external_userid}`, `GET /api/messages/{external_userid}/recent`, and `GET /api/messages/search`.
- `tests/test_messages_*.py` and `tests/test_route_registry_foundation.py` are validation coverage for this inventory and route registry behavior.
- `docs/development/legacy_replacement_backlog.md` and `.yaml` contain historical backlog entries for recent and broad wildcard; this inventory supersedes their operational decision for this group.
- `scripts/check_no_new_legacy.py` references `/api/messages/{external_userid}/recent` only as part of the customer-read deletion guard.
- Docs references are limited to `docs/crm_sensitive_routes.md`, `docs/mcp_usage.md`, and legacy replacement backlog entries.

Non-goals:

- No real WeCom send is enabled.
- No OpenClaw, payment, media storage, questionnaire, user-ops, or automation runtime send path is changed.
- `/api/messages*` broad wildcard is not deleted in this group.
