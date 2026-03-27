# OpenClaw CRM MCP Proxy v2.0.1 README Folder

这个文件夹是 `openclaw-crm-mcp-proxy-v2.0.1` 的完整说明集，适合直接发给产品、运营、运维或接入同学。

## 你应该先看哪一份

- `01_overview.md`
  - 先理解这是什么、为什么要这样做
- `02_capabilities.md`
  - 看这版到底能干什么
- `03_install.md`
  - 看怎么安装和升级
- `04_configuration.md`
  - 看怎么配 `CRM_MCP_URL` 和 `MCP_BEARER_TOKEN`
- `05_tool_catalog.md`
  - 看所有 MCP 工具能力清单
- `06_faq.md`
  - 看常见疑问和边界

## 一句话总结

这版不是本地 CRM，而是 OpenClaw 的 CRM MCP 薄代理。

OpenClaw 本地只起一个小代理服务，把所有 `/mcp` 请求转发到 CRM 主服务真实在线的 `/mcp`，因此 OpenClaw 本地不再需要数据库、企业微信配置和 CRM 全量源码。
