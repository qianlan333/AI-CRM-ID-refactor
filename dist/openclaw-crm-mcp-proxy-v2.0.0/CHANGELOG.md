# Changelog

## 2.0.0 - 2026-03-25

### Breaking change

- 运行形态从“本地完整 CRM 服务包”切换为“薄 MCP 代理包”
- OpenClaw 本地不再运行 CRM 服务副本
- OpenClaw 本地不再持有数据库和企业微信配置

### What this version does

- 本地只暴露 `/health` 和 `/mcp`
- 所有 MCP 请求都转发到远端 CRM 服务器
- 工具名保持不变，上层调用无感
- 推荐 OpenClaw 通过远端工具 `get_owner_recent_chat_dump` 读取真实聊天上下文

### Required configuration

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

### Deprecated path

- 旧的 `1.x` 本地完整 CRM 服务包不再推荐继续使用
- OpenClaw 本地库模式彻底废弃
