# OpenClaw CRM MCP Upgrade Guide

## 1. 版本目录规则

不要原地覆盖旧版本目录。

正确方式是每个版本一个独立目录，例如：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.0/
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1/
```

## 2. current 规则

OpenClaw 只指向一个“当前版本”。

建议使用固定软链接：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm -> /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1
```

不要让 OpenClaw 直接写死到某个历史版本目录。

## 3. 升级流程

最小步骤：

1. 上传新包，例如 `openclaw-crm-mcp-v1.0.1.tar.gz`
2. 解压到新的独立版本目录
3. 检查 `README.md`、`manifest.json`、`install.md`
4. 进入新版本目录执行 `./install.sh`
5. 准备 `.env` 或环境变量
6. 执行 `./verify.sh`
7. 验证通过后，把 `current/openclaw-crm` 切到新版本目录
8. 重载或重启 OpenClaw 的 MCP 进程
9. 再执行一次 `tools/list`
10. 再做一次最小 live 验证

示例：

```bash
mkdir -p /root/.openclaw/workspace/packages/releases /root/.openclaw/workspace/packages/current
tar -xzf openclaw-crm-mcp-v1.0.1.tar.gz -C /root/.openclaw/workspace/packages/releases
cd /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1
./install.sh
cp examples/.env.example .env
./verify.sh
ln -sfn /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1 /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 4. 回滚流程

最小步骤：

1. 把 `current/openclaw-crm` 切回旧版本目录
2. 重载或重启 OpenClaw 的 MCP 进程
3. 重新执行一次 `tools/list`

示例：

```bash
ln -sfn /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.0 /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 5. OpenClaw 新老版本处理策略

- 保持同一个 MCP 名称，例如 `openclaw-crm`
- 新旧版本并存，靠 `current` 指向切换
- 不在旧目录里直接覆盖文件
- 升级前先安装和验证新目录
- 回滚时只切换 `current`，不要回滚数据库

## 6. 版本号策略

- `1.x.y`
- `x` 变化：新增能力，但兼容旧调用
- `y` 变化：修 bug 或小幅兼容修复
- `2.0.0`：只有在出现 breaking change 时才发布

breaking change 的典型例子：

- 删除已有工具
- 改已有工具名称
- 改必填参数语义，导致旧调用失效
- 改返回约定，导致旧调用方必须修改

non-breaking change 的典型例子：

- 新增工具
- 新增可选参数
- 新增非破坏字段
- 兼容性修复
