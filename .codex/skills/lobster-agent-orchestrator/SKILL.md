---
name: lobster-agent-orchestrator
description: 当用户需要通过 Lobster 查看 CRM 子 Agent、编辑已有 Agent、创建新 Agent、检查草稿差异或提交发布申请时使用。适用于自动化转化模块下的 Agent 编排与配置维护，复用现有 MCP tools：`list_agent_configs`、`get_agent_config`、`create_agent_config`、`save_agent_prompt_draft`、`diff_agent_prompt`、`submit_agent_prompt_for_publish`。
---

# Lobster Agent Orchestrator

这个 skill 只负责 CRM 自动化转化模块里的子 Agent 编排，不碰任务流执行、自动化应答放行、也不直接操作运行中的批次。

## 何时使用

- 需要列出当前已有 Agent
- 需要查看某个 Agent 的草稿 / 已发布配置
- 需要创建一个新的 Agent
- 需要编辑已有 Agent 的 role prompt / task prompt / variables / output schema
- 需要比较草稿和已发布版本差异
- 需要把草稿提交为待发布

## 工作顺序

### 1. 查看现有 Agent

先调用：

- `list_agent_configs`

如需看详细配置，再调用：

- `get_agent_config`

## 2. 新建 Agent

调用：

- `create_agent_config`

最小必填字段：

- `agent_code`
- `display_name`
- `role_prompt`
- `task_prompt`

可选字段：

- `enabled`
- `variables`
- `output_schema`
- `change_summary`
- `operator`

`agent_code` 规则：

- 只能用小写字母、数字、下划线
- 建议用业务含义清楚的 snake_case
- 一旦创建，不要随意改 code

### 3. 编辑已有 Agent

先调用：

- `get_agent_config`

再调用：

- `save_agent_prompt_draft`

优先只 patch 实际要改的字段：

- `display_name`
- `enabled`
- `role_prompt`
- `task_prompt`
- `variables`
- `output_schema`
- `change_summary`

如果拿到了 `draft_version`，提交时优先带：

- `expected_draft_version`

这样可以避免把别人刚改过的草稿覆盖掉。

### 4. 发布前自检

调用：

- `diff_agent_prompt`

重点检查：

- role prompt 是否和已发布版本不同
- task prompt 是否和已发布版本不同
- variables 是否和已发布版本不同
- output schema 是否和已发布版本不同

### 5. 提交发布申请

调用：

- `submit_agent_prompt_for_publish`

注意：

- 这是提交发布申请，不是直接正式发布
- 线上运行仍只吃已发布版本

## 变量约定

自动化转化运行时会注入结构化上下文，所以变量定义建议围绕“让 Agent 明白会收到什么结构化输入”来写，不要假设能拿到完整聊天上下文。

问卷完成后按问卷明细生成话术时，建议 variables 里至少表达：

- `questionnaire_answers`
- `profile_segment`
- `behavior_tier`
- `standard_content_text`
- `member_profile`

如果用户没有提供完整变量结构，先通过 `get_agent_config` 查看同类 Agent 现有定义，再决定是否复用。

## 输出协议约定

输出协议建议保持稳定且字段少。默认优先保留：

- `draft_reply`
- `reason`
- `next_action`
- `need_human_review`

不要把输出协议改成自由散文，避免后续链路消费不稳定。

## 安全边界

- 不直接发布未审草稿
- 不删除已有 Agent
- 不修改中央 router webhook 配置
- 不修改自动化转化任务流执行记录

## 参考

- 详细工具矩阵见 [references/mcp-tool-matrix.md](references/mcp-tool-matrix.md)
