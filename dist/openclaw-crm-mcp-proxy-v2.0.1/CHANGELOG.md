# Changelog

## 2.0.1 - 2026-03-26

### Delivery refresh

- 重新产出干净的 `v2.0.1` 薄代理包
- 去掉 `v2.0.0` 目录里的本地验证残留
- 在文档和清单里补充 `get_owner_recent_chat_dump`
- 把远端 `CRM_MCP_URL` 示例更新为可达的公网 HTTPS 地址

### Package behavior

- 本地只暴露 `/health` 和 `/mcp`
- 所有 MCP 请求都转发到远端 CRM 服务器
- 工具名保持不变，上层调用无感

### Required configuration

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

### Deprecated path

- 旧的 `1.x` 本地完整 CRM 服务包不再推荐继续使用
