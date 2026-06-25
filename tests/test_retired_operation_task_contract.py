from __future__ import annotations

import importlib.util


def test_retired_operation_task_contract_module_is_removed() -> None:
    assert importlib.util.find_spec("aicrm_next.automation_engine.operation_task_contract") is None
