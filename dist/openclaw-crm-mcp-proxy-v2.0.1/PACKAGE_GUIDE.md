# OpenClaw CRM MCP Proxy v2.0.1 说明文档

## 1. 这是什么

`openclaw-crm-mcp-proxy-v2.0.1` 是一个给 OpenClaw 安装的薄代理 MCP 包。

它的作用不是在 OpenClaw 本地运行一套 CRM，也不是在 OpenClaw 本地保存客户、会话、标签或企业微信数据。

它只做一件事：

- 在 OpenClaw 本地起一个很小的代理服务
- 接住 OpenClaw 发来的 MCP 请求
- 把请求转发到 CRM 主服务真实在线的 `/mcp`
- 再把远端结果原样返回给 OpenClaw

可以把它理解成：

- OpenClaw 本地：只负责“接线”和“转发”
- CRM 主服务：负责“真实能力”和“真实数据”

## 2. 为什么要有这个包

这版包是为了替换旧的“本地完整 CRM 服务包”路线。

旧路线的问题已经很明确：

- OpenClaw 本地没有真实 CRM 数据
- OpenClaw 本地即使把 CRM 服务跑起来，查到的也是空库或伪环境
- 这会造成一种假象：
  - 工具看起来都在
  - 服务看起来也正常
  - 但查客户上下文、最近聊天、聊天 dump 时返回空结果

所以这版 `2.0.1` 的核心价值不是“新增更多功能”，而是把交付形态改正确：

- 不再让 OpenClaw 本地持有 CRM 副本
- 不再让 OpenClaw 本地维护数据库
- 不再让 OpenClaw 本地配置企业微信
- 所有查询和工具调用都回到 CRM 主服务真实数据上

## 3. 它能干什么

这个包本身不实现 CRM 业务逻辑，但它能让 OpenClaw 稳定使用 CRM 主服务已经提供的真实 MCP 能力。

当前它能承载的典型能力包括：

- 解析客户身份
  - `resolve_customer`
  - 支持手机号或 `external_userid`

- 获取客户上下文
  - `get_customer_context`
  - `get_contact`
  - `get_recent_messages`

- 标签操作
  - `update_customer_tags`

- 任务创建
  - `create_private_message_task`
  - `create_group_message_task`
  - `create_moment_task`

- 跟进候选
  - `get_hourly_followup_candidates`

- 最近聊天 dump
  - `get_owner_recent_chat_dump`

注意：

- 这些工具真正的实现和数据都在 CRM 主服务
- 代理包只是把这些能力安全地带到 OpenClaw 本地

## 4. 它不能干什么

这版包明确不负责这些事情：

- 不在本地保存 CRM 数据
- 不在本地运行完整 CRM 服务
- 不在本地连接 CRM 数据库
- 不在本地同步企业微信联系人或聊天
- 不在本地重新实现 MCP 工具逻辑
- 不在本地维护独立的 `tools/list`
- 不替代 CRM 主服务做业务判断

一句话：

它不是 CRM，本地也不是数据源，它只是 CRM MCP 的本地代理入口。

## 5. 它的工作方式

### 本地暴露的接口

代理服务只暴露两个 HTTP 接口：

- `GET /health`
- `POST /mcp`

### `/health` 做什么

`/health` 用于说明本地代理进程是否活着，并可选返回远端 CRM 是否可达的摘要。

它主要回答两个问题：

- 本地代理有没有启动成功
- 当前配置的远端 CRM MCP 地址是否大致可访问

### `/mcp` 做什么

`/mcp` 是 MCP 入口。

它收到 OpenClaw 发来的 JSON-RPC 请求后，会：

1. 读取本地环境变量：
   - `CRM_MCP_URL`
   - `MCP_BEARER_TOKEN`
2. 给远端 CRM MCP 发起同样的请求
3. 用 `Authorization: Bearer <MCP_BEARER_TOKEN>` 做认证
4. 把远端返回结果原样透传回来

这意味着：

- `tools/list` 是远端 CRM 决定的
- `tools/call` 也是远端 CRM 决定的
- 代理本地不解释工具含义，也不复制任何工具实现

## 6. 这版为什么比旧包正确

### 旧包的问题

旧的 `1.x` 路线是“把本地完整 CRM 服务包塞给 OpenClaw”。

这个方向的问题不是代码写得不够多，而是架构前提本身不成立：

- OpenClaw 机器不是 CRM 数据主机
- 没有真实数据库
- 没有真实会话存档
- 没有真实企业微信配置和同步链路

所以旧包越完整，结果越容易出现“服务正常但数据为空”。

### 新包的正确点

`2.0.1` 走的是“薄代理”模式：

- CRM 主服务继续作为唯一真实数据源
- OpenClaw 只部署最小代理
- OpenClaw 的所有 CRM 能力最终都来自 CRM 主服务

这样，OpenClaw 看到的客户信息、上下文、最近消息、最近聊天 dump，才会和 CRM 主服务保持一致。

## 7. 最小依赖和配置

### 必填环境变量

只需要两个必填变量：

- `CRM_MCP_URL`
- `MCP_BEARER_TOKEN`

### 可选环境变量

- `APP_HOST`
- `APP_PORT`
- `CRM_MCP_TIMEOUT_SECONDS`
- `CRM_MCP_RETRY_COUNT`

### 明确不再需要的配置

这些都不应该再要求 OpenClaw 本地配置：

- `DATABASE_URL`
- `DATABASE_PATH`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`
- 本地联系人同步
- 本地聊天同步
- 本地 schema 初始化

## 8. 当前推荐的远端地址

当前远端 CRM MCP 对外地址应配置为：

```text
https://www.youcangogogo.com/mcp
```

健康检查：

```text
https://www.youcangogogo.com/health
```

所以 OpenClaw 本地代理最核心的配置，就是把：

- `CRM_MCP_URL=https://www.youcangogogo.com/mcp`

写进 `.env`。

## 9. OpenClaw 最终连的是谁

这一点很重要，最容易被误解。

OpenClaw 最终不是直接连 CRM 主服务，也不是直接连数据库。

调用链路是：

1. OpenClaw 调本地代理：
   - `http://127.0.0.1:5001/mcp`
2. 本地代理再转发到远端 CRM：
   - `https://www.youcangogogo.com/mcp`
3. CRM 主服务返回真实结果
4. 本地代理把结果返回给 OpenClaw

所以从 OpenClaw 视角看：

- 本地只看到一个本地 MCP 服务

但从数据真实性看：

- 真正返回的数据来自 CRM 主服务

## 10. 典型适用场景

这个包适合这些场景：

- OpenClaw 需要调用 CRM 能力，但不适合本地部署 CRM 全服务
- OpenClaw 需要拿到 CRM 主服务的真实客户和聊天数据
- 希望 OpenClaw 安装过程尽量简单
- 希望升级和回滚都只靠切换包版本完成

不适合这些场景：

- 想让 OpenClaw 本地脱离 CRM 主服务独立工作
- 想让 OpenClaw 本地自己保存客户数据
- 想在 OpenClaw 本地改 CRM 底层实现

## 11. 交付物包含什么

`2.0.1` 包内只包含最小运行件：

- `VERSION`
- `manifest.json`
- `README.md`
- `CHANGELOG.md`
- `UPGRADE.md`
- `requirements.txt`
- `openclaw_crm_proxy_server.py`
- `install.sh`
- `verify.sh`
- `examples/.env.example`
- `examples/mcporter.json.example`

明确不包含：

- `wecom_ability_service/` 全量源码
- `db.py`
- `schema.sql`
- `routes.py`
- `services.py`
- 企业微信完整实现
- CRM 本地数据库副本

## 12. 安装和升级思路

推荐安装目录：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-proxy-v2.0.1/
```

固定 current：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

推荐流程：

1. 上传新包
2. 解压到新的独立版本目录
3. 配置 `.env`
4. 跑 `install.sh`
5. 跑 `verify.sh`
6. 把 `current` 指向新版本
7. 重载 OpenClaw

这套模式的好处是：

- 不覆盖旧目录
- 回滚简单
- 不容易把旧环境改坏

## 13. 回滚怎么理解

回滚应该回到“旧代理版本”，而不是回到“本地完整 CRM 服务包”。

也就是说：

- `2.0.1 -> 2.0.0` 这种回滚是合理的
- `2.x -> 1.x 本地完整服务包` 不推荐再走

因为 `1.x` 路线的问题不在某个 bug，而在整体形态不对。

## 14. 给别人解释时最短的话术

如果你要把这版包讲给别人听，可以直接用这段话：

> 这不是一套本地 CRM，而是 OpenClaw 的 CRM MCP 本地代理。
> OpenClaw 本地只起一个很小的 `/mcp` 服务，把所有请求转发到 CRM 主服务真实在线的 `/mcp`。
> 所以 OpenClaw 本地不需要数据库、不需要企业微信配置，也不持有 CRM 数据。
> 真正的客户、上下文、最近聊天和聊天 dump 都来自 CRM 主服务。

## 15. 结论

`openclaw-crm-mcp-proxy-v2.0.1` 的价值不在于“多做了一个 CRM”，而在于：

- 把 OpenClaw 的 CRM 接入形态改正确了
- 让 OpenClaw 从此只消费 CRM 主服务的真实 MCP
- 让本地安装足够轻
- 让升级、切换和回滚更简单
- 让“工具可见但查空库”的问题从交付形态上被彻底避免
