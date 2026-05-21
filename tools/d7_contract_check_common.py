from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

Json = dict[str, Any]

DEFAULT_RESULT_FIELDS = {
    "ok",
    "adapter",
    "mode",
    "operation",
    "idempotency_key",
    "target",
    "result",
    "audit_id",
    "side_effect_executed",
    "error_code",
    "error_message",
}


def resolve_project_root(file: str) -> Path:
    return Path(file).resolve().parents[1]


def ensure_project_root_on_path(project_root: Path) -> None:
    root = str(project_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def project_path(project_root: Path, relpath: str) -> Path:
    return project_root / relpath


def read_project_text(project_root: Path, relpath: str) -> str:
    return project_path(project_root, relpath).read_text(encoding="utf-8")


def collect_missing_files(project_root: Path, relpaths: list[str], blockers: list[Json], *, reason: str) -> list[Json]:
    missing = [{"path": relpath} for relpath in relpaths if not project_path(project_root, relpath).exists()]
    for item in missing:
        blockers.append({"reason": reason, "path": item["path"]})
    return missing


def check_adapter_methods(
    adapters_module: Any,
    required_methods: dict[str, list[str]],
    blockers: list[Json],
    *,
    contracts_module: Any | None = None,
) -> Json:
    result: Json = {}
    for class_name, methods in required_methods.items():
        contract_exists = None
        if contracts_module is not None:
            contract_exists = hasattr(contracts_module, f"{class_name}Contract")
        cls = getattr(adapters_module, class_name, None)
        missing = [method for method in methods if cls is None or not callable(getattr(cls, method, None))]
        item: Json = {"exists": cls is not None, "missing_methods": missing}
        if contract_exists is not None:
            item["contract_exists"] = contract_exists
            if not contract_exists:
                blockers.append({"reason": "missing_adapter_contract", "class": class_name})
        if cls is None:
            blockers.append({"reason": "missing_adapter_class", "class": class_name})
        for method in missing:
            blockers.append({"reason": "missing_adapter_method", "class": class_name, "method": method})
        result[class_name] = item
    return result


@contextmanager
def clean_environment(names: list[str]) -> Iterator[None]:
    saved = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def check_adapter_mode_guards(
    module: Any,
    production_flags: dict[str, str],
    sample_call: Callable[[Any], Json],
    blockers: list[Json],
    defaults: Json,
) -> Json:
    guards: Json = {"defaults": defaults, "production_without_flag": {}, "production_with_flag": {}, "disabled": {}}
    for class_name, flag in production_flags.items():
        cls = getattr(module, class_name)
        disabled_result = sample_call(cls("disabled"))
        guards["disabled"][class_name] = disabled_result["error_code"]
        if disabled_result["error_code"] != "adapter_disabled":
            blockers.append({"reason": "disabled_mode_not_stable", "class": class_name, "error_code": disabled_result["error_code"]})
        os.environ.pop(flag, None)
        guarded = sample_call(cls("production"))
        guards["production_without_flag"][class_name] = guarded["error_code"]
        if guarded["error_code"] != "production_guard_failed":
            blockers.append({"reason": "production_mode_not_guarded", "class": class_name, "error_code": guarded["error_code"]})
        os.environ[flag] = "true"
        not_implemented = sample_call(cls("production"))
        guards["production_with_flag"][class_name] = not_implemented["error_code"]
        if not_implemented["error_code"] != "production_not_implemented":
            blockers.append({"reason": "production_mode_not_fail_closed", "class": class_name, "error_code": not_implemented["error_code"]})
        os.environ.pop(flag, None)
    return guards


def check_fake_operation_result_safety(
    results: list[Json],
    repeated: Json,
    repeated_again: Json,
    audit_events: list[Json],
    blockers: list[Json],
    *,
    required_fields: set[str] = DEFAULT_RESULT_FIELDS,
) -> tuple[Json, Json, Json]:
    missing_fields = {item["adapter"]: sorted(required_fields - set(item)) for item in results if required_fields - set(item)}
    if missing_fields:
        blockers.append({"reason": "result_shape_missing_fields", "missing_fields": missing_fields})
    side_effects = {item["adapter"]: item["side_effect_executed"] for item in results}
    if any(side_effects.values()):
        blockers.append({"reason": "side_effect_executed_true", "side_effects": side_effects})
    deterministic = repeated["result"] == repeated_again["result"]
    if not deterministic:
        blockers.append({"reason": "idempotency_not_deterministic"})
    audit_ok = len(audit_events) >= len(results) and all(
        {"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event)
        for event in audit_events
    )
    if not audit_ok:
        blockers.append({"reason": "audit_record_shape_invalid"})
    return {"deterministic_repeated_result": deterministic}, {"audit_records": len(audit_events), "shape_ok": audit_ok}, {"side_effect_executed": side_effects}


def scan_docs_for_forbidden_markers(
    project_root: Path,
    relpaths: list[str],
    markers: list[str],
    blockers: list[Json],
) -> tuple[list[Json], list[Json]]:
    missing_docs: list[Json] = []
    forbidden: list[Json] = []
    for relpath in relpaths:
        path = project_path(project_root, relpath)
        if not path.exists():
            missing_docs.append({"path": relpath})
            blockers.append({"reason": "missing_doc", "path": relpath})
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in text:
                forbidden.append({"path": relpath, "marker": marker})
                blockers.append({"reason": "forbidden_status_marker", "path": relpath, "marker": marker})
    return missing_docs, forbidden


def write_json_report(report: Json, path: Path, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n", encoding="utf-8")


def write_markdown_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
