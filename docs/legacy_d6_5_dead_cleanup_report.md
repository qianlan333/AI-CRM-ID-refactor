# Legacy D6.5 Dead Cleanup Report

## Goal

D6.5 starts physical cleanup after D1-D6 readonly route retirement. The scope is deliberately narrow: remove unreferenced readonly leftovers only, preserve every write, external, runtime, payment, OAuth, WeCom, OpenClaw, cloud, archive, contacts, and identity fallback, and keep AI-CRM Next as the default runtime.

This is not D7 write/external retirement. It does not replace or remove real external adapters.

## Scan Scope

The cleanup used these scans across `wecom_ability_service`, `aicrm_next`, `tests`, `docs`, and `tools`:

- `rg image_library attachment_library miniprogram_library ...`
- `rg admin_wechat_pay_products wechat-pay/products api/products /p/ ...`
- `rg customer_center customer_timeline api/customers admin/customers ...`
- `rg admin_user_ops user-ops batch-send do-not-disturb ...`
- `rg admin_questionnaires public_questionnaires api/h5/questionnaires questionnaire ...`
- `rg automation_conversion automation-conversion activation-webhook openclaw workflow ...`

The scan found many protected references in mixed write/external/runtime fallback paths. Only files with no runtime, registrar, test, tool, or exact path references were deleted.

## Actually Deleted Files

- `wecom_ability_service/templates/admin_console/attachment_library.html`
- `docs/generated/route_inventory.md`
- `docs/generated/route_inventory.json`

## Tombstone Files

- `wecom_ability_service/customer_center/LEGACY_DEPENDENCY_FALLBACK.md`
- `wecom_ability_service/customer_timeline/LEGACY_DEPENDENCY_FALLBACK.md`

No new tombstone file was added in D6.5.

## Not Deleted Due To References

- `wecom_ability_service/templates/admin_console/image_library.html`: rendered by AI-CRM Next frontend compatibility and covered by template tests.
- `wecom_ability_service/templates/admin_console/miniprogram_library.html`: rendered by AI-CRM Next frontend compatibility and covered by template tests.
- `wecom_ability_service/domains/image_library`: MCP adapter, product slices, tests, and media fallback still import it.
- `wecom_ability_service/domains/miniprogram_library`: automation welcome card and tests still import it.
- `wecom_ability_service/domains/attachment_library`: User Ops, automation, private message, marketing, and tests still import it.
- `wecom_ability_service/customer_center/`: MCP, admin profile, marketing, dashboard, and customer read application queries still import it.
- `wecom_ability_service/customer_timeline/`: MCP, automation orchestration, and customer read application queries still import it.
- `wecom_ability_service/http/admin_questionnaires.py`, `public_questionnaires.py`, and `admin_questionnaire_console.py`: still carry admin write, submit, and console POST fallback.
- `wecom_ability_service/http/automation_conversion.py` and related automation modules: still carry manual override, activation webhook, workflow/runtime, agent, OpenClaw, operation task, and dispatch fallback.

## Protected Files Kept

- `app.py`
- `legacy_flask_app.py`
- `wecom_ability_service/__init__.py`
- `wecom_ability_service/routes.py`
- `wecom_ability_service/http/__init__.py`
- `openclaw_service/`
- `wecom_ability_service/http/wechat_pay.py`
- `wecom_ability_service/http/alipay_pay.py`
- `wecom_ability_service/http/admin_wechat_pay.py`
- `wecom_ability_service/http/admin_alipay_pay.py`
- `wecom_ability_service/http/archive.py`
- `wecom_ability_service/http/contacts.py`
- `wecom_ability_service/http/identity.py`
- all Questionnaire submit, OAuth, admin write, diagnostics, and external-push fallback files
- all Automation write, external, workflow/runtime, agent, WeCom, and OpenClaw fallback files

## Reference Scan Summary

- D1 Media: old HTTP route modules are absent; attachment template was orphaned; image and miniprogram templates remain active through Next frontend compatibility.
- D2 Product: old admin product owner is absent; payment and public product fallback remain referenced.
- D3 Customer: old HTTP route modules are absent; dependency packages remain active fallback.
- D4 User Ops: old HTTP readonly owner is absent; write, send, and deferred job helpers remain protected.
- D5 Questionnaire: readonly route registrations are retired; mixed modules remain protected.
- D6 Automation: readonly route registrations and aliases are retired; mixed modules remain protected.

## Registrar Check Summary

`wecom_ability_service/http/__init__.py` no longer imports or registers the deleted D1-D6 readonly route owner modules. D6.5 deleted files are not referenced by the registrar.

## Legacy Fallback Check Summary

Expected smoke commands:

- `python3 app.py --help`
- `python3 legacy_flask_app.py --help`
- `from legacy_flask_app import main`

These checks must pass before D6.5 acceptance.

## Next Smoke And Parity Summary

D6.5 does not change AI-CRM Next route code. Required verification remains:

- AI-CRM Next pytest pass in the project venv.
- Six parity reports pass: User Ops, Customer Read Model, Questionnaire, Automation, Commerce, and Media.

## Production Safety

- production config modified: false
- real traffic cutover executed: false
- real external adapter call executed: false
- old system write endpoint executed: false
- Next write endpoint executed: false

## Risk

The only runtime-adjacent deletion is the old attachment-library Flask template. It is safe because old D1 route modules are gone and Next uses the placeholder template for `/admin/attachment-library`. The generated route inventory deletion removes stale evidence artifacts and has no runtime effect.

## Rollback

Rollback is a normal git revert of the D6.5 PR. Restoring the deleted template or generated inventory files does not require DB rollback and does not affect production route ownership.

## Next Step

D7 write/external blockers remain. The next step is D7 Write / External capability replacement planning, not deletion.
