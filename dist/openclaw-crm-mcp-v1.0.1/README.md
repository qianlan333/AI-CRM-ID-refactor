# OpenClaw CRM MCP v1.0.1

这是一个给 OpenClaw 安装和调用的 CRM MCP 包。开发和真实能力扩展都应继续在 CRM 服务器完成，OpenClaw 只负责安装、切版本和调用。

## 这个包是干什么的

这个包用于把 CRM 服务器已经实现好的能力，以 MCP 方式交付给 OpenClaw 使用。

当前定位：

- CRM 服务器负责开发、修复和扩展
- OpenClaw 只安装这个包并调用工具
- 不把 OpenClaw 当成持续开发环境

## 当前能力范围

当前支持：

- 通过手机号或 `external_userid` 解析客户：`resolve_customer`
- 获取客户上下文：`get_customer_context`
- 读取联系人和最近消息：`get_contact`、`get_recent_messages`
- 标签管理：`update_customer_tags`
- 创建任务：`create_private_message_task`、`create_group_message_task`、`create_moment_task`
- 获取每小时最该联系的候选客户：`get_hourly_followup_candidates`

当前不支持：

- UI
- 复杂平台层编排
- 在 OpenClaw 侧直接改 CRM 底层逻辑
- 用 Skill 替代 MCP 服务端能力

## 输入输出规则

输入规则：

- 客户定位优先使用 `customer_ref`
- `customer_ref` 支持手机号或 `external_userid`
- 任务类工具默认 `dry_run=true`
- 只有显式传 `dry_run=false` 且 `confirm=true` 时，才允许真实创建任务

输出规则：

- 成功时返回工具结果和必要上下文
- 解析不到手机号时返回明确错误，不静默失败
- `get_customer_context` 返回客户信息、最近消息和最近时间线事件

主要工具：

- `resolve_customer`
- `get_customer_context`
- `get_contact`
- `get_recent_messages`
- `update_customer_tags`
- `create_private_message_task`
- `create_group_message_task`
- `create_moment_task`
- `get_hourly_followup_candidates`

## 包内结构

- `README.md`: 当前包说明
- `VERSION`: 当前版本号
- `manifest.json`: 包清单和工具列表
- `CHANGELOG.md`: 版本变更记录
- `UPGRADE.md`: OpenClaw 升级和回滚规则
- `install.md`: 最小安装说明
- `requirements.txt`: Python 依赖
- `install.sh`: 安装脚本
- `verify.sh`: 验证脚本
- `examples/.env.example`: 环境变量示例
- `examples/mcporter.json.example`: OpenClaw 配置示例
- `openclaw_crm_server.py`: 启动入口
- `wecom_ability_service/`: 运行所需服务代码

## 安装方式

你应该上传整个压缩包：

- `openclaw-crm-mcp-v1.0.1.tar.gz`

推荐解压位置：

```text
/root/.openclaw/workspace/packages/releases/openclaw-crm-mcp-v1.0.1/
```

OpenClaw 固定只认一个当前路径：

```text
/root/.openclaw/workspace/packages/current/openclaw-crm
```

详细步骤见 `install.md` 和 `UPGRADE.md`。

## 最小运行要求

Python：

- `>=3.10,<3.13`

最小环境变量：

- `MCP_BEARER_TOKEN`
- `DATABASE_PATH` 或 `DATABASE_URL`
- `WECOM_CORP_ID`
- `WECOM_CONTACT_SECRET`
- `WECOM_SECRET`
- `WECOM_AGENT_ID`

依赖安装：

```bash
./install.sh
```

启动：

```bash
set -a
source ./.env
set +a
./.venv/bin/python openclaw_crm_server.py run
```

验证：

```bash
./verify.sh
```

## 新老版本处理

固定规则：

- 不覆盖旧版本目录
- 每个版本一个独立目录
- OpenClaw 只指向 `current/openclaw-crm`
- 升级靠切换 `current`
- 回滚也靠切换 `current`

## 能力边界

- 这是 MCP 交付包，不是 Skill 包
- 如果后续需要指导 OpenClaw 如何组织调用流程，再单独交付 Skill 包
- 当前包的目标是“让 OpenClaw 调系统能力”，不是承载复杂业务解释层
