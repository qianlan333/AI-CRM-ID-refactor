# 06 FAQ

## Q1：这版是不是一个 CRM 服务？

不是。

它只是 OpenClaw 本地的 CRM MCP 代理。

## Q2：OpenClaw 本地还需要数据库吗？

不需要。

## Q3：OpenClaw 本地还需要企业微信配置吗？

不需要。

## Q4：为什么旧版会查到空会话？

因为旧版是本地完整服务路线，而 OpenClaw 本地没有真实 CRM 数据。

## Q5：这版为什么不会再出现“空库”问题？

因为这版所有请求都转发到 CRM 主服务真实 `/mcp`，数据源不在 OpenClaw 本地。

## Q6：群发能力还在吗？

在。

只要远端 CRM 主服务还暴露这些工具，就能继续用：

- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`

## Q7：最近聊天 dump 能查到真实数据吗？

可以。

前提是远端 CRM 主服务的 `get_owner_recent_chat_dump` 正常在线，而当前已确认它在线可用。

## Q8：以后 OpenClaw 还需要装完整 CRM 吗？

不需要。

新的主线就是薄代理模式。

## Q9：如果远端 CRM 新增工具，这个代理包要不要改？

通常不需要。

只要代理仍然把 `/mcp` 原样转发，新的工具会自动通过远端 `tools/list` 暴露出来。

## Q10：如果远端 CRM 地址变化怎么办？

只改 `.env` 里的 `CRM_MCP_URL` 即可，不需要重做本地 CRM 服务。
