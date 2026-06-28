# experiments/ai_crm_next Cleanup Inventory

Generated for Batch 3 cleanup planning on 2026-06-28. This is an inventory only:
no files are deleted, moved, or reclassified by this document.

## Summary

`experiments/ai_crm_next` is still documented as a frozen evidence workspace.
The live runtime package is root `aicrm_next/`, and the experiment README says
tests/tools must import that root package instead of adding another
`experiments/ai_crm_next/src/aicrm_next`.

Current file snapshot:

| Area | Count | Cleanup meaning |
|---|---:|---|
| All tracked files under `experiments/ai_crm_next` | 182 | Evidence workspace total |
| `tests/` Python tests, excluding fixtures | 42 | Experiment-local active regression coverage |
| `tests/fixtures/**/*.json` | 25 | Parity fixture data used by experiment-local tests |
| `tools/*.py` | 24 | Experiment-local parity, smoke, readiness, and report tooling |
| `docs/*.md` | 81 | Mostly gray/canary/signoff/runbook evidence |
| `migrations/**/*.py` | 3 | Experiment-local Alembic scaffold and PostgreSQL readiness migrations |

Root repo references are narrow:

- `README.md` documents how to run the experiment-local test environment.
- `scripts/check_no_duplicate_next_source.sh` blocks a duplicate
  `experiments/ai_crm_next/src/aicrm_next` package.
- `tests/test_next_source_consolidation.py` covers that duplicate-source guard.
- `tests/test_ci_workflow_contract.py` asserts the duplicate-source guard is not
  part of the PR smoke block.
- No GitHub workflow currently runs the experiment-local tests/tools directly.

## Active Keep Candidates

Keep these until a follow-up PR either ports the coverage to root tests/tools or
explicitly retires the frozen evidence workspace:

- Experiment harness:
  `experiments/ai_crm_next/README.md`,
  `experiments/ai_crm_next/pyproject.toml`,
  `experiments/ai_crm_next/alembic.ini`,
  `experiments/ai_crm_next/scripts/run_postgres_integration_tests.sh`,
  `experiments/ai_crm_next/migrations/**`.
- Experiment tests and fixtures:
  `experiments/ai_crm_next/tests/**`, including parity fixtures under
  `experiments/ai_crm_next/tests/fixtures/**`.
- Root duplicate-source guard:
  `scripts/check_no_duplicate_next_source.sh` and
  `tests/test_next_source_consolidation.py`.

Test-covered experiment tools:

- `experiments/ai_crm_next/tools/capture_frontend_screenshots.py`
- `experiments/ai_crm_next/tools/check_batch_1_media_canary_readiness.py`
- `experiments/ai_crm_next/tools/check_batch_1_media_production_signoff_readiness.py`
- `experiments/ai_crm_next/tools/check_batch_2_product_canary_readiness.py`
- `experiments/ai_crm_next/tools/check_batch_3_customer_canary_readiness.py`
- `experiments/ai_crm_next/tools/check_batch_4_user_ops_canary_readiness.py`
- `experiments/ai_crm_next/tools/check_batch_5_questionnaire_canary_readiness.py`
- `experiments/ai_crm_next/tools/check_production_canary_approval_package.py`
- `experiments/ai_crm_next/tools/compare_commerce_parity.py`
- `experiments/ai_crm_next/tools/compare_customer_read_model_parity.py`
- `experiments/ai_crm_next/tools/compare_media_library_parity.py`
- `experiments/ai_crm_next/tools/compare_questionnaire_parity.py`
- `experiments/ai_crm_next/tools/compare_user_ops_parity.py`
- `experiments/ai_crm_next/tools/customer_read_model_gray_smoke.py`
- `experiments/ai_crm_next/tools/generate_gray_release_report.py`
- `experiments/ai_crm_next/tools/media_library_gray_smoke.py`
- `experiments/ai_crm_next/tools/product_management_gray_smoke.py`
- `experiments/ai_crm_next/tools/questionnaire_readonly_gray_smoke.py`
- `experiments/ai_crm_next/tools/readonly_http_dual_run.py`
- `experiments/ai_crm_next/tools/run_gray_rehearsal_batch.py`
- `experiments/ai_crm_next/tools/seed_old_flask_customer_sample.py`
- `experiments/ai_crm_next/tools/seed_old_flask_questionnaire_sample.py`
- `experiments/ai_crm_next/tools/user_ops_readonly_gray_smoke.py`

`experiments/ai_crm_next/tools/_root_tool_wrapper.py` has no direct test import
but is infrastructure for running experiment tools against root `aicrm_next/`;
keep it with the tool set until the tool set is retired or moved.

## Archive Candidates

These look like historical gray/canary evidence rather than live runtime input.
They should be moved to an archive path before deletion is considered:

- Batch-specific readonly canary bundles:
  `experiments/ai_crm_next/docs/batch_1_*`,
  `experiments/ai_crm_next/docs/batch_2_*`,
  `experiments/ai_crm_next/docs/batch_3_*`,
  `experiments/ai_crm_next/docs/batch_4_*`,
  `experiments/ai_crm_next/docs/batch_5_*`.
- Gray/canary orchestration and signoff docs:
  `experiments/ai_crm_next/docs/gray_*`,
  `experiments/ai_crm_next/docs/production_canary_*`,
  `experiments/ai_crm_next/docs/route_level_gray_release_*`,
  `experiments/ai_crm_next/docs/route_level_proxy_template.md`,
  `experiments/ai_crm_next/docs/staging_canary_topology.md`.
- Historical execution reports and evidence summaries:
  `experiments/ai_crm_next/docs/*_execution_report.md`,
  `experiments/ai_crm_next/docs/*_signoff*.md`,
  `experiments/ai_crm_next/docs/real_postgres_integration_run.md`,
  `experiments/ai_crm_next/docs/real_readonly_http_dual_run.md`.
- Migration-era strategy docs that are not root architecture sources:
  `experiments/ai_crm_next/docs/migration_strategy.md`,
  `experiments/ai_crm_next/docs/production_replacement_route.md`,
  `experiments/ai_crm_next/docs/remaining_work_queue.md`,
  `experiments/ai_crm_next/docs/risk_register.md`,
  `experiments/ai_crm_next/docs/final_gap_analysis.md`,
  `experiments/ai_crm_next/docs/module_status_matrix.md`.

Do not archive these docs blindly if a test reads them. Several experiment tests
assert safety wording in docs such as frontend parity, fast readonly replacement,
gray release, production canary approval, and route-level runbook files. A safe
archive PR must either keep those tests with updated paths or retire the tests in
the same PR.

## Proposed Follow-up Sequence

1. Decide whether experiment-local tests are still valuable as frozen regression
   coverage. If yes, keep the harness and only archive stale evidence docs.
2. For docs read by tests, update tests and paths in the same PR that moves the
   docs to `docs/archive/experiments_ai_crm_next/`.
3. Port any still-useful tools from `experiments/ai_crm_next/tools/` to root
   `tools/` only when they are still used in current AI-CRM Next operations.
4. After docs/tools are archived or ported, revisit fixtures and experiment
   migrations; do not delete fixtures while parity tests still import them.
5. Keep `scripts/check_no_duplicate_next_source.sh` until the whole
   `experiments/ai_crm_next` directory is removed or permanently archived.

## Non-goals

- No runtime code changes.
- No movement or deletion in this batch.
- No production data access, deploy config change, or external call.
- No claim that archived evidence is production canary evidence.
