# Test Governance Migration

## Goal

Keep high-risk delivery safety while reducing the amount of test-routing metadata
that must change with ordinary product code. The current
`docs/ci/test_scope_manifest.yml` remains the only authoritative selector during
the observation period.

The migration is intentionally additive: it does not claim an immediate
repository-line reduction while both selectors coexist. Stage 2 adds a weekly,
read-only observation workflow that aggregates unique pull-request evidence and
builds a duplicate/slow-test review queue. The actual deletion of the legacy
selector, large manifest, and redundant tests belongs to the separately approved
cutover stage.

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
safety fallbacks, and whether the candidate would avoid a full regression. The
weekly `Test Governance Observability` workflow downloads retained reports,
de-duplicates repeated commits by pull-request number, and evaluates the
repository-owned thresholds in `docs/ci/test_scope_policy.yml`.

Cutover requires a separate, explicitly approved change after all of these are
true in `AI-CRM-ID-refactor`:

1. At least 20 unique pull requests and 14 days of shadow evidence exist.
2. The evidence contains at least eight scoped and five high-risk pull requests,
   so a high-risk-only burst cannot qualify the selector.
3. No high-risk change is classified below full regression, and no normal-path
   sample relies on an unclassified or no-test-match safety fallback. A fallback
   on an already high-risk sample is reported but does not weaken its full gate.
4. Every legacy-only test is explicitly recorded in
   `docs/ci/test_scope_legacy_only_review.yml` as either included by the
   candidate or intentional legacy overcoverage.
5. The generated report says `automated_ready_for_explicit_cutover_review=true`,
   an explicit human approval is given, and the old selector remains available
   for a one-commit rollback.

Nothing in this stage ports the policy to `qianlan333/AI-CRM` or deploys it to
production. Those remain separate confirmation points.

## Duplicate and slow-test audit

`scripts/ci/audit_test_inventory.py` parses pytest source without importing the
application. It reports overwritten duplicate definitions, exact duplicate-body
candidates above a minimum AST size, slow files from the duration baseline,
oversized files, and baseline paths that are missing or retired. The report is a
review queue only: it never deletes a test or changes CI routing. Similar-looking
tests are kept until their fixtures, assertions, and protected risk are reviewed.

## Duration baseline

The checked-in baseline was refreshed from successful main run `29566083427`,
covering 613 files and 3,906 items. The inventory report exposes newly added or
retired files until the next successful baseline refresh lands.

The scheduled full regression aggregates all eight JUnit artifacts and rebuilds
`docs/ci/pytest_duration_baseline.json`. If the baseline changes, automation first
pushes a dedicated branch and then opens or updates a draft pull request; it never
writes directly to `main`. If repository token policy blocks pull-request
creation, the workflow remains green and publishes a manual compare link in its
summary. Baseline publication is best-effort and cannot turn an otherwise
successful regression red.
