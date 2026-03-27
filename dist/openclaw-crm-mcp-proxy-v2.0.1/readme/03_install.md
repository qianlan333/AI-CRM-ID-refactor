# 03 Install

## 上传哪个文件

上传这个包：

- `openclaw-crm-mcp-proxy-v2.0.1.tar.gz`

## 推荐目录

不要覆盖旧目录。

推荐解压到：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1/
```

OpenClaw 固定只认：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

## 最小安装步骤

1. 上传新包
2. 解压到新的独立版本目录
3. 复制环境变量示例
4. 填写 `CRM_MCP_URL` 和 `MCP_BEARER_TOKEN`
5. 执行 `install.sh`
6. 执行 `verify.sh`
7. 把 `current/openclaw-crm` 切到新版本目录
8. 重载 OpenClaw

## 示例命令

```bash
mkdir -p /root/.openclaw/workspace/packages/releases /root/.openclaw/workspace/packages/current
tar -xzf openclaw-crm-mcp-proxy-v2.0.1.tar.gz -C /root/.openclaw/workspace/packages/releases
cd /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1
cp examples/.env.example .env
./install.sh
./verify.sh
ln -sfn /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1 /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 回滚怎么做

最小回滚方式：

1. 把 `current` 切回旧代理版本目录
2. 重载 OpenClaw

不再建议回滚回旧的 `1.x` 本地完整 CRM 包。
