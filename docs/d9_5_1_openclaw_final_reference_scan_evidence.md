# D9.5.1 OpenClaw Final Reference Scan Evidence

## Scope

D9.5.1 captures repository reference evidence before any future `openclaw_service/` shim deletion proposal. This round does not delete the shim, does not change production configuration, does not call OpenClaw or MCP external services, and does not cut traffic.

## Scan Summary

| scan_command | result_count | allowed_hits | blocked_hits | needs_manual_review_hits | evidence_summary |
| --- | ---: | --- | --- | --- | --- |
| `rg "import openclaw_service\|from openclaw_service" .` | 64 | `openclaw_service/__init__.py` shim docstring, tests/checkers negative assertions, D9 docs, historical archive docs | 0 | archived docs and historical runbook text should remain classified before a future removal PR | No AI-CRM Next runtime import was found; the direct import hits are shim/test/doc text only. |
| `rg "openclaw_service" aicrm_next experiments/ai_crm_next/src/aicrm_next` | 0 | none | 0 | 0 | AI-CRM Next and the experiments mirror runtime source have zero textual hits. |
| `rg "openclaw_service" legacy_flask wecom_ability_service` | 7 | `legacy_flask/openclaw_legacy` archive metadata and D9.4 shim notes | 0 | 0 | Legacy archive references are expected; `wecom_ability_service` had no hit in this scan. |
| `rg "openclaw_service" tools tests` | 240 | D9 checkers/tests, shim import smoke, synthetic blocker tests, historical negative assertions | 0 | non-D9 historical tests should remain static-only references | Tool and test hits are static checks or test fixtures; no operational tool dependency was found. |
| `rg "openclaw_service" docs scripts deploy .github` | 258 | D8/D9 retirement docs, archive notes, planning docs, historical inventories | 0 | historical docs, refactor notes, and runbook-like docs require final classification before a deletion PR | Separate targeted scans found zero hits in `deploy/`, `.github/`, and `scripts/`. |
| `rg "legacy_flask.openclaw_legacy" .` | 17 | compatibility shim, D9 docs, D9 checkers/tests | 0 | 0 | Archive package references are expected and do not make the archive a production owner. |

## Targeted Production/Deploy Scan

| scan_command | result_count | allowed_hits | blocked_hits | needs_manual_review_hits | evidence_summary |
| --- | ---: | --- | --- | --- | --- |
| `rg "openclaw_service" deploy .github` | 0 | none | 0 | 0 | No deployment workflow or GitHub workflow reference was found. |
| `rg "openclaw_service" scripts` | 0 | none | 0 | 0 | No scripts reference was found. |

## AST Runtime Import Evidence

| source_root | openclaw_service_import_hits | blocked_hits | evidence_summary |
| --- | ---: | ---: | --- |
| `aicrm_next/` | 0 | 0 | No Python AST import from `openclaw_service` exists in Next runtime source. |
| `experiments/ai_crm_next/src/aicrm_next/` | 0 | 0 | No Python AST import from `openclaw_service` exists in the experiments mirror runtime source. |

## Decision

- Reference scan status: `completed`.
- Observation status: `pending_observation_evidence`.
- Deletion PR candidate: false.

The repository scan supports planning acceptance, but it does not provide operational observation-window evidence. A future deletion proposal still needs production-like log evidence, runtime shim hit counts, D7.7 adapter workload evidence, rollback signoff, and human approval.
