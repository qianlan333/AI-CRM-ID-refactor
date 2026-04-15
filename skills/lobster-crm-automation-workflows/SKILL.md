---
name: lobster-crm-automation-workflows
description: Use when Lobster needs to inspect or create CRM automation-conversion workflows and workflow nodes through the `wecom_mcp` proxy. Covers listing all workflows, reading workflow nodes, creating new workflows, and adding new workflow nodes without relying on native `crm.automation.*` tools.
---

# Lobster CRM Automation Workflows

This skill is for Lobster to operate the CRM automation-conversion workflow workspace through the `wecom_mcp` proxy tool.

Do not assume native `crm.automation.*` tools are visible in the current session. Use `wecom-preflight` plus `wecom_mcp list/call` instead.

## Use This Skill For

- 查看全部任务流
- 查看某个任务流下的全部节点
- 新增任务流
- 在已有任务流下新增节点

## Workflow

1. Before the first `wecom_mcp` call in a session, run the `wecom-preflight` skill.
2. Discover the usable CRM MCP category before doing workflow operations:
   - First try `wecom_mcp list crm`
   - If that category is empty or unavailable, try `wecom_mcp list crm.automation`
3. Use the category that returns workflow tools. Call methods through `wecom_mcp call <category> <method> <args>`.
4. Do not guess method names. Prefer the exact method names returned by `wecom_mcp list <category>`.
5. When the category lists the workflow methods, use this mapping:
   - registry lookup: `crm.automation.get_workflow_registry`
   - workflow listing: `crm.automation.list_workflows`
   - node listing: `crm.automation.get_workflow_nodes`
   - workflow creation: `crm.automation.create_workflow`
   - node creation: `crm.automation.create_workflow_node`
6. To create a node, first confirm the target workflow exists.

## Operating Rules

- Prefer creating workflows in `draft` status unless the user explicitly asks to activate them immediately.
- Do not invent `profile_segment_template_id` or `agent_bindings`. If the user has not provided them, default to the simplest valid workflow:
  - `segmentation_basis = none`
  - `generation_mode = manual_layered`
- When creating a node, do not invent a `target_audience_code`. It must already belong to the workflow audiences.
- If the user does not provide schedule details, prefer `trigger_mode = audience_entered`.
- For `standard_direct` nodes, always provide `standard_content_text`.
- If the create call fails with a validation error, surface the exact constraint and adjust the payload instead of guessing silently.
- If the first guessed category fails, retry with the other candidate category before concluding the workflow tools are unavailable.

## Response Style

- When listing workflows, summarize each workflow with:
  - `workflow_id`
  - `workflow_code`
  - `workflow_name`
  - `status`
  - node count
- When creating a workflow or node, always report the created IDs and codes.

## References

- See [tools.md](references/tools.md) for `wecom_mcp` discovery flow, category fallback, and minimal payloads.
