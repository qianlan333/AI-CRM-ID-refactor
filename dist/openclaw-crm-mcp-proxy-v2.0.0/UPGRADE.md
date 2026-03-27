# OpenClaw CRM MCP Proxy Upgrade Guide

## 1. 这是 breaking change

`2.0.0` 是运行形态变更，不是普通小升级。

旧包：

- 本地完整 CRM 服务包

新包：

- 薄 MCP 代理包

因此必须升级主版本，不能继续用 `1.x` 口径混用。

## 2. 旧 1.x 路线状态

旧的 `1.x` 本地完整服务包不要继续用于 OpenClaw 安装。

原因：

- OpenClaw 本地没有真实 CRM 数据
- 本地运行完整服务只会查空库或假环境
- 正确模式是转发到 CRM 服务器真实 `/mcp`

## 3. 新版本目录规则

不要覆盖旧目录。

推荐目录：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.0/
```

OpenClaw 只认固定 current：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

## 4. 升级步骤

1. 上传 `openclaw-crm-mcp-proxy-v2.0.0.tar.gz`
2. 解压到新的独立版本目录
3. 配置 `CRM_MCP_URL` 和 `MCP_BEARER_TOKEN`
4. 运行 `./install.sh`
5. 运行 `./verify.sh`
6. 验证通过后，把 `current` 切到新版本目录
7. 重载 OpenClaw

示例：

```bash
mkdir -p /root/.openclaw/workspace/packages/releases /root/.openclaw/workspace/packages/current
tar -xzf openclaw-crm-mcp-proxy-v2.0.0.tar.gz -C /root/.openclaw/workspace/packages/releases
cd /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.0
cp examples/.env.example .env
./install.sh
./verify.sh
ln -sfn /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.0 /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 5. 回滚步骤

1. 把 `current` 切回旧代理版本目录
2. 重载 OpenClaw

示例：

```bash
ln -sfn /root/.openclaw/workspace/packages/releases/<previous-proxy-version> /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 6. 回滚边界

不再建议回滚到“本地完整 CRM 服务包”路线。

`2.0.0` 的回滚边界是：

- 只在薄代理版本之间切换
- 不再把 OpenClaw 切回本地库模式
