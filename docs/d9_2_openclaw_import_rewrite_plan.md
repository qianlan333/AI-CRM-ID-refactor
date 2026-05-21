# D9.2 OpenClaw Import Rewrite Plan

## Current Import Graph Summary

D9.1 import freeze shows there are no runtime Python imports of `openclaw_service` in:

- `aicrm_next/**`
- `experiments/ai_crm_next/src/aicrm_next/**`
- `legacy_flask/**`
- `wecom_ability_service/**`
- `tools/**`
- `scripts/**`

The current `openclaw_service/` package is retained as a compatibility shim with `openclaw_service/LEGACY_FROZEN.md`. D9.4 also keeps `legacy_flask/openclaw_legacy/` as the archive package for the moved frozen marker. Current references are docs/tests/checker inventory references and metadata, not production runtime dependencies.

## Future Rewrite Strategy

If a future move creates `legacy_flask/openclaw_legacy/`, any approved legacy fallback import should be rewritten from:

```python
from openclaw_service... import ...
import openclaw_service...
```

to:

```python
from legacy_flask.openclaw_legacy... import ...
import legacy_flask.openclaw_legacy...
```

AI-CRM Next must not import either path. New application behavior remains behind the D7.7 MCP/OpenClaw adapter boundary.

## Temporary Shim Strategy

D9.4 keeps `openclaw_service/` as a temporary compatibility shim. The shim must:

- contain compatibility exports only;
- avoid new business logic;
- avoid OpenClaw calls, MCP external calls, and webhook delivery;
- be covered by D9.1 import freeze allowlist updates;
- expire in a later D9 phase after operational evidence and signoff.

## D9.4 Import Rewrite Result

- `aicrm_next/**` still has no `openclaw_service` import.
- `openclaw_service/__init__.py` forwards metadata to `legacy_flask.openclaw_legacy`.
- No production deploy or runtime traffic path was changed.

## D9.5 Shim Removal Planning Update

D9.5 does not remove the shim. It adds the final reference scan plan, readiness checklist, and observation-window gates needed before a future deletion PR can be prepared.

## Files Requiring Manual Rewrite

- `docs/d9_openclaw_legacy_adapter_retirement_plan.md`
- `docs/d9_openclaw_legacy_dependency_inventory.md`
- `docs/d9_1_openclaw_legacy_import_freeze_plan.md`
- `docs/d9_1_openclaw_import_allowlist.md`
- D9 checkers that currently verify `openclaw_service/` is still in place.
- D9 tests that currently assert the pre-move state.
- Any future docs/scripts that mention the old OpenClaw path.

## Files Not To Rewrite Yet

- `aicrm_next/**`: must continue to use D7.7 adapters, not legacy package imports.
- `legacy_flask/openclaw_legacy/**`: archive metadata only; no OpenClaw runtime bridge is implemented in D9.4.
- `legacy_flask/**` outside the skeleton: no direct archive import is needed yet.
- `wecom_ability_service/**`: no OpenClaw shim import is added.
- production deploy, nginx, systemd, and traffic configuration: no automatic rewrite.

## Docs / Tests / Checkers Update Plan

After a future physical move:

1. Update the D9 dependency inventory to show the archive package path.
2. Update the D9.1 allowlist to identify the compatibility shim and any static references.
3. Update D9 checkers to distinguish shim existence from old physical package retention.
4. Update tests to verify the archive package and shim behavior.
5. Keep D7.7 adapter contract tests unchanged as the primary Next boundary proof.
6. Update D9.3 skeleton checks to verify the moved files and compatibility shim rather than skeleton-only state.

## Rollback Strategy

The future move must be a standalone commit or PR segment so `git revert` can restore the pre-move path. If the shim fails, rollback restores the original `openclaw_service/` package and reruns D9.1/D9.2 checkers.

No production deploy path is changed by D9.2, and no production rollback depends on an automatic script in this slice.
