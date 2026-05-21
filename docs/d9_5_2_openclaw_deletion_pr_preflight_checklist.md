# D9.5.2 OpenClaw Deletion PR Preflight Checklist

Allowed status values: `pending`, `available`, `needs_manual_review`, `blocked`.

| check_item | required | current_status | evidence | blocker_if_missing | owner | notes |
| --- | --- | --- | --- | --- | --- | --- |
| final reference scan rerun | true | available | D9.5.1 scan evidence | yes | migration owner | rerun before any future deletion PR |
| no runtime imports | true | available | AST scan for `aicrm_next/` and experiments mirror | yes | migration owner | current scan reports zero hits |
| no production log hits | true | pending | production app logs | yes | platform owner | not_available_in_local_environment |
| observation window complete | true | pending | runtime observation record | yes | platform owner | required before PR preparation |
| rollback plan confirmed | true | needs_manual_review | D9.5 rollback plan plus owner signoff | yes | release owner | rollback independence is not yet confirmed |
| human signoff collected | true | pending | approval record | yes | release owner | required before deletion PR |
| deletion PR scope limited to `openclaw_service` shim | true | pending | future PR diff | yes | migration owner | no PR is prepared in this round |
| no production config changes | true | available | dirty diff and checker | yes | release owner | production config remains unchanged |
| D7.7 checker PASS | true | needs_manual_review | D7.7 checker artifact | yes | migration owner | must be rerun at PR time |
| D9.1 checker PASS | true | available | D9.1 checker artifact | yes | migration owner | import freeze remains required |
| D9.4 checker PASS | true | available | D9.4 checker artifact | yes | migration owner | archive/shim state remains required |
| D9.5.1 checker PASS | true | available | D9.5.1 checker artifact | yes | migration owner | current recommendation remains pending observation |

## Current Preflight Decision

- Deletion candidate: false.
- Deletion PR preparation: blocked.
- Reason: observation evidence, rollback independence, workload evidence, and human signoff are pending.
