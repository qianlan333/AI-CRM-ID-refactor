# Send Content Next-Native Backend

The standard send content backend lives in `aicrm_next/send_content` and follows the Next layering pattern:

- `dto.py`: request and content package DTOs.
- `application.py`: normalization, preview, and material picker use cases.
- `repo.py`: fixture repository and repository selection.
- `postgres_repo.py`: production PostgreSQL adapter through the Next media library repository.
- `api.py`: FastAPI routes returning JSON errors.

The router is registered in `aicrm_next/main.py` before `frontend_compat_router`.

The preview flow is side-effect free. It only reads local material libraries, and it does not upload to WeCom, resolve WeCom `media_id`, create `add_msg_template`, write send records, or change real sending logic.

Production mode uses PostgreSQL-backed repositories. If production data is unavailable, the API returns degraded `production_unavailable` JSON rather than fixture success. Fixture data is only for non-production local contract mode.

Automation task write APIs stay in `aicrm_next/automation_engine`. They persist standard content under:

```json
{
  "config": {
    "operation_content": {
      "content_mode": "unified",
      "profile_segment_template_id": 0,
      "unified_content_json": {},
      "segment_contents_json": [],
      "agent_config_json": {}
    }
  }
}
```

These APIs do not modify task trigger, audience, send time, status, external sending, timers, or WeCom outbound execution.

