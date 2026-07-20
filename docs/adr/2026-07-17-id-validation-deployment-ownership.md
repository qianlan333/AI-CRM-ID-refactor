# ADR: ID-refactor owns the isolated validation deployment

Date: 2026-07-17

## Decision

`qianlan333/AI-CRM-ID-refactor` is the only repository allowed to deploy the
validation runtime at `49.232.57.128` / `id-dev.youcangogogo.com` while the
execution-runtime redesign is being developed and soaked.

The repository has one deployment environment, `id-validation`. A successful
push-triggered `CI Fast` run on `main` is the only workflow event that may
deploy. The workflow rejects a different repository, source repository, host,
environment, or public origin before transferring a release.

The workflow uses only the environment-scoped secrets
`ID_VALIDATION_DEPLOY_HOST`, `ID_VALIDATION_DEPLOY_USER`, and
`ID_VALIDATION_DEPLOY_SSH_KEY`. It has no production target, reusable deploy
entrypoint, manual promotion input, cross-repository token, or credential for
`150.158.82.186`.

## Source and runtime identity

The repository `main` SHA is source provenance, not automatically a new runtime
identity. The deploy workflow computes deterministic runtime and validation tree
digests between the active release and the verified `main` SHA. Only explicitly
non-runtime paths under `.github/`, `docs/`, `scripts/ci/`, `tests/`, and the
small root metadata allowlist are excluded from the runtime digest. Every unknown
path fails closed as runtime-impacting.

When the runtime digest is unchanged and public health proves the active release,
the workflow records a source-only verification in the Actions summary and does
not transfer a bundle, open SSH, change the server checkout, or restart runtime
units. The active release SHA therefore remains the immutable queue-validation
and soak candidate while `main` may advance through runtime-equivalent changes.
Queue Operations accepts that deployed SHA only when it is still an ancestor of
current `main` and exactly matches public health.

Any runtime tree change, unavailable public health, missing ancestry, or unknown
classification follows the existing fail-closed deployment path. Runtime changes
still create a new exact-SHA release and invalidate exact-release validation.

## Provenance and rollback

Every non-noop deployment verifies the exact CI SHA, live base ancestry,
incremental bundle checksum, and server checkout origin. After public health
reports the exact release SHA, it atomically records repository, source CI run,
deploy run, base SHA, release SHA, bundle hash, environment, and deployment
time on the server.

Rollback is another exact-SHA deployment from ID-refactor to the previous
validated release. It never restores AI-CRM's automatic access to id-dev,
shared SSH keys, a legacy runtime, or a schema downgrade.

## Promotion boundary

Validation changes remain in ID-refactor until the user explicitly approves
`PROMOTE <validated_ID_SHA> TO AI-CRM`. ID-only workflow and credential files
are excluded from the promotable application manifest. Promotion to the
AI-CRM repository does not itself authorize any other server deployment.
