# OpenClaw CRM MCP 1.0.0

这是一个可直接交付给 OpenClaw 使用的最小 CRM MCP 包。它保留当前已经在真实环境验证过的 MCP 能力面，不扩平台，不改 CRM 主服务。

## 包含能力

- `resolve_customer`
- `get_customer_context`
- `get_contact`
- `get_recent_messages`
- `update_customer_tags`
- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`
- `get_hourly_followup_candidates`

## 目录说明

- `openclaw_crm_server.py`: 启动入口
- `wecom_ability_service/`: MCP 服务源码
- `requirements.txt`: 运行时依赖
- `install.sh`: 最小安装脚本
- `verify.sh`: 最小验证脚本
- `manifest.json`: 版本和工具清单
- `mcp_usage.md`: MCP 使用说明
- `examples/mcporter.json.example`: OpenClaw 配置示例
- `examples/.env.example`: 环境变量示例

## Python 要求

- Python `>=3.10,<3.13`

## 依赖安装

```bash
./install.sh
```

默认会：

- 创建或复用 `./.venv`
- 安装 `requirements.txt`

## 最小环境变量

完整示例见 `examples/.env.example`。

最小必填：

- `MCP_BEARER_TOKEN`
- `DATABASE_PATH` 或 `DATABASE_URL`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`

常用可选：

- `APP_HOST`，默认 `127.0.0.1`
- `APP_PORT`，默认 `5000`
- `WECOM_API_BASE`
- `WECOM_DEFAULT_OWNER_USERID`
- `WECOM_ARCHIVE_SECRET`
- `WECOM_PRIVATE_KEY_PATH`
- `WECOM_SDK_LIB_PATH`

## 启动方式

初始化数据库：

```bash
set -a
source ./.env
set +a
./.venv/bin/python openclaw_crm_server.py init-db
```

启动服务：

```bash
set -a
source ./.env
set +a
./.venv/bin/python openclaw_crm_server.py run
```

## 最小验证

一键验证：

```bash
./verify.sh
```

手动验证：

```bash
curl -sS http://127.0.0.1:5001/health
curl -sS \
  -H "Authorization: Bearer ${MCP_BEARER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  http://127.0.0.1:5001/mcp
```

## OpenClaw 配置示例

见 `examples/mcporter.json.example`。建议 OpenClaw 以“固定 current 路径 + 独立版本目录”的方式引用这个包，不要直接覆盖旧版本目录。

## 运行边界

- 这是“最小 CRM MCP”交付包，不是复杂平台
- 当前任务类工具默认 `dry_run=true`
- 只有显式传 `dry_run=false` 且 `confirm=true` 才会真实创建任务
- 包内保留当前服务源码，因此也会包含 CRM 主服务的其他路由文件，但本次交付面以 MCP 为准
