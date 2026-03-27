# OpenClaw CRM MCP Proxy v2.0.1

这是一个给 OpenClaw 安装的薄代理 MCP 包。

## 这是什么

这个包不是本地 CRM 服务副本，而是一个很小的本地 MCP 代理。

它只做两件事：

- 提供本地 `/health`
- 提供本地 `/mcp`，并把所有 JSON-RPC 请求转发到远端 CRM 服务器真实可用的 `/mcp`

## 固定定位

- CRM 服务器继续负责真实数据、真实工具、真实能力
- OpenClaw 云端只安装这个代理包
- OpenClaw 本地不持有 CRM 数据
- OpenClaw 本地不连接本地数据库
- OpenClaw 本地不需要企业微信配置

## 当前能力范围

本地代理本身不实现工具逻辑。

OpenClaw 通过本地代理最终可调用的工具，完全由远端 CRM `/mcp` 决定。当前预期至少包括：

- `resolve_customer`
- `get_customer_context`
- `update_customer_tags`
- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`
- `get_hourly_followup_candidates`
- `get_owner_recent_chat_dump`

其中 `get_owner_recent_chat_dump` 的真实数据来自 CRM 主服务，不来自 OpenClaw 本地。

## 运行方式

OpenClaw 本地启动：

- `openclaw_crm_proxy_server.py`

本地代理读取环境变量：

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

然后把 `/mcp` 请求原样转发到远端 CRM。

## 必填环境变量

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

## 可选环境变量

- `APP_HOST`，默认 `127.0.0.1`
- `APP_PORT`，默认 `5001`
- `CRM_MCP_TIMEOUT_SECONDS`，默认 `30`
- `CRM_MCP_RETRY_COUNT`，默认 `0`

## 明确不再需要

这个代理包不再要求这些本地配置：

- `DATABASE_URL`
- `DATABASE_PATH`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`
- 任何企业微信 SDK、联系人同步或本地 schema

## 安装方式

上传这个文件：

- `openclaw-crm-mcp-proxy-v2.0.1.tar.gz`

建议目录：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1/
```

OpenClaw 固定只认：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

## 远端 CRM 地址

当前远端可达示例地址：

```text
https://www.youcangogogo.com/mcp
```

健康检查：

```text
https://www.youcangogogo.com/health
```

## 旧包状态

旧的 `1.x` 本地完整 CRM 服务包应视为废弃路线，不再继续用于 OpenClaw 安装。

原因：

- OpenClaw 本地没有真实 CRM 数据
- 本地完整服务只会落到空库或假环境
- 正确形态应当是薄代理转发到 CRM 服务器

## 验证方式

```bash
./install.sh
cp examples/.env.example .env
./verify.sh
```

`verify.sh` 会验证：

- 本地代理 import 正常
- 本地代理可启动
- 本地 `/health` 正常
- 通过本地代理访问远端 `tools/list` 成功

## OpenClaw 配置

见：

- `examples/mcporter.json.example`

OpenClaw 连的是本地代理 `/mcp`，不是直接连远端 CRM `/mcp`。
