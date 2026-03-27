# 01 Overview

## 这是什么

`openclaw-crm-mcp-proxy-v2.0.1` 是一个给 OpenClaw 安装的薄代理 MCP 包。

它不是 CRM 服务本体，也不是 CRM 数据副本。

它的职责非常简单：

- 在 OpenClaw 本地暴露 `/health`
- 在 OpenClaw 本地暴露 `/mcp`
- 把所有 MCP 请求转发到 CRM 主服务真实在线的 `/mcp`
- 把远端返回结果原样返回给 OpenClaw

## 为什么要改成这种形态

旧的 `1.x` 路线是把“本地完整 CRM 服务包”塞给 OpenClaw。

这条路的问题已经被验证过：

- OpenClaw 本地没有真实 CRM 数据
- OpenClaw 本地没有真实聊天记录主库
- OpenClaw 本地也不应该承担企业微信配置和同步

所以旧模式会出现：

- 工具在
- 服务也能启动
- 但一查上下文、最近聊天、聊天 dump，返回空结果

`2.x` 代理模式就是为了解决这个根问题。

## 新模式的核心原则

- CRM 主服务负责真实数据和真实工具
- OpenClaw 只负责调用
- OpenClaw 本地不持有 CRM 数据
- OpenClaw 本地不连本地数据库
- OpenClaw 本地不配置企业微信

## 调用链路

1. OpenClaw 调本地代理：
   - `http://127.0.0.1:5001/mcp`
2. 本地代理转发到远端 CRM：
   - `https://www.youcangogogo.com/mcp`
3. CRM 主服务返回真实结果
4. 本地代理把结果透传给 OpenClaw

## 结论

这版的价值不在“又做了一套 CRM”，而在于：

- 让 OpenClaw 终于稳定接到 CRM 主服务真实数据
- 从架构上避免“本地空库”问题
- 把 OpenClaw 的安装和升级成本降到最低
