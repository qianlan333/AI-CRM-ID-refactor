# JS/API Guardrails

## Completed Stages

- Phase 1: route inventory, focused admin API docs correction, and the first `AdminApi` shared client.
- Phase 2: stronger `AdminApi.requestJson` behavior and deeper reuse from customer admin JS.
- Phase 3: customer detail split into ordinary static JS files under `window.CustomerProfile`.
- Phase 4: Customer Pulse Inbox split into ordinary static JS files under `window.CustomerPulseInbox`.
- Phase 5: automation auto reply workspace inline JS extracted into ordinary static JS files under `window.AutomationAutoReply`.
- Phase 7: automation overview workspace inline JS extracted into ordinary static JS files under `window.AutomationOverview`.

## Shared Principles

- Flask remains the backend API/BFF layer.
- Jinja remains the page shell.
- Admin page JavaScript uses plain static files and a `window` namespace.
- The current stage does not use Vite, TypeScript, React, or Vue.
- Shared request, JSON parsing, and HTML escaping helpers go through `AdminApi`.
- Page-specific tenant, actor, and action-token behavior stays in the page namespace.
- API paths do not change as part of JS modularization.
- Authentication and RBAC do not change as part of JS modularization.
- Database schema does not change as part of JS modularization.

## Adding New Admin JS

- Do not put large inline JavaScript blocks in templates.
- Put new page scripts under `wecom_ability_service/static/admin_console/`.
- Use a page namespace such as `window.SomeWorkspace`.
- Prefer small files with clear responsibilities: `core`, `renderers`, `actions`, `boot`, and a small entrypoint.
- Load scripts from the template `scripts_extra` block in dependency order with `defer`.
- Do not use `import`, `export`, or `require` unless a separate PR introduces and documents frontend build tooling.
- Do not copy `requestJson`, `escapeHtml`, or `safeJsonParse`; reuse `AdminApi`.
- Keep page-specific action-token or tenant logic local to the page namespace.

## Current Guardrail Coverage

- Customer detail page script order and `CustomerProfile` modules.
- Customer Pulse Inbox script order and `CustomerPulseInbox` modules.
- Automation auto reply script order and `AutomationAutoReply` modules.
- Automation overview script order and `AutomationOverview` modules.
- `AdminApi` shared-client contract.
- Base template order: `admin_api_client.js` before `admin_console.js`.
- No frontend build tooling in the repository root.

The executable audit is `scripts/audit_admin_static_js.py`. It is intentionally scoped to the protected Phase 3-7 pages and static JS files, including `automation_conversion_overview_workspace.html` and `automation_overview*.js`, not to every legacy admin template.

## Next Steps

- Continue splitting automation conversion by small, bounded workspaces.
- Keep Vite or TypeScript proof-of-concept work in a separate PR from business migration work.
- If frontend build tooling is introduced later, update this guardrail document, the audit script, static tests, and deployment notes in the same PR.
