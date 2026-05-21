# D9.5 OpenClaw Final Reference Scan Plan

| scan_target | command | expected_result | allowed_hits | blocker_if_found | owner | notes |
| --- | --- | --- | --- | --- | --- | --- |
| Python runtime imports | `rg "import openclaw_service|from openclaw_service" .` | no runtime imports outside planned shim smoke tests | `openclaw_service/__init__.py`, D9 checkers/tests, docs text | any `aicrm_next/**`, deploy script, or unclassified runtime import | migration owner | follow with AST-based checker for Python files |
| AI-CRM Next runtime | `rg "openclaw_service" aicrm_next experiments/ai_crm_next/src/aicrm_next` | zero hits | none | any hit | Next owner | D7.7 adapter boundary is the only allowed path |
| Legacy archive and fallback | `rg "openclaw_service" legacy_flask wecom_ability_service` | archive/fallback references only | docs comments or compatibility notices | runtime dependency not listed in allowlist | legacy owner | classify before D9.5.2 |
| Tools and tests | `rg "openclaw_service" tools tests` | checkers/tests only | D9 readiness checks and shim import smoke | unclassified operational tool dependency | migration owner | tooling must not call OpenClaw |
| Docs and scripts | `rg "openclaw_service" docs scripts deploy .github` | docs/archive references only | retirement docs, historical notes, planned deletion proposal | deploy, production workflow, or runbook dependency | release owner | deploy hits require manual review |
| Archive path references | `rg "legacy_flask.openclaw_legacy" .` | archive package and shim references only | D9 docs/checkers/tests and shim metadata | AI-CRM Next runtime import | migration owner | confirms replacement path is archive-only |

## D9.5.1 Execution Status

The final reference scan was executed and recorded in `docs/d9_5_1_openclaw_final_reference_scan_evidence.md`.

Result summary:

- AI-CRM Next runtime import hits: 0.
- Experiments Next mirror runtime import hits: 0.
- `deploy/`, `.github/`, and `scripts/` hits: 0.
- Docs/tests/checkers retain static references for retirement evidence and regression checks.
- Observation-window evidence remains pending.
