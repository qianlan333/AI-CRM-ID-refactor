# Route-Level Proxy Template

This file is a template only. It must not be applied directly to production. It contains no production hostnames, secrets, or deploy paths.

## App-Level Flags

```bash
# PSEUDO ONLY - do not apply directly
AICRM_NEXT_ROUTE_MEDIA_READONLY=true
AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false
```

## Media Library Example

```nginx
# PSEUDO ONLY - do not apply directly
location /admin/image-library {
    proxy_pass http://aicrm_next;
}

# PSEUDO ONLY - do not apply directly
location /api/admin/image-library {
    proxy_pass http://aicrm_next;
}
```

## Product Management Example

```nginx
# PSEUDO ONLY - do not apply directly
location /admin/wechat-pay/products {
    proxy_pass http://aicrm_next;
}

# PSEUDO ONLY - do not apply directly
location /api/admin/wechat-pay/products {
    proxy_pass http://aicrm_next;
}
```

Checkout and payment notify paths must remain on old Flask until real provider adapter validation is approved.

## Customer Readonly Example

```nginx
# PSEUDO ONLY - do not apply directly
location /admin/customers {
    proxy_pass http://aicrm_next;
}

# PSEUDO ONLY - do not apply directly
location /api/customers {
    proxy_pass http://aicrm_next;
}
```

## User Ops Readonly Example

```nginx
# PSEUDO ONLY - do not apply directly
location /admin/user-ops/ui {
    proxy_pass http://aicrm_next;
}

# PSEUDO ONLY - do not apply directly
location /api/admin/user-ops/overview {
    proxy_pass http://aicrm_next;
}
```

DND, batch-send, deferred jobs, and internal write routes must stay disabled for Next route cutover in readonly gray.

## Questionnaire Readonly Example

```nginx
# PSEUDO ONLY - do not apply directly
location /admin/questionnaires {
    proxy_pass http://aicrm_next;
}

# PSEUDO ONLY - do not apply directly
location /api/h5/questionnaires {
    proxy_pass http://aicrm_next;
}
```

Submit, OAuth callback, and external push routes are excluded from readonly gray.

## Automation Readonly Example

```nginx
# PSEUDO ONLY - do not apply directly
location /admin/automation-conversion {
    proxy_pass http://aicrm_next;
}

# PSEUDO ONLY - do not apply directly
location /api/admin/automation-conversion/overview {
    proxy_pass http://aicrm_next;
}
```

Manual override, activation webhook, OpenClaw push, workflow runtime, and agent runtime are excluded from readonly gray.
