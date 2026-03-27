# 02 Capabilities

## 代理层能力

这版包自己本身能做的事只有这些：

- 本地提供 `GET /health`
- 本地提供 `POST /mcp`
- 从环境变量读取：
  - `CRM_MCP_URL`
  - `MCP_BEARER_TOKEN`
- 以 Bearer Token 把请求转发到远端 CRM
- 透传远端结果
- 对少量基础错误做包装：
  - 远端不可达
  - 超时
  - 本地缺少必填环境变量

## 通过代理暴露出来的 CRM 能力

这些能力都不在本地实现，而是来自远端 CRM 主服务：

- 客户解析
  - `resolve_customer`

- 客户上下文
  - `get_customer_context`
  - `get_contact`
  - `get_recent_messages`

- 标签管理
  - `update_customer_tags`

- 任务创建
  - `create_private_message_task`
  - `create_group_message_task`
  - `create_moment_task`

- 跟进候选
  - `get_hourly_followup_candidates`

- 最近聊天 dump
  - `get_owner_recent_chat_dump`

## 关键业务结论

这意味着 OpenClaw 现在可以通过这版代理：

- 查客户
- 看客户上下文
- 看最近聊天
- 打标签
- 创建私聊群发
- 创建客户群群发
- 创建朋友圈任务
- 看本小时最该联系谁
- 拉某个员工最近聊天 dump

而且这些结果都来自 CRM 主服务真实数据，不来自 OpenClaw 本地空库。
