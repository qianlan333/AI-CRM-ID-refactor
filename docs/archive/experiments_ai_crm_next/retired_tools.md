# Retired Experiment Tool Wrappers

The frozen `experiments/ai_crm_next` workspace previously contained thin
wrappers that imported same-named scripts from the repository root `tools/`
directory. Those root scripts no longer exist, so the wrappers failed at import
time and no longer represented runnable evidence.

This archive record documents their retirement. The historical markdown reports
under `docs/archive/experiments_ai_crm_next/docs/` still describe what those
commands produced at the time; they are not current runbooks.

Retired wrappers:

- `compare_commerce_parity.py`
- `compare_customer_read_model_parity.py`
- `compare_media_library_parity.py`
- `compare_questionnaire_parity.py`
- `compare_user_ops_parity.py`
- `customer_read_model_gray_smoke.py`
- `media_library_gray_smoke.py`
- `product_management_gray_smoke.py`
- `questionnaire_readonly_gray_smoke.py`
- `run_gray_rehearsal_batch.py`
- `user_ops_readonly_gray_smoke.py`

Retired tests:

- `test_customer_read_model_gray_smoke.py`
- `test_media_library_gray_smoke.py`
- `test_product_management_gray_smoke.py`
- `test_questionnaire_readonly_gray_smoke.py`
- `test_gray_rehearsal_batch.py`
- `test_user_ops_readonly_gray_smoke.py`

Active experiment coverage remains in the parity specs, fixture masking tests,
contract tests, readiness document tests, and architecture gates.
