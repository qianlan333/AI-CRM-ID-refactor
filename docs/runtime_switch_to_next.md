# Runtime Switch To AI-CRM Next

AI-CRM now defaults to the FastAPI modular monolith in `aicrm_next/`.

## Current Default

```bash
python3 app.py run
```

starts:

```text
aicrm_next.main:app
```

The default host is `127.0.0.1`. The default port is `5001`, unless `APP_PORT` is set.

## Legacy Fallback

Legacy Flask remains available for rollback and comparison only:

```bash
python3 app.py run-legacy
python3 legacy_flask_app.py run
```

Legacy database initialization is explicit:

```bash
python3 app.py init-db-legacy
python3 legacy_flask_app.py init-db
```

`python3 app.py init-db` remains as a deprecated legacy alias for existing deployment scripts. It still loads legacy Flask only after that command is explicitly selected.

## Route Owner Confirmation

AI-CRM Next responses set:

```text
X-AICRM-Route-Owner: ai_crm_next
X-AICRM-App: ai_crm_next
```

Legacy Flask responses set:

```text
X-AICRM-Route-Owner: legacy_flask
X-AICRM-App: ai_crm_legacy_flask
```

## Rollback To Legacy

Rollback is an operator decision. Do not change production Nginx or systemd from this repository change alone.

Local fallback command:

```bash
python3 app.py run-legacy
```

If production rollback is approved separately, restore the service command to the legacy runner and verify the old route owner header.

## Production Preconditions

- Human signoff completed.
- Production config diff reviewed.
- Nginx/systemd change approved separately.
- Latest smoke and parity evidence attached.
- Rollback owner online.
- External adapters remain disabled unless separately approved.

## Forbidden In This Switch

- No production traffic cutover is executed by this document.
- No production Nginx or deploy config is modified here.
- No WeCom, OAuth, Payment, OpenClaw, cloud, workflow, or webhook provider is enabled here.
- No module is marked `production_ready`.
- No canary is marked `production_approved`.
