# D8.3 Legacy Package Move Map

D8.3.0 is planning only. No file in this map is physically moved by this round.

| current_path | future_path | move_phase | import_rewrite_required | runtime_role | default_next_imported | legacy_fallback_imported | shim_required | move_blocker | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/__init__.py` | `legacy_flask/app_factory.py` | D8.4 | yes | legacy app factory | false | true | true | app factory smoke, D8.2 lockdown guard, rollback plan | D8.4 moved entry layer; old path is shim |
| `wecom_ability_service/routes.py` | `legacy_flask/routes.py` | D8.4 | yes | legacy route facade | false | true | true | route registrar smoke and retired route guard proof | D8.4 moved facade; old path is shim |
| `wecom_ability_service/http/__init__.py` | `legacy_flask/http/__init__.py` | D8.4 | yes | legacy HTTP registrar facade | false | true | true | import rewrite map and fallback route smoke | D8.4 moved registrar facade; old path is shim |
| `wecom_ability_service/http/*` | `legacy_flask/http/*` | future | yes | retained fallback HTTP modules | false | true | true | write/external fallback evidence and D8.2 lockdown coverage | most controller modules remain in old location |
| `wecom_ability_service/domains/*` | `legacy_flask/domains/*` | D8.3.3 | yes | retained fallback domain helpers | false | true | true | mixed fallback dependency audit | no move in D8.3.0 |
| `wecom_ability_service/templates/*` | `legacy_flask/templates/*` | D8.3.3 | path audit | legacy fallback templates | false | true | maybe | Flask template loader path proof | no move in D8.3.0 |
| `wecom_ability_service/static/*` | `legacy_flask/static/*` | D8.3.3 | path audit | legacy fallback static assets | false | true | maybe | static URL path proof | no move in D8.3.0 |
| `wecom_ability_service/legacy_lockdown.py` | `legacy_flask/legacy_lockdown.py` | D8.4 | yes | retired route guard | false | true | true | D8.2 checker must pass after rewrite | D8.4 moved guard; old path is shim |
| `openclaw_service/*` | keep independent until D9 or later `legacy_flask/openclaw_legacy/*` | D9 or later | yes if moved | OpenClaw legacy fallback/reference | false | true | maybe | D7.7/D9 compatibility gate and OpenClaw rollback proof | not part of D8.3 move |
| `legacy_flask_app.py` | stays as explicit runner importing `legacy_flask.app_factory` | D8.4 | yes | explicit fallback CLI | false | true | no | help/import smoke and rollback proof | file remains in place |
| `app.py` | stays in place | none | no default rewrite | AI-CRM Next default and legacy command dispatcher | false | conditional explicit fallback only | no | default runtime proof | must keep Next default |
| `tests/*` | update legacy imports to archive package where relevant | D8.3.2-D8.3.5 | yes | validation | false | conditional | no | focused test inventory | no test rewrite in D8.3.0 |
| `tools/*` | update legacy fallback tools where relevant | D8.3.2-D8.3.5 | yes | validation and diagnostics | false | conditional | no | checker and smoke inventory | no tool rewrite in D8.3.0 |
| `docs/*` | update references after move | D8.3.2-D8.3.5 | reference rewrite | documentation | false | false | no | docs consistency check | no physical move in D8.3.0 |
