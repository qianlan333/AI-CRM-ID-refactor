# Production Test Runbook

这条路径不依赖 SSH 写权限或 PG 写用户。生产验证优先走真实后台登录态 Admin API。

## 约束

- 测试 package 使用 `prod_verify_` 前缀。
- 测试 external_userid 只允许 `wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ`。
- 如执行真实私信，sender 只允许 `HuangYouCan`。
- 不输出 DSN、token、secret。
- 测试结束 archive 所有 `prod_verify_*` package。

## 创建测试包

```bash
AICRM_ADMIN_SESSION_COOKIE='...' \
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md \
  --api-base https://www.youcangogogo.com \
  --admin-session-cookie-from-env \
  --package-key-prefix prod_verify_ \
  --apply \
  --confirm-production \
  --operator prod-test
```

默认不 publish、不 activate。需要发布时增加 `--publish`。

## 验证点

- Package create/PATCH/preview/publish 通过 Admin API。
- Members API 只返回 `nickname/external_userid/entered_at`。
- Webhook GET 不返回 secret 明文。
- Outbound job body 只有 `external_userid[]`。
- User Ops preview/execute 只调用标准 batch-send 端口。
- 清理时通过 `DELETE /api/admin/ai-audience/packages/{id}` archive。
