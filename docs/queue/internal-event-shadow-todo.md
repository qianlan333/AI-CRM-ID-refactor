# Internal Event Shadow TODO

## ai_campaign.created

P0-2D adds shadow internal events for Cloud Campaign approve/start command
handlers in `aicrm_next/cloud_orchestrator/campaigns_write.py`.

This module currently exposes status/step write commands such as approve,
reject, start, pause, delete, and step mutations. It does not expose a mature
create-campaign command handler in this write path. Do not invent a create path
for `ai_campaign.created`.

When a real create-campaign write command lands, emit:

- `event_type`: `ai_campaign.created`
- `aggregate_type`: `ai_campaign`
- `aggregate_id`: campaign code
- `idempotency_key`: stable create command key
- consumers: `ai_assist_notify_consumer`, `campaign_summary_consumer`,
  `broadcast_task_planner_consumer`
