# Production Test Runbook

这条路径不依赖 SSH 写权限、PG 写用户或浏览器 admin cookie。生产验证优先走 External Spec API Bearer token。

## 约束

- 测试 package 使用 `prod_verify_` 前缀。
- 测试 external_userid 只允许 `wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ`。
- 如执行真实私信，sender 只允许 `HuangYouCan`。
- 不输出 DSN、token、secret。
- 测试结束 archive 所有 `prod_verify_*` package。

## External API 创建测试包

```bash
export AICRM_AI_AUDIENCE_SPEC_API_TOKEN='...'
```

Dry-run：

```bash
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md \
  --external-api-base https://www.youcangogogo.com \
  --external-token-from-env \
  --package-key-prefix prod_verify_ \
  --dry-run
```

Apply：

```bash
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md \
  --external-api-base https://www.youcangogogo.com \
  --external-token-from-env \
  --package-key-prefix prod_verify_ \
  --apply \
  --confirm-production \
  --operator prod-test
```

默认不 publish、不 activate。需要发布时要求生产配置 `AICRM_AI_AUDIENCE_SPEC_ALLOW_PUBLISH=true`，再增加 `--publish`。

Archive：

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $AICRM_AI_AUDIENCE_SPEC_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://www.youcangogogo.com/api/external/ai-audience/packages/prod_verify_q101_submitted_added_wecom/archive \
  -d '{"operator":"prod-test"}'
```

## 验证点

- Package create/update/preview/publish/archive 通过 External Spec API。
- Members API 只返回 `nickname/external_userid/entered_at`。
- Webhook GET 不返回 secret 明文。
- Outbound job body 只有 `external_userid[]`。
- User Ops preview/execute 只调用标准 batch-send 端口。
- 清理时通过 `DELETE /api/admin/ai-audience/packages/{id}` archive。
