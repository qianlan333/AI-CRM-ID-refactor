# Batch 6 Automation Readonly Proxy Pseudo Config

Every example in this file is PSEUDO ONLY. Do not apply directly to production. The examples do not contain production hosts or secrets.

## Route Flags

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=true
AICRM_NEXT_ROUTE_AUTOMATION_WRITES=false
AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK=false
AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME=false
AICRM_NEXT_AUTOMATION_AGENT_RUNTIME=false
AICRM_NEXT_EXTERNAL_OPENCLAW=false
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false
AICRM_NEXT_EXTERNAL_WEBHOOK=false
```

Rollback:

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false
```

## Header Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/automation-conversion {
    if ($http_x_aicrm_next_canary = "automation-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/automation-conversion/overview {
    if ($http_x_aicrm_next_canary = "automation-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/automation-conversion/pools {
    if ($http_x_aicrm_next_canary = "automation-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/automation-conversion/members {
    if ($http_x_aicrm_next_canary = "automation-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/automation-conversion/execution-records {
    if ($http_x_aicrm_next_canary = "automation-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Excluded Write And External Routes

```nginx
# PSEUDO ONLY - manual override excluded from Batch 6, do not apply to production
location /api/admin/automation-conversion/manual-write-placeholder {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - activation webhook excluded from Batch 6, do not apply to production
location /api/customer-automation/activation-webhook {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - OpenClaw push excluded from Batch 6, do not apply to production
location /api/admin/automation-conversion/openclaw-placeholder {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - workflow and agent runtime excluded from Batch 6, do not apply to production
location /api/admin/automation-conversion/runtime-placeholder {
    proxy_pass http://old_flask_staging;
}
```

## Safety

- PSEUDO ONLY examples.
- Staging router only.
- No production host.
- No secrets.
- No manual override.
- No confirm conversion.
- No activation webhook.
- No OpenClaw push.
- No workflow runtime or agent runtime.
- No real WeCom dispatch.
- No external webhook.
