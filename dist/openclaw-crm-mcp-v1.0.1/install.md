# OpenClaw CRM MCP Install Guide

## 1. 上传文件

上传这个包：

- `openclaw-crm-mcp-v1.0.1.tar.gz`

## 2. 解压位置

不要覆盖旧目录。解压到新的独立版本目录：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1/
```

## 3. 安装依赖

```bash
cd /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1
./install.sh
```

## 4. 准备环境变量

复制示例：

```bash
cp examples/.env.example .env
```

至少补齐：

- `MCP_BEARER_TOKEN`
- `DATABASE_PATH` 或 `DATABASE_URL`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`

## 5. 安装前验证

```bash
./verify.sh
```

## 6. 切到 current

OpenClaw 只应指向固定 current 路径：

```bash
mkdir -p /root/.openclaw/workspace/packages/current
ln -sfn /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1 /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 7. OpenClaw 配置示例

见：

- `examples/mcporter.json.example`

其中 `cwd` 应固定指向：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

## 8. 最小回滚

把 `current` 切回旧版本目录，再重载 OpenClaw 对应配置。
