# 04 Configuration

## 必填环境变量

这版只有两个必填变量：

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

## 当前推荐配置

```env
CRM_MCP_URL=https://www.youcangogogo.com/mcp
MCP_BEARER_TOKEN=replace-with-your-token
```

## 可选变量

```env
APP_HOST=127.0.0.1
APP_PORT=5001
CRM_MCP_TIMEOUT_SECONDS=30
CRM_MCP_RETRY_COUNT=0
```

## 明确不再需要的变量

这些都不应再要求 OpenClaw 本地配置：

- `DATABASE_URL`
- `DATABASE_PATH`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`

## OpenClaw 自己连哪里

OpenClaw 本地连接的是代理：

```text
http://127.0.0.1:5001/mcp
```

代理再去连远端 CRM：

```text
https://www.youcangogogo.com/mcp
```

## 配置示例文件

看这两个文件：

- `examples/.env.example`
- `examples/mcporter.json.example`
