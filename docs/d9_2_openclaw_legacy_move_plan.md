# D9.2 OpenClaw Legacy Move Plan

## Goal

D9.2 plans a future move of `openclaw_service/` into `legacy_flask/openclaw_legacy/`.

This slice is planning only. It does not move files, does not delete `openclaw_service/`, does not create the future runtime package, does not call OpenClaw, does not call an external MCP service, does not send webhooks, does not change production configuration, and does not cut traffic.

AI-CRM Next continues to use the D7.7 MCP/OpenClaw adapter boundary. `app.py run` remains AI-CRM Next by default.

## Target Future Structure

Future implementation may create:

```text
legacy_flask/
  openclaw_legacy/
    __init__.py
    README.md
    LEGACY_FROZEN.md
    ...
```

`legacy_flask/openclaw_legacy/` would be an archive/fallback package only. It must not become a production owner, must not receive new OpenClaw/MCP features, and must not be imported by AI-CRM Next runtime code. The D7.7 adapter boundary remains the primary path for MCP/OpenClaw behavior.

## Proposed Move Mapping

| current_path | future_path | notes |
| --- | --- | --- |
| `openclaw_service/` | `legacy_flask/openclaw_legacy/` | move root after D9.1 import freeze acceptance and human signoff |
| `openclaw_service/LEGACY_FROZEN.md` | `legacy_flask/openclaw_legacy/LEGACY_FROZEN.md` | retain frozen marker after move |

If more files are added under `openclaw_service/` before implementation, each file must be added to the move map before any move starts.

## Import Rewrite Strategy

Future implementation should:

- rewrite `from openclaw_service...` to `from legacy_flask.openclaw_legacy...` only where a legacy fallback import is explicitly approved;
- keep `openclaw_service` as a temporary compatibility shim during the rollout window;
- keep the shim compatibility-only with no new business logic;
- keep `aicrm_next/**` blocked from importing either `openclaw_service` or the legacy archive package;
- update docs/tests/checkers static references after the physical move;
- keep production deploy and runtime defaults unchanged.

## Move Phases

| phase | name | scope |
| --- | --- | --- |
| D9.2.0 | planning only | move plan, move map, import rewrite plan, checker, tests |
| D9.2.1 / D9.3 | create package skeleton | create `legacy_flask/openclaw_legacy/` skeleton only after acceptance |
| D9.2.2 | move files | move frozen legacy files under archive package |
| D9.2.3 | create compatibility shim | keep `openclaw_service` import compatibility during rollout |
| D9.2.4 | update static references | update docs/tests/checkers/scripts references |
| D9.2.5 | remove shim after operational window | only after evidence and signoff |

D9.2.0 is complete. D9.3 created the skeleton only. D9.4 moved the metadata-only frozen marker into the archive package and retained `openclaw_service/` as a compatibility shim.

## Move Gate

Implementation must not start until all conditions are met:

- D9.1 import freeze PASS.
- No forbidden runtime imports.
- Dependency inventory complete.
- Move map complete.
- Import rewrite plan complete.
- D7.7 adapter contract remains PASS.
- Rollback plan approved.
- Human signoff.

## Rollback

The physical move must be git-revertable. A temporary `openclaw_service` compatibility shim must exist during rollout so old emergency references do not crash while static references are rewritten.

D9.2 makes no production configuration changes and performs no real OpenClaw calls. If a later move phase fails, rollback is to revert the package move and rerun D9.1/D9.2 checkers.

## D9.2 Status

- `openclaw_legacy_move_status = planning_ready`
- `openclaw_service_deleted = false`
- `openclaw_service_moved = metadata_marker_archived_with_shim`
- `legacy_flask_openclaw_legacy_status = archive_package_with_moved_legacy_files`
- `production_config_modified = false`
- deletion readiness remains false

## Next Step

D9.5 shim removal planning only after operational evidence, rollback proof, and human signoff.
