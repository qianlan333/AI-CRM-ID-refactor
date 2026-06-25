# AI Audience 人群包

AI Audience 用 Markdown spec 和受控 Admin API 创建、校验、发布 SQL 人群包。它不恢复旧 automation program / Runtime V2，也不新增私信群发发送器。

## 创建流程

1. 按 `package_spec.md` 编写 Markdown spec。
2. 本地 dry-run：
   `python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md --dry-run`
3. 通过后台 session 调用 Admin API 创建或更新 package/version。
4. preview 校验 sample rows 和 SQL 依赖。
5. 需要上线时 publish，然后在后台手动 activate。

## 权限边界

- `/api/admin/ai-audience/*` 只接受 admin session。
- `/api/ai/audience/*` 只接受 internal token，不能给浏览器调用。
- API 不返回 SQL、inbound secret、outbound signing secret、payload 明细或成员隐私字段。

## 群发边界

一键群发只复用 User Ops 标准 batch-send：

- `POST /api/admin/user-ops/batch-send/preview`
- `POST /api/admin/user-ops/batch-send/execute`

AI Audience 只通过 `target_source=ai_audience_package` 提供标准 target rows。发送人由 package sender whitelist 解析，禁止默认兜底。
