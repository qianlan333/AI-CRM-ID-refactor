# Legacy Retirement Plan

AI-CRM default runtime has moved to AI-CRM Next. Legacy Flask remains as a fallback until production evidence allows deletion.

## Current State

- `python3 app.py run` starts AI-CRM Next.
- `python3 app.py run-legacy` starts legacy Flask.
- `wecom_ability_service/` and `openclaw_service/` are frozen, not deleted.
- Production traffic cutover is not executed by this plan.

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

This document is a plan only. It does not delete legacy code.
