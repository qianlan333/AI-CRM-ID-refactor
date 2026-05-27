# Next Source Consolidation Report

Historical D6.5/D6.6 source-consolidation report: references to
`experiments/ai_crm_next/src/aicrm_next/**` below are deletion evidence only.
The duplicate package has been deleted and must not be restored; root
`aicrm_next/` is the only Next production source.

## Decision

- root source of truth: `aicrm_next/`.
- experiments source policy: `experiments/ai_crm_next/` keeps docs, tools, tests, fixtures, migrations, scripts, and project metadata only.
- duplicate source removed: `experiments/ai_crm_next/src/aicrm_next/**`.
- D7 write, external, runtime, payment, OAuth, WeCom, OpenClaw, archive, contacts, identity fallback files were not deleted.

## Equivalence Evidence

| check | result |
| --- | --- |
| root file count | `156` |
| duplicate file count | `156` |
| paths missing in root | `0` |
| paths extra in root | `0` |
| SHA-256 content differences | `0` |

Evidence command used before deletion:

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib
root=Path("aicrm_next")
dup=Path("experiments/ai_crm_next/src/aicrm_next")
# compare relative paths and sha256 for every file
PY
```

## Import Path Changes

- `experiments/ai_crm_next/pyproject.toml` now sets pytest `pythonpath = ["../.."]`, which points to the repository root package.
- experiment tools that previously inserted `PROJECT_ROOT / "src"` now insert the repository root before importing `aicrm_next`.
- experiment tests that inspect source files now read root `aicrm_next/` files.
- `tests/test_next_source_consolidation.py` guards the default runtime, duplicate-source absence, experiment import path, and root Next forbidden imports.

## Kept Experiment Materials

- `experiments/ai_crm_next/README.md`
- `experiments/ai_crm_next/alembic.ini`
- `experiments/ai_crm_next/docs/`
- `experiments/ai_crm_next/migrations/`
- `experiments/ai_crm_next/scripts/`
- `experiments/ai_crm_next/tests/`
- `experiments/ai_crm_next/tools/`
- `experiments/ai_crm_next/pyproject.toml`

## D1-D6 Dead Cleanup

- Additional safe cleanup in this batch is limited to stale `src/aicrm_next` references in experiment docs/tests/tools and the duplicate source tree itself.
- No uncertain D1-D6 fallback file was deleted. Existing protected or `needs_manual_review` entries in `docs/legacy_dead_code_inventory.md` remain in place.

## Deleted Duplicate Files

- `experiments/ai_crm_next/src/aicrm_next/__init__.py`
- `experiments/ai_crm_next/src/aicrm_next/ai_assist/api.py`
- `experiments/ai_crm_next/src/aicrm_next/ai_assist/application.py`
- `experiments/ai_crm_next/src/aicrm_next/ai_assist/followup.py`
- `experiments/ai_crm_next/src/aicrm_next/ai_assist/pulse.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/api.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/application.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/domain.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/parity_spec.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/state_machine.py`
- `experiments/ai_crm_next/src/aicrm_next/automation_engine/workflow.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/__init__.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/api.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/application.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/domain.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/parity_spec.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/payment_adapters.py`
- `experiments/ai_crm_next/src/aicrm_next/commerce/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/api.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/application.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/models.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/parity_spec.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/projections.py`
- `experiments/ai_crm_next/src/aicrm_next/customer_read_model/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/api_adapter_notes.md`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/legacy_routes.py`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/admin_api_client.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/admin_console.css`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/admin_console.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config_agents.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config_boot.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config_channel_model.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config_core.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config_tag_picker.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_agent_config_templates.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_auto_reply.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_auto_reply_actions.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_auto_reply_core.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_auto_reply_modal.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_auto_reply_outputs.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_conversion_workspace.css`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_overview.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_overview_actions.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_overview_core.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/automation_overview_renderers.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/customer_profile.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/customer_profile_automation.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/customer_profile_core.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/customer_profile_sections.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/image_picker.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/image_upload_client.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/jobs.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/static/admin_console/wecom_tag_management.js`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/_automation_operation_orchestration_panel.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/api_docs.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/audit.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/automation_program_list.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/automation_program_setup_wizard.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/base.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/broadcast_jobs.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/cloud_campaigns_workspace.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/cloud_integration_workspace.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/cloud_observability.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_app_settings.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_base.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_checklist.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_login_access.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_marketing_automation.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_mcp_tools.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_overview.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/config_wecom_tags.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/customer_detail.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/customers.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/dashboard.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/hxc_dashboard.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/hxc_send_config.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/image_library.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/jobs.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/login.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/miniprogram_library.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/operations.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/placeholder.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/questionnaire_detail.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/questionnaire_external_push_logs.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/questionnaires.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/setup_wizard.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/user_ops.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/wechat_pay_transactions.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_console/wecom_customer_acquisition_links.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_questionnaires.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/admin_user_ops.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/questionnaire_h5_page.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/questionnaire_h5_result.html`
- `experiments/ai_crm_next/src/aicrm_next/frontend_compat/templates/questionnaire_h5_submitted.html`
- `experiments/ai_crm_next/src/aicrm_next/identity_contact/api.py`
- `experiments/ai_crm_next/src/aicrm_next/identity_contact/application.py`
- `experiments/ai_crm_next/src/aicrm_next/identity_contact/domain.py`
- `experiments/ai_crm_next/src/aicrm_next/identity_contact/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/identity_contact/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/integration_gateway/api.py`
- `experiments/ai_crm_next/src/aicrm_next/integration_gateway/dispatch.py`
- `experiments/ai_crm_next/src/aicrm_next/integration_gateway/fake_adapters.py`
- `experiments/ai_crm_next/src/aicrm_next/integration_gateway/mcp.py`
- `experiments/ai_crm_next/src/aicrm_next/integration_gateway/ports.py`
- `experiments/ai_crm_next/src/aicrm_next/main.py`
- `experiments/ai_crm_next/src/aicrm_next/media_library/__init__.py`
- `experiments/ai_crm_next/src/aicrm_next/media_library/api.py`
- `experiments/ai_crm_next/src/aicrm_next/media_library/application.py`
- `experiments/ai_crm_next/src/aicrm_next/media_library/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/media_library/parity_spec.py`
- `experiments/ai_crm_next/src/aicrm_next/media_library/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/api.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/application.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/models.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/parity_spec.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/ops_enrollment/user_ops.py`
- `experiments/ai_crm_next/src/aicrm_next/platform_foundation/api.py`
- `experiments/ai_crm_next/src/aicrm_next/platform_foundation/application.py`
- `experiments/ai_crm_next/src/aicrm_next/platform_foundation/audit.py`
- `experiments/ai_crm_next/src/aicrm_next/platform_foundation/auth.py`
- `experiments/ai_crm_next/src/aicrm_next/platform_foundation/idempotency.py`
- `experiments/ai_crm_next/src/aicrm_next/platform_foundation/observability.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/api.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/application.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/domain.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/dto.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/oauth.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/parity_spec.py`
- `experiments/ai_crm_next/src/aicrm_next/questionnaire/repo.py`
- `experiments/ai_crm_next/src/aicrm_next/shared/config.py`
- `experiments/ai_crm_next/src/aicrm_next/shared/database.py`
- `experiments/ai_crm_next/src/aicrm_next/shared/errors.py`
- `experiments/ai_crm_next/src/aicrm_next/shared/pagination.py`
- `experiments/ai_crm_next/src/aicrm_next/shared/postgres_test_guard.py`
- `experiments/ai_crm_next/src/aicrm_next/shared/typing.py`
