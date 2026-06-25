from __future__ import annotations

import importlib.util

from aicrm_next.automation_engine.repo import build_automation_repository


def test_retired_task_workflow_profile_modules_are_removed() -> None:
    retired_modules = {
        "aicrm_next.automation_engine.domain",
        "aicrm_next.automation_engine.profile_segments",
        "aicrm_next.automation_engine.state_machine",
        "aicrm_next.automation_engine.task_groups",
        "aicrm_next.automation_engine.tasks",
        "aicrm_next.automation_engine.workflow",
        "aicrm_next.automation_engine.workflow_nodes",
        "aicrm_next.automation_engine.workflows",
    }

    for module_name in retired_modules:
        assert importlib.util.find_spec(module_name) is None


def test_fixture_automation_repository_is_agent_only() -> None:
    repo = build_automation_repository()

    for name in (
        "list_pools",
        "list_members",
        "get_member",
        "find_member",
        "list_profile_segment_templates",
        "create_profile_segment_template",
        "list_task_groups",
        "create_task_group",
        "list_workflows",
        "create_workflow",
        "list_workflow_nodes",
        "create_workflow_node",
        "list_tasks",
        "create_task",
    ):
        assert not hasattr(repo, name)

    assert hasattr(repo, "list_agents")
    assert hasattr(repo, "list_agent_outputs")
    assert hasattr(repo, "list_agent_runs")
