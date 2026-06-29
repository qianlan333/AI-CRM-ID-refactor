# experiments/ai_crm_next Cleanup Inventory

Generated: 2026-06-29

## Scope

`experiments/ai_crm_next` is a frozen evidence workspace. The live runtime package
is root `aicrm_next/`; this inventory does not delete or move experiment files.

This pass only classifies files for later cleanup:

- keep while referenced by root docs, scripts, tests, or CI;
- keep as experiment-local regression tooling while the frozen workspace remains;
- archive historical canary, gray-release, rehearsal, signoff, and execution
  evidence under `docs/archive/experiments_ai_crm_next/` in a later PR;
- do not introduce `experiments/ai_crm_next/src/aicrm_next`.

## Top-Level Counts

| area | tracked files | current classification |
|---|---:|---|
| root experiment config (`README.md`, `.gitignore`, `pyproject.toml`, `alembic.ini`) | 4 | active reference |
| `migrations/**/*.py` | 3 | experiment-local Alembic scaffold and PostgreSQL readiness migrations |
| `scripts/` | 1 | experiment-local test helper |
| `tools/` | 24 | experiment-local regression / evidence tooling |
| `tests/` Python tests, excluding fixtures | 42 | experiment-local active regression coverage |
| `tests/fixtures/**/*.json` | 25 | parity fixture data used by experiment-local tests |
| `docs/` | 81 | mixed: reference docs plus archive candidates |
| all tracked files under `experiments/ai_crm_next` | 182 | evidence workspace total |

## Root References

Current root-level references found outside `experiments/ai_crm_next`:

| root file | reference | classification |
|---|---|---|
| `README.md` | documents how to run the experiment test environment | active doc pointer |
| `scripts/check_no_duplicate_next_source.sh` | forbids `experiments/ai_crm_next/src/aicrm_next` | active guard |
| `tests/test_next_source_consolidation.py` | asserts the duplicate-source guard remains present | active guard test |
| `tests/test_ci_workflow_contract.py` | asserts the duplicate-source guard is not part of PR smoke | active CI contract test |

No root CI workflow or root runtime module imports experiment-local source files
as live runtime code.

## Active Experiment-Local Tests

Keep while the experiment workspace remains frozen:

- Contract/parity tests: `test_*_contract.py`, `test_*_parity.py`,
  `test_route_owner_headers.py`, `test_identity_resolution.py`,
  `test_mcp_contract.py`, `test_health.py`.
- SQL / fixture regression tests: `test_*_sql_repo.py`,
  `test_seed_old_flask_*_sample.py`, `test_postgres_test_guard.py`.
- Parity fixture data: `experiments/ai_crm_next/tests/fixtures/**`.
- Gray / canary readiness tests that validate evidence docs:
  `test_batch_*_canary_readiness.py`,
  `test_batch_1_media_production_signoff_readiness.py`,
  `test_gray_rehearsal_batch.py`,
  `test_gray_release_runbook.py`,
  `test_production_canary_approval_package.py`.
- Frontend parity tests that document frozen route expectations:
  `test_frontend_*`.

These tests are not root runtime tests; they are evidence-workspace checks.

## Active Experiment-Local Tools

Keep while their paired tests or docs remain:

- Readiness checkers: `check_batch_*_canary_readiness.py`,
  `check_batch_1_media_production_signoff_readiness.py`,
  `check_production_canary_approval_package.py`.
- Parity comparators: `compare_*_parity.py`.
- Gray / dual-run helpers: `*_gray_smoke.py`, `readonly_http_dual_run.py`,
  `run_gray_rehearsal_batch.py`, `generate_gray_release_report.py`.
- Fixture/screenshot helpers: `seed_old_flask_*_sample.py`,
  `capture_frontend_screenshots.py`.
- `_root_tool_wrapper.py` remains useful as long as experiment tools import the
  root `aicrm_next/` package.

## Reference Docs To Keep For Now

Keep as long as the frozen workspace remains discoverable:

- `experiments/ai_crm_next/README.md`
- `experiments/ai_crm_next/docs/architecture.md`
- `experiments/ai_crm_next/docs/api_contracts.md`
- `experiments/ai_crm_next/docs/feature_parity_matrix.md`
- `experiments/ai_crm_next/docs/final_gap_analysis.md`
- `experiments/ai_crm_next/docs/module_status_matrix.md`
- `experiments/ai_crm_next/docs/migration_strategy.md`
- `experiments/ai_crm_next/docs/postgres_integration_testing.md`
- `experiments/ai_crm_next/docs/remaining_work_queue.md`
- `experiments/ai_crm_next/docs/*_parity_strategy.md`
- `experiments/ai_crm_next/docs/*_route_cutover_manifest.md`
- `experiments/ai_crm_next/docs/*_sample*_checklist.md`
- `experiments/ai_crm_next/docs/frontend_*`
- `experiments/ai_crm_next/docs/readonly_http_dual_run_strategy.md`
- `experiments/ai_crm_next/docs/real_readonly_http_dual_run.md`
- `experiments/ai_crm_next/docs/real_postgres_integration_run.md`

These are still useful for reconstructing migration decisions and parity
criteria, even though they are not live runtime instructions.

## Archive Candidates

These are historical evidence/report families. They should be moved in a later
PR to `docs/archive/experiments_ai_crm_next/` after checking any linked tests are
updated or intentionally retired:

- `experiments/ai_crm_next/docs/batch_*_canary_*`
- `experiments/ai_crm_next/docs/batch_*_proxy_pseudo_config.md`
- `experiments/ai_crm_next/docs/batch_*_route_flags.md`
- `experiments/ai_crm_next/docs/gray_rehearsal_*`
- `experiments/ai_crm_next/docs/gray_release_*`
- `experiments/ai_crm_next/docs/*_gray_release_plan.md`
- `experiments/ai_crm_next/docs/*_canary_*`
- `experiments/ai_crm_next/docs/production_canary_*`
- `experiments/ai_crm_next/docs/route_level_gray_release_*`
- `experiments/ai_crm_next/docs/*_execution_report.md`
- `experiments/ai_crm_next/docs/*_signoff*.md`
- `experiments/ai_crm_next/docs/production_replacement_route.md`
- `experiments/ai_crm_next/docs/risk_register.md`
- `experiments/ai_crm_next/docs/staging_canary_topology.md`
- `experiments/ai_crm_next/docs/go_no_go_checklist.md`
- `experiments/ai_crm_next/docs/fast_readonly_human_test_tasks.md`
- `experiments/ai_crm_next/docs/fast_readonly_replacement_execution_plan.md`

Do not delete these directly. Most are audit/evidence records, not generated
scratch files. Several experiment-local tests assert safety wording in docs such
as frontend parity, fast readonly replacement, gray release, production canary
approval, and route-level runbook files; archive movement must update or retire
those tests in the same PR.

## Cleanup Order Recommendation

1. Keep root duplicate-source guard and README pointer.
2. Decide whether experiment-local readiness/canary tests are still expected to
   run anywhere. If not, archive their paired docs and tools together.
3. Move historical evidence docs to `docs/archive/experiments_ai_crm_next/`.
4. Update `experiments/ai_crm_next/README.md` with a retention rule: keep only
   parity/reference docs and tests that still protect root `aicrm_next/`.
5. Only after inventory-backed archive movement, consider deleting generated
   screenshots or regenerated reports that are not referenced by tests/docs.

## Non-Goals

- No runtime code changes.
- No deploy/nginx/systemd changes.
- No external calls.
- No production data access.
- No deletion of `experiments/ai_crm_next` files in this batch.
