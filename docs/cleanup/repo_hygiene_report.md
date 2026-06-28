# Repo Hygiene Audit

Phase 2-1 scope: this report was regenerated after cleaning stale Markdown
internal references only. The previous baseline had 711
`missing_markdown_reference` findings; this run has 0. Remaining findings are
queued for later batches and are intentionally not handled in this document-only
PR.

- Version: `1`
- Root: `.`
- Generated at: `2026-06-28T13:31:54Z`
- Markdown files scanned: 232
- Issues: 49

## Issue Summary

- `agent_entry_overlap`: 1
- `aicrm_next_console_marker`: 23
- `aicrm_next_legacy_marker`: 13
- `aicrm_next_print_marker`: 10
- `tracked_artifact_candidate`: 2

## Issues

- **HYG-0001** `agent_entry_overlap` `review` `agent-entry-docs` - Multiple agent-facing entry documents exist and should share canonical preflight wording.
  - Evidence: .codex/skills/lobster-agent-orchestrator/README.md, .codex/skills/lobster-agent-orchestrator/SKILL.md, .codex/skills/lobster-agent-orchestrator/references/mcp-tool-matrix.md, AGENTS.md, CLAUDE.md, README.md, docs/development/ai_crm_next_architecture_skill.md, docs/development/codex_task_template.md, docs/skills/frontend-development-skill.md, skills/ai-crm-next-architecture/SKILL.md, skills/image-library-curator/README.md, skills/image-library-curator/SKILL.md, skills/image-library-curator/references/system-prompt.md, skills/image-library-curator/references/workflow-a-batch-annotate.md, skills/image-library-curator/references/workflow-b-upload-annotate.md, skills/image-library-curator/references/workflow-c-recommend.md, skills/lobster-crm-automation-workflows/SKILL.md, skills/lobster-crm-automation-workflows/references/tools.md
- **HYG-0002** `aicrm_next_console_marker` `review` `aicrm_next/admin_jobs/__init__.py:1` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0003** `aicrm_next_console_marker` `review` `aicrm_next/admin_jobs/templates/admin_console/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0004** `aicrm_next_console_marker` `review` `aicrm_next/admin_jobs/templates/admin_console/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0005** `aicrm_next_console_marker` `review` `aicrm_next/admin_shell/templates/admin_shell/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0006** `aicrm_next_console_marker` `review` `aicrm_next/admin_shell/templates/admin_shell/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0007** `aicrm_next_console_marker` `review` `aicrm_next/automation_engine/group_ops/templates/admin_console/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0008** `aicrm_next_console_marker` `review` `aicrm_next/automation_engine/group_ops/templates/admin_console/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0009** `aicrm_next_console_marker` `review` `aicrm_next/automation_engine/static/admin_console/channel_admission_pages.js:75` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0010** `aicrm_next_console_marker` `review` `aicrm_next/automation_engine/templates/admin_console/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0011** `aicrm_next_console_marker` `review` `aicrm_next/automation_engine/templates/admin_console/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0012** `aicrm_next_console_marker` `review` `aicrm_next/customer_tags/templates/admin_console/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0013** `aicrm_next_console_marker` `review` `aicrm_next/customer_tags/templates/admin_console/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0014** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js:89` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0015** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/api_docs.html:883` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0016** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/api_docs.html:906` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0017** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/api_docs.html:927` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0018** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0019** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0020** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/login.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0021** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/admin_console/miniprogram_library.html:440` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0022** `aicrm_next_console_marker` `review` `aicrm_next/frontend_compat/templates/questionnaire_h5_page.html:650` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0023** `aicrm_next_console_marker` `review` `aicrm_next/radar_links/templates/admin_console/base.html:7` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0024** `aicrm_next_console_marker` `review` `aicrm_next/radar_links/templates/admin_console/base.html:10` - `console.` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0025** `aicrm_next_legacy_marker` `review` `aicrm_next/automation_engine/application.py:47` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0026** `aicrm_next_legacy_marker` `review` `aicrm_next/automation_engine/application.py:64` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0027** `aicrm_next_legacy_marker` `review` `aicrm_next/automation_engine/application.py:81` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0028** `aicrm_next_legacy_marker` `review` `aicrm_next/customer_tags/wecom_tag_live_adapter.py:77` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0029** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/media_live_adapter.py:57` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0030** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/oauth_identity_adapter.py:92` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0031** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/oauth_identity_live_adapter.py:60` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0032** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/openclaw_mcp_ai_assist_live_adapter.py:87` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0033** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/payment_commerce_live_adapter.py:69` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0034** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/wecom_contact_callback_adapter.py:92` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0035** `aicrm_next_legacy_marker` `review` `aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py:67` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0036** `aicrm_next_legacy_marker` `review` `aicrm_next/questionnaire/external_submit_adapter.py:56` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0037** `aicrm_next_legacy_marker` `review` `aicrm_next/questionnaire/external_submit_live_adapter.py:74` - `production_compat` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0038** `aicrm_next_print_marker` `review` `aicrm_next/integration_gateway/user_ops_adapters.py:30` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0039** `aicrm_next_print_marker` `review` `aicrm_next/integration_gateway/user_ops_adapters.py:371` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0040** `aicrm_next_print_marker` `review` `aicrm_next/integration_gateway/user_ops_adapters.py:411` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0041** `aicrm_next_print_marker` `review` `aicrm_next/integration_gateway/user_ops_adapters.py:573` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0042** `aicrm_next_print_marker` `review` `aicrm_next/integration_gateway/user_ops_adapters.py:657` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0043** `aicrm_next_print_marker` `review` `aicrm_next/platform_foundation/external_effects/jobs.py:107` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0044** `aicrm_next_print_marker` `review` `aicrm_next/platform_foundation/external_effects/jobs.py:117` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0045** `aicrm_next_print_marker` `review` `aicrm_next/platform_foundation/legacy_cleanup/jobs.py:14` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0046** `aicrm_next_print_marker` `review` `aicrm_next/platform_foundation/legacy_cleanup/jobs.py:22` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0047** `aicrm_next_print_marker` `review` `aicrm_next/platform_foundation/legacy_cleanup/jobs.py:30` - `print(` appears in `aicrm_next/`.
  - Evidence: Review marker before turning hygiene checks into enforcement.
- **HYG-0048** `tracked_artifact_candidate` `review` `.codex_artifacts/automation_conversion_settings.png` - File lives under a generated-output or temporary artifact directory.
  - Evidence: Classify as durable evidence under docs/reports/evidence/ or generated output ignored by git.
- **HYG-0049** `tracked_artifact_candidate` `review` `artifacts/internal_event_coverage_audit.json` - File lives under a generated-output or temporary artifact directory.
  - Evidence: Classify as durable evidence under docs/reports/evidence/ or generated output ignored by git.

## Suggested Cleanup Batches

- Fix stale agent-entry references before changing runtime code.
- Decide whether tracked artifact directories are evidence or generated output.
- Review debug/TODO/legacy markers in `aicrm_next/` before expanding lint gates.
