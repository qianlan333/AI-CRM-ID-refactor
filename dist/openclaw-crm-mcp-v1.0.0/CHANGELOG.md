# Changelog

## 1.0.0 - 2026-03-25

### Included MCP tools

- `resolve_customer`
- `get_customer_context`
- `get_contact`
- `get_recent_messages`
- `update_customer_tags`
- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`
- `get_hourly_followup_candidates`

### What this version does

- 支持 `customer_ref` 作为手机号或 `external_userid`
- 在 MCP 层复用已有 CRM 的手机号解析能力
- 任务类工具默认 `dry_run=true`
- `get_customer_context` 兼容现网 legacy timeline 调用签名

### Current boundaries

- 不改 CRM 主服务接口能力
- 不引入 scheduler
- 不做复杂平台层封装
- 不做 UI

### Known limitations

- 当前包仍基于现有 Flask 服务源码运行，不是单独抽离的独立微服务实现
- `get_customer_context` 在现网 legacy timeline 路径下会返回兼容性 warning，这属于已知兼容提示，不影响工具可用
- 如果后续出现 breaking change，必须发布新主版本，不允许在 `1.0.0` 目录内原地覆盖
