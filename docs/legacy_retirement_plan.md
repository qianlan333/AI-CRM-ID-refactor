# Legacy Retirement Plan

AI-CRM default runtime has moved to AI-CRM Next. Legacy Flask remains as a fallback until production evidence allows deletion.

## Current State

- `python3 app.py run` starts AI-CRM Next.
- `python3 app.py run-legacy` starts legacy Flask.
- `wecom_ability_service/` and `openclaw_service/` are frozen, not deleted.
- Production traffic cutover is not executed by this plan.
- D1 Media Library old Flask route modules are retired/deleted. AI-CRM Next owns Media Library route handling by default.

## Retirement Principles

- Delete only after production route evidence exists.
- Keep rollback possible until the relevant batch is signed off.
- Do not delete write or external adapter code until real replacement and rollback evidence exist.
- Do not mix multiple delete batches in one PR.

## Rollback Conditions

- Route smoke fails.
- Old fallback route is needed for recovery.
- External adapter behavior is not fully replaced.
- Data migration evidence is incomplete.

## Required Evidence Before Deletion

- Production canary or replacement evidence for the target route family.
- Latest smoke and parity report.
- Route owner proof.
- Rollback proof.
- Human signoff.

This document tracks the retirement plan and completed delete batches. It does not authorize deletion outside the explicitly completed batch list below.

## Completed Delete Batches

### D1: Media Library Old Routes

Deleted files:

- `wecom_ability_service/http/image_library_endpoint.py`
- `wecom_ability_service/http/image_library_create.py`
- `wecom_ability_service/http/attachment_library_endpoint.py`
- `wecom_ability_service/http/miniprogram_library_endpoint.py`

The legacy HTTP registrar no longer imports or registers these modules. Rollback is `git revert` of the D1 PR or restoring a pre-D1 fallback tag. D2 Product old routes have not started.
