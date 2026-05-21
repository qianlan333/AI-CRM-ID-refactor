# D9.1 OpenClaw Legacy Import Freeze Plan

## Goal

`openclaw_service/` remains a frozen legacy package. D9.1 prevents new runtime imports from depending on it.

AI-CRM Next runtime paths must use the D7.7 MCP/OpenClaw adapter boundary instead of importing the legacy package. This phase does not delete, move, archive, or execute `openclaw_service/`. It also does not call OpenClaw, call an external MCP service, send webhooks, change production configuration, or cut traffic.

## Import Policy

| category | meaning | enforcement |
| --- | --- | --- |
| forbidden_runtime_import | Runtime Python code imports `openclaw_service` directly | checker blocker |
| allowed_legacy_fallback_import | Existing explicit fallback import with written rationale | allowlist required and expires in a future D9 phase |
| allowed_test_reference | Tests may assert path existence or absence of imports | static reference only, no direct package import |
| allowed_docs_reference | Docs may mention historical paths and retirement gates | static reference only |
| allowed_static_inventory_reference | Checkers may inspect paths or scan import text | static reference only |
| needs_manual_review | Any ambiguous legacy fallback or tooling reference | review before merge |

Default policy is deny. A path is not allowed just because it exists in the allowlist; the allowlist must also mark the reference as allowed and describe why it is not a runtime dependency.

## Forbidden Imports

The following are blocked by D9.1:

- `aicrm_next/**` importing `openclaw_service`.
- `experiments/ai_crm_next/src/aicrm_next/**` importing `openclaw_service`.
- `legacy_flask/**` adding a runtime import of `openclaw_service` unless explicitly allowlisted with a retirement phase.
- `wecom_ability_service/**` adding a runtime import of `openclaw_service` unless explicitly allowlisted with a retirement phase.
- `tools/**` importing `openclaw_service` at runtime, except checker/static inventory code that only scans paths or text.
- `scripts/**` importing `openclaw_service` at runtime.

AI-CRM Next and new runtime code must route through:

- `aicrm_next/integration_gateway/mcp_openclaw_adapters.py`
- `aicrm_next/integration_gateway/mcp_openclaw_contracts.py`
- the D7.7 MCP/OpenClaw gateway APIs

## Allowed References

Allowed references are static and bounded:

- `openclaw_service/LEGACY_FROZEN.md`
- D9 and legacy retirement docs that mention historical paths.
- D9 tests that assert the package still exists and is not imported by Next.
- D9 checkers that inspect path existence and scan import text.
- Existing legacy fallback references only when explicitly allowlisted with a reason and future retirement phase.

No allowed reference becomes a production owner, default runtime dependency, or evidence that the legacy adapter can be removed.

## Enforcement Strategy

- The checker parses Python files and detects actual `import openclaw_service` and `from openclaw_service ...` statements.
- The checker scans the allowlist for exceptions and fails if a runtime import is not allowlisted.
- Any `aicrm_next/**` import of the old package fails regardless of allowlist.
- Static docs/tests/checker references are reported as allowed references, not runtime dependencies.
- D9.2 cannot move or archive `openclaw_service/` until D9.1 import freeze acceptance passes.

## D9.1 Status

- `openclaw_legacy_import_freeze_status = ready`
- `openclaw_service_deleted = false`
- `openclaw_service_moved = false`
- `new_runtime_imports_allowed = false`
- `production_config_modified = false`
- deletion readiness remains false

## Next Step

D9.2 Move/archive planning or implementation may start only after D9.1 acceptance.
