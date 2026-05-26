# Send Content Composer Next-Native Frontend

The standard composer frontend is implemented only under `aicrm_next/frontend_compat`:

- `static/admin_console/send_content_composer.js`
- `static/admin_console/send_content_composer.css`
- `static/admin_console/material_picker.js`
- `static/admin_console/material_picker.css`
- `templates/admin_console/_automation_operation_orchestration_panel.html`

No matching files are added to old Flask templates or old Flask static directories.

## Boundary

The composer configures only `SendContentPackage`.

The outer automation page owns:

- mode selection
- profile template selection for `profile_layered`
- behavior rule selection for `behavior_layered`
- agent selection for `agent`

The composer owns:

- copy text when enabled
- image material IDs
- miniprogram material IDs
- attachment material IDs
- selected material display
- local preview

Agent mode opens the same composer with `textEnabled=false`, hides the copy textarea and customer-name insertion, and saves only material IDs into `agent_config_json`.

## Material Selection

Material selection is centralized through `AICRMMaterialPicker`.

The picker reads only `GET /api/admin/material-picker/items`. It does not fetch the image, miniprogram, or attachment library APIs directly, and it uses `thumbnail_url` for images instead of fetching original base64 payloads.

## Old Flask

Do not add old Flask template/static copies, do not route through `production_compat`, and do not maintain two versions of this UI.
