# MCP Tool Matrix

## 只读

- `list_agent_configs`
- `get_agent_config`
- `diff_agent_prompt`

## 草稿写入

- `create_agent_config`
- `save_agent_prompt_draft`

## 发布申请

- `submit_agent_prompt_for_publish`

## 推荐调用链

### 查看已有 Agent

1. `list_agent_configs`
2. `get_agent_config`

### 新建 Agent

1. `create_agent_config`
2. `get_agent_config`
3. `diff_agent_prompt`
4. `submit_agent_prompt_for_publish`

### 编辑已有 Agent

1. `get_agent_config`
2. `save_agent_prompt_draft`
3. `diff_agent_prompt`
4. `submit_agent_prompt_for_publish`

## create_agent_config 示例

```json
{
  "agent_code": "questionnaire_followup_agent",
  "display_name": "问卷跟进 Agent",
  "enabled": true,
  "role_prompt": "你是问卷跟进 Agent。",
  "task_prompt": "基于问卷明细生成首轮跟进话术。",
  "variables": [
    {
      "variable_key": "questionnaire_answers",
      "display_name": "问卷答案",
      "description": "结构化问卷答案",
      "enabled": true
    }
  ],
  "output_schema": [
    {
      "field_key": "draft_reply",
      "display_name": "草稿回复",
      "type": "string",
      "required": true
    }
  ],
  "change_summary": "新建问卷跟进 Agent",
  "operator": "lobster"
}
```

## save_agent_prompt_draft 示例

```json
{
  "agent_code": "pricing_agent",
  "task_prompt": "先解释价格结构，再收敛到下一步动作。",
  "change_summary": "收紧价格答疑脚本",
  "expected_draft_version": 7,
  "operator": "lobster"
}
```
