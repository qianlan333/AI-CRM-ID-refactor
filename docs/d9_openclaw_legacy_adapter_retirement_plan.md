# D9 OpenClaw Legacy Adapter Retirement Plan

## Goal

D9.0 creates the physical retirement planning gate for the OpenClaw legacy adapter. It documents how `openclaw_service/` can later be frozen, moved, archived, replaced, and eventually removed after production evidence exists.

This slice is planning only. It does not move or delete `openclaw_service/`, does not call OpenClaw, does not call an external MCP service, does not send webhooks, does not change production configuration, and does not cut traffic.

## Current State

- `openclaw_service/` still exists.
- `openclaw_service/LEGACY_FROZEN.md` still exists.
- AI-CRM Next has D7.7 fake/staging-disabled MCP and OpenClaw compatibility contracts.
- Real OpenClaw and external MCP calls are not enabled for production behavior.
- OpenClaw legacy adapter code remains a fallback/reference surface for rollback, tool-name compatibility, plugin validation, and old operational notes.
- `app.py run` remains AI-CRM Next by default.
- `legacy_flask/` and `wecom_ability_service/` remain retained compatibility/fallback packages.

## Why Not Delete Immediately

- Real OpenClaw bridge behavior has not been cut over with production evidence.
- MCP tool compatibility still needs staging or production-like verification.
- OpenClaw webhook, bearer token, plugin, and skill compatibility have not been proven against the real runtime.
- Legacy skill names and old payload shapes are not fully confirmed against every historical OpenClaw workflow.
- Rollback may still need the legacy adapter reference while D7.7 remains fake/staging-disabled.
- Operational docs, scripts, and plugin validation notes still reference old OpenClaw/MCP paths.
- Webhook replay, retry, and duplicate push behavior still need real-environment evidence before any physical removal.

## D9 Phases

| phase | name | scope | runtime change |
| --- | --- | --- | --- |
| D9.0 | Retirement planning / readiness gate | Inventory, compatibility matrix, checker, tests, and gates | none |
| D9.1 | Freeze OpenClaw legacy adapter imports | Prevent new runtime imports and add review checks | import freeze ready |
| D9.2 | Move OpenClaw legacy adapter under archive package | Move only after import freeze and rollback plan | move planning ready |
| D9.3 | Create OpenClaw legacy archive skeleton | Create skeleton only, no file move or shim | skeleton created |
| D9.4 | Replace remaining docs/scripts references and move files | Move files with shim, then rewrite docs/scripts/plugin notes | planned |
| D9.4 | Disable legacy OpenClaw adapter runtime loading | Disable any remaining legacy runtime bridge outside emergency rollback | planned |
| D9.5 | Physical deletion after evidence and signoff | Remove old adapter after evidence, rollback proof, and human approval | planned |

D9.0 is accepted. D9.1 adds the import freeze policy, allowlist, checker, and tests without moving or deleting `openclaw_service/`. D9.2 adds move/archive planning, move map, import rewrite plan, checker, and tests without moving files. D9.3 creates the skeleton archive package without moving files or creating a shim.

## Delete Gate

Before `openclaw_service/` can be physically removed, all of the following must be true:

- D7.7 real OpenClaw and MCP replacement evidence exists.
- No runtime import of `openclaw_service` exists in AI-CRM Next or legacy fallback startup paths.
- No docs, scripts, deploy notes, plugin instructions, or tests reference the old path except archive notes.
- MCP tool compatibility is verified in staging or a production-like environment.
- OpenClaw plugin and skill bridge behavior is validated or explicitly deprecated.
- Bearer token and webhook token handling has a documented security review.
- Webhook replay, retry, duplicate-delivery, and rollback behavior has evidence.
- Rollback no longer requires the old adapter.
- Backup, restore, and git revert plans exist.
- Human signoff is recorded.

## Rollback

D9.0 changes only documentation, checker, and tests. It does not change runtime behavior.

Future D9.1-D9.5 phases must each have a separate rollback plan. Physical deletion must remain git-revertable and must not be combined with production configuration changes. If a later archive or deletion phase fails, rollback should restore the last retained adapter package and re-run D7.7 and D9 readiness checks.

## D9.0 Status

- `openclaw_legacy_adapter_status = retirement_planning_ready`
- `openclaw_service_deleted = false`
- `openclaw_service_moved = false`
- `openclaw_legacy_import_freeze_status = ready`
- `openclaw_legacy_move_status = planning_ready`
- `legacy_flask_openclaw_legacy_status = skeleton_created`
- `openclaw_service_shim_created = false`
- `new_runtime_imports_allowed = false`
- `real_openclaw_call_executed = false`
- `production_config_modified = false`
- deletion readiness remains false

## D9.4 Status Update

- `openclaw_legacy_files_moved = true`
- `openclaw_service_deleted = false`
- `openclaw_service_is_compatibility_shim = true`
- `legacy_flask_openclaw_legacy_contains_moved_files = true`
- `real_openclaw_call_executed = false`
- `production_config_modified = false`
- deletion readiness remains false

## D9.5 Status Update

- `openclaw_service_shim_removal_status = planning_ready`
- `openclaw_service_deleted = false`
- `openclaw_service_shim_deleted = false`
- `legacy_flask_openclaw_legacy_retained = true`
- `production_config_modified = false`
- `real_openclaw_call_executed = false`
- deletion readiness remains false

## D9.5.1 Status Update

- `openclaw_service_shim_reference_scan_status = completed`
- `openclaw_service_shim_observation_status = pending_observation_evidence`
- `openclaw_service_deleted = false`
- `openclaw_service_shim_deleted = false`
- `production_config_modified = false`
- `real_openclaw_call_executed = false`
- deletion readiness remains false
- shim deletion PR candidate remains false

## Next Step

D9.5.1 acceptance, then operational observation evidence capture. Shim removal remains future work and requires production-like evidence, rollback proof, and human signoff.
