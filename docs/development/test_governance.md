# Test Governance Migration

## Goal

Keep high-risk delivery safety while reducing the amount of test-routing metadata
that must change with ordinary product code. The current
`docs/ci/test_scope_manifest.yml` remains the only authoritative selector during
the observation period.

This first stage is intentionally additive: it does not claim an immediate CI
time or repository-line reduction while both selectors coexist. Its immediate
benefits are measurable routing evidence, a current duration baseline, and fewer
route-count maintenance edits. The actual deletion of the legacy selector,
large manifest, and their redundant contract tests belongs to the separately
approved cutover stage.

## Architecture boundary

- Capability owner: CI and test governance.
- Routes: none.
- Runtime owner: build-time tooling only; no Next or legacy runtime route changes.
- External calls and production data: none. Contract tests continue to forbid real
  external effects.
- Checker change: `scripts/ci/select_test_scope_v2.py` adds an observational
  selector and parity report.
- Rollback: remove the shadow step and its policy. The existing selector remains
  untouched and authoritative throughout the trial.

## Candidate selection rules

The candidate selector derives a context from `aicrm_next/<context>/...`, then
finds tests through module/path references and test-name conventions. Direct test
changes select the changed test itself. Unclassified runtime paths, deleted files,
or runtime files with no matching test fall back to full regression.

Only exceptions live in `docs/ci/test_scope_policy.yml`:

- authentication;
- payment, refund, and entitlement writes;
- WeCom callbacks and real external-effect boundaries;
- questionnaire and durable group-operation writes;
- migrations, deploy/runtime transactions, dependency files, and global
  architecture contracts.

Those categories continue to require the full architecture gate and full
regression. Ordinary read-only, local-context, and UI-adjacent changes are the
intended candidates for a small context slice plus the fast architecture gate.

## Pytest conventions

New or materially rewritten tests should use strict registered markers:

- `unit`: isolated logic with no database or external process;
- `postgres`: requires the migrated PostgreSQL test schema;
- `high_risk`: protects an approved high-risk business or delivery boundary;
- `slow`: intentionally expensive and suitable for the full/nightly suite.

Existing tests do not need a bulk marker-only rewrite. Markers should be added
when a test is already being changed, so governance does not create a large,
low-signal migration diff.

The first cleanup also removes aggregate router/route cardinality assertions and
one redundant manifest-count test. The remaining contracts validate unique route
groups, complete route ownership, static catch-all ordering, and executable route
policy lookup, so a legitimate new route no longer requires unrelated count
updates.

## Observation and cutover

Every CI Fast run writes a v2 comparison to the job summary and uploads the JSON
report. The report records the legacy and candidate test sets, high-risk reasons,
safety fallbacks, and whether the candidate would avoid a full regression.

Cutover requires a separate, explicitly approved change after all of these are
true in `AI-CRM`:

1. At least 20 representative pull-request runs have shadow evidence.
2. No high-risk change is classified below full regression.
3. No unclassified or no-test-match fallback remains for normal development
   paths.
4. Every removed legacy-only test is reviewed as intentional rather than missed
   coverage.
5. The old selector remains available for a one-commit rollback.

This stage is ported to `qianlan333/AI-CRM` only as shadow tooling. The existing
selector remains authoritative; this does not approve the cutover stage or alter
any business runtime behavior.

## Duration baseline

The previous baseline covered 481 files and 2,843 items. This migration refreshes
it from successful AI-CRM main run `29553412086`, covering 585 files and 3,634
items, so new shards no longer fall back to an outdated per-item estimate for
104 files.

The scheduled full regression aggregates all eight JUnit artifacts and rebuilds
`docs/ci/pytest_duration_baseline.json`. If the baseline changes, automation opens
or updates a draft pull request; it never writes directly to `main`. Baseline
publication is best-effort and cannot turn an otherwise successful regression
red.
