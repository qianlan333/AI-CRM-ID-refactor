---
name: lobster-crm-automation-workflows
description: Use when Lobster needs to inspect or create CRM automation-conversion workflows and workflow nodes through MCP. Covers listing all workflows, reading workflow nodes, creating new workflows, and adding new workflow nodes.
---

# Lobster CRM Automation Workflows

This skill is for Lobster to operate the CRM automation-conversion workflow workspace through MCP.

It assumes the `openclaw-wecom-mcp` / `wecom-mcp` server is already enabled and reachable.

## Use This Skill For

- 查看全部任务流
- 查看某个任务流下的全部节点
- 新增任务流
- 在已有任务流下新增节点

## Workflow

1. If you are unsure which enum values are allowed, call `crm.automation.get_workflow_registry` first.
2. To inspect current setup, call `crm.automation.list_workflows`.
3. If the user asks for one workflow's nodes only, call `crm.automation.get_workflow_nodes`.
4. To create a workflow, call `crm.automation.create_workflow`.
5. To create a node, first confirm the target workflow exists, then call `crm.automation.create_workflow_node`.

## Operating Rules

- Prefer creating workflows in `draft` status unless the user explicitly asks to activate them immediately.
- Do not invent `profile_segment_template_id` or `agent_bindings`. If the user has not provided them, default to the simplest valid workflow:
  - `segmentation_basis = none`
  - `generation_mode = manual_layered`
- When creating a node, do not invent a `target_audience_code`. It must already belong to the workflow audiences.
- If the user does not provide schedule details, prefer `trigger_mode = audience_entered`.
- For `standard_direct` nodes, always provide `standard_content_text`.
- If the create call fails with a validation error, surface the exact constraint and adjust the payload instead of guessing silently.

## Response Style

- When listing workflows, summarize each workflow with:
  - `workflow_id`
  - `workflow_code`
  - `workflow_name`
  - `status`
  - node count
- When creating a workflow or node, always report the created IDs and codes.

## References

- See [tools.md](references/tools.md) for tool contracts, enums, and minimal example payloads.
