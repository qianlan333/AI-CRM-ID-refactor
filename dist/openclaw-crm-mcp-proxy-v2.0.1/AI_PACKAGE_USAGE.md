# OpenClaw CRM MCP Proxy v2.0.1 完整使用说明

## 1. 文档目的

这是一份给 AI 或接入方阅读的单文件完整说明。

目标是让阅读者一次性理解下面这些内容：

- 这个包是什么
- 它解决什么问题
- 它能做什么
- 它不能做什么
- 应该如何安装
- 应该如何配置
- OpenClaw 实际如何调用它
- 它和 CRM 主服务的关系是什么
- 升级和回滚怎么做

这份文档描述的对象是：

- `openclaw-crm-mcp-proxy-v2.0.1`

## 2. 一句话定义

`openclaw-crm-mcp-proxy-v2.0.1` 是一个给 OpenClaw 安装的薄代理 MCP 包。

它不会在 OpenClaw 本地运行完整 CRM，也不会在 OpenClaw 本地保存 CRM 数据。  
它只是在 OpenClaw 本地启动一个很小的代理服务，把所有 MCP 请求转发到 CRM 主服务真实在线的 `/mcp`。

## 3. 为什么需要这个包

旧的 `1.x` 路线是“本地完整 CRM 服务包”。

这条路线的问题已经确认：

- OpenClaw 本地没有真实 CRM 数据
- OpenClaw 本地没有真实聊天记录主库
- OpenClaw 本地不适合承担企业微信配置和同步
- 所以本地完整 CRM 包即使能启动，查到的也往往是空库、空上下文、空聊天

因此，`2.x` 的正确路线是：

- CRM 主服务继续负责真实能力和真实数据
- OpenClaw 本地只部署一个轻量代理
- 所有 CRM 查询、标签操作、任务创建、聊天 dump 都来自 CRM 主服务真实数据

## 4. 包的核心定位

### 4.1 这个包是什么

这个包是：

- 本地 MCP 代理
- OpenClaw 与 CRM 主服务之间的连接层
- 一个很轻的 HTTP 服务

### 4.2 这个包不是什么

这个包不是：

- CRM 主服务本体
- CRM 数据库副本
- 企业微信接入服务
- 会话存档同步服务
- 本地业务逻辑执行器

## 5. 它的工作方式

这个包在 OpenClaw 本地只提供两个接口：

- `GET /health`
- `POST /mcp`

### 5.1 `/health`

用途：

- 检查本地代理是否存活
- 可选检查远端 CRM 是否大致可达

### 5.2 `/mcp`

用途：

- 接收 OpenClaw 发来的 MCP JSON-RPC 请求
- 转发到远端 CRM 主服务真实 `/mcp`
- 原样返回远端结果

### 5.3 请求转发逻辑

本地代理收到请求后会：

1. 读取环境变量：
   - `CRM_MCP_URL`
   - `MCP_BEARER_TOKEN`
2. 以 `Authorization: Bearer <MCP_BEARER_TOKEN>` 调远端 CRM MCP
3. 将远端返回结果透传给本地调用方

### 5.4 本地代理不做的事

本地代理不会：

- 在本地实现 `tools/list`
- 在本地实现任何 CRM 工具逻辑
- 在本地重写工具返回结构
- 在本地维护客户、聊天、标签、任务数据

也就是说：

- `tools/list` 由远端 CRM 决定
- `tools/call` 的真实执行也由远端 CRM 决定

## 6. OpenClaw 调用链路

完整链路如下：

1. OpenClaw 调本地代理
   - `http://127.0.0.1:5001/mcp`
2. 本地代理转发到远端 CRM MCP
   - `https://www.youcangogogo.com/mcp`
3. CRM 主服务执行真实工具逻辑
4. CRM 主服务返回真实结果
5. 本地代理把结果返回给 OpenClaw

结论：

- OpenClaw 本地看到的是本地 MCP 服务
- 真实数据来源是远端 CRM 主服务

## 7. 当前远端地址

当前推荐配置的远端 CRM MCP 地址为：

```text
https://www.youcangogogo.com/mcp
```

对应健康检查：

```text
https://www.youcangogogo.com/health
```

## 8. 包当前能承载的能力

本地代理本身不实现 CRM 业务，但它能把远端 CRM 已有的真实工具带给 OpenClaw。

当前重点工具包括：

- `resolve_customer`
- `get_customer_context`
- `get_contact`
- `get_recent_messages`
- `update_customer_tags`
- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`
- `get_hourly_followup_candidates`
- `get_owner_recent_chat_dump`

## 9. 工具能力说明

### 9.1 `resolve_customer`

用途：

- 通过手机号或 `external_userid` 解析客户

典型场景：

- OpenClaw 只有手机号，需要先找到 CRM 中对应客户

### 9.2 `get_customer_context`

用途：

- 获取客户上下文

典型内容通常包括：

- 客户信息
- 最近消息
- 最近时间线事件

### 9.3 `get_contact`

用途：

- 获取联系人信息

### 9.4 `get_recent_messages`

用途：

- 获取最近聊天消息

### 9.5 `update_customer_tags`

用途：

- 添加标签
- 移除标签

### 9.6 `create_private_message_task`

用途：

- 创建私聊群发任务

### 9.7 `create_group_message_task`

用途：

- 创建客户群群发任务

### 9.8 `create_moment_task`

用途：

- 创建朋友圈任务

### 9.9 `get_hourly_followup_candidates`

用途：

- 获取当前最值得跟进的客户候选列表

### 9.10 `get_owner_recent_chat_dump`

用途：

- 拉取某个员工最近聊天 dump

典型场景：

- 看某个员工最近私聊对话
- 确认 CRM 主服务已经持有真实聊天记录

## 10. 典型业务能力总结

通过这版代理，OpenClaw 可以稳定做这些事：

- 通过手机号找客户
- 看客户上下文
- 看最近聊天
- 看某个员工最近聊天 dump
- 打标签/去标签
- 给用户设置私聊群发任务
- 给客户群设置群发任务
- 设置朋友圈任务
- 查看本小时优先跟进名单

## 11. 这版明确不能做什么

这版包明确不负责这些能力：

- 不在本地保存 CRM 数据
- 不在本地初始化数据库
- 不在本地同步企业微信联系人
- 不在本地同步聊天记录
- 不在本地维护 CRM schema
- 不在本地实现 CRM 业务逻辑
- 不替代 CRM 主服务

## 12. 运行所需最小依赖

### 12.1 Python 版本

- `>=3.10,<3.13`

### 12.2 Python 依赖

当前包只需要：

- `Flask==3.1.0`
- `requests==2.32.3`

## 13. 环境变量配置

### 13.1 必填变量

只有两个必填变量：

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

### 13.2 可选变量

- `APP_HOST`
- `APP_PORT`
- `CRM_MCP_TIMEOUT_SECONDS`
- `CRM_MCP_RETRY_COUNT`

### 13.3 推荐示例

```env
APP_HOST=127.0.0.1
APP_PORT=5001

CRM_MCP_URL=https://www.youcangogogo.com/mcp
MCP_BEARER_TOKEN=replace-with-your-token

CRM_MCP_TIMEOUT_SECONDS=30
CRM_MCP_RETRY_COUNT=0
```

### 13.4 明确不再需要的变量

这些都不应该再要求 OpenClaw 本地配置：

- `DATABASE_URL`
- `DATABASE_PATH`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`

## 14. 包内文件清单

`openclaw-crm-mcp-proxy-v2.0.1` 包内应包含：

- `VERSION`
- `manifest.json`
- `README.md`
- `CHANGELOG.md`
- `UPGRADE.md`
- `AI_PACKAGE_USAGE.md`
- `requirements.txt`
- `openclaw_crm_proxy_server.py`
- `install.sh`
- `verify.sh`
- `examples/.env.example`
- `examples/mcporter.json.example`

## 15. 包内不应包含什么

这版薄代理包不应再包含：

- `wecom_ability_service/` 全量源码
- `db.py`
- `schema.sql`
- `schema_postgres.sql`
- `services.py`
- 企业微信完整实现
- 本地 CRM 数据库副本

## 16. 安装方式

### 16.1 上传的文件

上传：

- `openclaw-crm-mcp-proxy-v2.0.1.tar.gz`

### 16.2 推荐解压目录

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1/
```

### 16.3 固定 current 路径

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

### 16.4 最小安装步骤

1. 上传新包
2. 解压到新的独立版本目录
3. 复制 `examples/.env.example` 为 `.env`
4. 配置 `CRM_MCP_URL` 和 `MCP_BEARER_TOKEN`
5. 运行 `install.sh`
6. 运行 `verify.sh`
7. 把 `current` 指向新版本
8. 重载 OpenClaw

### 16.5 示例命令

```bash
mkdir -p /root/.openclaw/workspace/packages/releases /root/.openclaw/workspace/packages/current
tar -xzf openclaw-crm-mcp-proxy-v2.0.1.tar.gz -C /root/.openclaw/workspace/packages/releases
cd /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1
cp examples/.env.example .env
./install.sh
./verify.sh
ln -sfn /root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1 /root/.openclaw/workspace/packages/current/openclaw-crm
```

## 17. OpenClaw 配置方式

OpenClaw 的示例配置文件在：

- `examples/mcporter.json.example`

核心语义是：

- `cwd` 指向当前版本目录
- `start_command` 启动本地代理
- OpenClaw 自己连接本地代理的：
  - `http://127.0.0.1:5001/mcp`

示例：

```json
{
  "name": "openclaw-crm",
  "version": "2.0.1",
  "transport": "http",
  "cwd": "/root/.openclaw/workspace/packages/current/openclaw-crm",
  "start_command": "bash -lc 'set -a && source ./.env && set +a && ./.venv/bin/python openclaw_crm_proxy_server.py'",
  "mcp_url": "http://127.0.0.1:5001/mcp",
  "health_url": "http://127.0.0.1:5001/health"
}
```

## 18. `install.sh` 做什么

`install.sh` 负责：

- 创建或复用本地 `.venv`
- 安装 `requirements.txt`

它不负责：

- 初始化数据库
- 初始化 CRM schema
- 配置企业微信

## 19. `verify.sh` 做什么

`verify.sh` 负责：

1. 检查代理可 import
2. 启动本地代理
3. 调本地 `/health`
4. 通过本地代理调用远端 `tools/list`
5. 确认关键工具存在

当前校验的关键工具包括：

- `resolve_customer`
- `get_customer_context`
- `update_customer_tags`
- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`
- `get_hourly_followup_candidates`
- `get_owner_recent_chat_dump`

## 20. 升级策略

推荐使用独立版本目录，不要覆盖旧目录。

升级方式：

1. 上传新包
2. 解压到新版本目录
3. 安装依赖
4. 验证
5. 切换 `current`
6. 重载 OpenClaw

## 21. 回滚策略

回滚应回到旧的代理版本，而不是旧的本地完整 CRM 包。

也就是说：

- 合理回滚：`2.0.1 -> 2.0.0`
- 不推荐回滚：`2.x -> 1.x 本地完整服务`

原因不是某个单点 bug，而是旧 `1.x` 路线本身的交付形态不对。

## 22. 给 AI 的接入理解要点

如果这份文档是给 AI 读，AI 应该理解以下固定规则：

1. 本地代理不是 CRM 服务本体
2. 所有 CRM 数据都来自远端主服务
3. 不要假设 OpenClaw 本地有数据库或企业微信配置
4. 不要在本地代理层实现业务逻辑
5. 所有工具能力都应该视为远端 CRM `/mcp` 的能力
6. 如果远端新增工具，代理通常无需修改
7. `get_owner_recent_chat_dump` 的结果来自远端真实聊天记录

## 23. 给别人讲时可以直接复用的话

可以直接这样介绍：

> `openclaw-crm-mcp-proxy-v2.0.1` 不是本地 CRM，而是 OpenClaw 的 CRM MCP 薄代理。
> OpenClaw 本地只起一个很小的 `/mcp` 服务，把所有请求转发到 CRM 主服务真实在线的 `/mcp`。
> 所以 OpenClaw 本地不需要数据库、不需要企业微信配置，也不持有 CRM 数据。
> 真正的客户信息、上下文、最近聊天、聊天 dump、标签操作和任务创建都来自 CRM 主服务。

## 24. 最终结论

这版包的真正价值是：

- 把 OpenClaw 的 CRM 接入形态改正确
- 让 OpenClaw 从此只消费 CRM 主服务的真实数据
- 避免本地空库问题
- 让本地安装尽量轻
- 让升级和回滚足够简单

如果需要一句最短总结：

> 这是一个把 OpenClaw 接到 CRM 主服务真实 MCP 上的薄代理包。
