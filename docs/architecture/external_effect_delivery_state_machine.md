# External effect delivery state machine

`external_effect_job` is the canonical queue for real external side effects. Scheduler,
realtime callback, and manual execution all enter the same durable claim boundary.

## Claim and lease

- Scheduler claims only due `queued` or `failed_retryable` jobs.
- Scheduler scans honor `scheduled_at` and retry backoff. An explicit trusted
  `dispatch_one(job_id)` may claim a queued/retryable job early, but uses the same
  lease-token/CAS result boundary.
- A claim atomically changes the job to `dispatching` and assigns a unique
  `lease_token` plus `lease_expires_at`.
- Result persistence compares both `status = dispatching` and the lease token.
  A worker that lost its lease writes neither an attempt nor a job result.
- Expired `dispatching` jobs are quarantined as `unknown_after_dispatch`. They are
  never automatically requeued because the former worker may have reached the provider.

## Truthful terminal states

| State | Required evidence | Automatic retry |
| --- | --- | --- |
| `succeeded` | A real side effect executed and an accepted provider response or receipt was persisted | No |
| `simulated` | A fake/fixture adapter completed without a real external call | No |
| `blocked` | Policy, allowlist, kill switch, or validation prevented the provider call | No |
| `failed_retryable` | The provider returned a definite response that is safe to retry | Yes, when due |
| `failed_terminal` | A definite non-retryable provider or payload failure | No |
| `unknown_after_dispatch` | Dispatch started but the provider outcome or result persistence is uncertain | Never |

An adapter may not turn `side_effect_executed = false` into `succeeded`. Fake success
is `simulated`; a claimed success without real execution is `blocked`. A real call
without provider evidence is `unknown_after_dispatch`.

The attempt row and final job transition are committed in one transaction. A
successful provider call followed by an unpersisted result is quarantined as unknown,
not retried as if no call occurred.

## Manual recovery

`unknown_after_dispatch` requires provider-side reconciliation. Manual retry requires
an actor, a reason, and an explicit `confirm_duplicate_risk = true` acknowledgement.
The authorization is appended to `external_effect_attempt` before the job is queued.

## Broadcast fake adapters

Fake WeCom private/group broadcast responses use `simulated` in `broadcast_jobs`,
`outbound_tasks`, and cloud-plan recipient/message projections. They never set `sent`,
increment `sent_count`, or populate `sent_at`.
