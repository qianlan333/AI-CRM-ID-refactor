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
