from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_retired_operation_task_contract_module_is_removed() -> None:
    assert importlib.util.find_spec("aicrm_next.automation_engine.operation_task_contract") is None


def test_retired_operation_task_is_not_a_broadcast_source_option() -> None:
    from aicrm_next.admin_jobs.domain import BROADCAST_SOURCE_TYPE_LABELS, BROADCAST_SOURCE_TYPES
    from aicrm_next.admin_jobs.repository import clean_broadcast_filters

    assert "operation_task" not in BROADCAST_SOURCE_TYPES
    assert "operation_task" not in BROADCAST_SOURCE_TYPE_LABELS

    _, source_types = clean_broadcast_filters([], ["operation_task", "manual"])

    assert source_types == ["manual"]


def test_retired_operation_task_label_is_not_special_cased_in_admin_jobs() -> None:
    source = (PROJECT_ROOT / "aicrm_next" / "admin_jobs" / "application.py").read_text(encoding="utf-8")

    assert 'source_type == "operation_task"' not in source
    assert '"运营任务"' not in source
