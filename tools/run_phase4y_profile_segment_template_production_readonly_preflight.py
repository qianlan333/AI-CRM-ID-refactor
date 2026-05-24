#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE4Y_YAML = ROOT / "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.yaml"
PHASE4X_YAML = ROOT / "docs/development/phase_4x_profile_segment_template_production_readonly_final_gate.yaml"
APPROVAL_ENV = "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"
CONFIG_REVIEW_ENV = "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"
BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
PRODUCTION_DB_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"
ALLOWED_STATUSES = {"pending", "completed", "blocked", "not_applicable"}
CLOSURE_ITEMS = (
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "db_config_owner_approval",
    "business_owner_approval",
    "rollback_owner_assigned",
    "dry_run_operator_assigned",
    "release_config_reviewer_approval",
    "security_data_reviewer_approval",
    "production_config_review_completed",
    "production_db_env_confirmed",
    "read_only_flags_confirmed",
    "evidence_path_confirmed",
    "fallback_validation_plan_confirmed",
    "secret_redaction_confirmed",
    "pii_redaction_confirmed",
)
OWNER_ITEMS = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "db_config_owner_approval",
    "business_owner_approval",
    "rollback_owner_assigned",
    "dry_run_operator_assigned",
    "release_config_reviewer_approval",
    "security_data_reviewer_approval",
}
CONFIG_ITEMS = {
    "production_config_review_completed",
    "production_db_env_confirmed",
    "read_only_flags_confirmed",
}
EVIDENCE_ITEMS = {
    "evidence_path_confirmed",
    "fallback_validation_plan_confirmed",
    "secret_redaction_confirmed",
    "pii_redaction_confirmed",
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _strip_yaml_comments(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_yaml_comments(raw)
        if stripped.strip():
            lines.append((len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))
    return lines


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, current_text = lines[index]
    if current_indent < indent:
        return {}, index
    if current_text.startswith("- "):
        result: list[Any] = []
        while index < len(lines):
            line_indent, text = lines[index]
            if line_indent != indent or not text.startswith("- "):
                break
            item_text = text[2:].strip()
            index += 1
            if not item_text:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                result.append(value)
                continue
            if ":" not in item_text:
                result.append(_parse_scalar(item_text))
                continue
            key, raw_value = item_text.split(":", 1)
            item: dict[str, Any] = {}
            raw_value = raw_value.strip()
            if raw_value:
                item[key.strip()] = _parse_scalar(raw_value)
            else:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                item[key.strip()] = value
            result.append(item)
        return result, index
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def _load_yaml_without_dependency(path: Path) -> dict[str, Any]:
    data, _ = _parse_yaml_block(_yaml_lines(path.read_text(encoding="utf-8")), 0, 0)
    return data if isinstance(data, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(path)


def _load_status_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text) or {}
        except ModuleNotFoundError:
            data = _load_yaml_without_dependency(path)
    if not isinstance(data, dict):
        return {}
    closure = data.get("closure_items") if isinstance(data.get("closure_items"), dict) else data
    return dict(closure) if isinstance(closure, dict) else {}


def _redacted_db_presence() -> str | None:
    return "<redacted-present>" if os.environ.get(PRODUCTION_DB_ENV) else None


def _default_closure() -> dict[str, str]:
    data = _load_yaml(PHASE4Y_YAML)
    closure = data.get("closure_items") if isinstance(data.get("closure_items"), dict) else {}
    return {field: str(closure.get(field, "pending")) for field in CLOSURE_ITEMS}


def _merge_status_file(closure: dict[str, str], path: str | None) -> tuple[dict[str, str], list[str]]:
    invalid: list[str] = []
    if not path:
        return closure, invalid
    raw = _load_status_file(Path(path))
    for field, value in raw.items():
        if field not in closure:
            invalid.append(f"unknown closure item: {field}")
            continue
        status = str(value).strip()
        if status not in ALLOWED_STATUSES:
            invalid.append(f"invalid status for {field}: {status}")
            closure[field] = "blocked"
            continue
        closure[field] = status
    return closure, invalid


def _apply_env_and_args(closure: dict[str, str], args: argparse.Namespace) -> None:
    if os.environ.get(APPROVAL_ENV) == "1" and closure["automation_engine_owner_approval"] == "pending":
        closure["automation_engine_owner_approval"] = "completed"
    if os.environ.get(CONFIG_REVIEW_ENV) == "1" and closure["production_config_review_completed"] == "pending":
        closure["production_config_review_completed"] = "completed"
    if os.environ.get(PRODUCTION_DB_ENV) and closure["production_db_env_confirmed"] == "pending":
        closure["production_db_env_confirmed"] = "completed"
    if args.read_only and args.confirm_no_writes and closure["read_only_flags_confirmed"] == "pending":
        closure["read_only_flags_confirmed"] = "completed"


def _env_summary(args: argparse.Namespace) -> dict[str, Any]:
    backend = (os.environ.get(BACKEND_ENV) or "").strip()
    return {
        APPROVAL_ENV: os.environ.get(APPROVAL_ENV) == "1",
        CONFIG_REVIEW_ENV: os.environ.get(CONFIG_REVIEW_ENV) == "1",
        BACKEND_ENV: backend == "sqlalchemy",
        PRODUCTION_DB_ENV: bool(os.environ.get(PRODUCTION_DB_ENV)),
        "production_db_env_redacted": _redacted_db_presence(),
        "--read-only": bool(args.read_only),
        "--confirm-no-writes": bool(args.confirm_no_writes),
    }


def _status_complete(status: str) -> bool:
    return status in {"completed", "not_applicable"}


def _items_for_action(fields: set[str], closure: dict[str, str]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for field in CLOSURE_ITEMS:
        if field in fields and not _status_complete(closure[field]):
            actions.append({"item": f"complete {field}"})
    return actions


def _build_readiness(closure: dict[str, str], invalid_statuses: list[str], env: dict[str, Any]) -> dict[str, Any]:
    missing = [{"item": f"{field}_{closure[field]}"} for field in CLOSURE_ITEMS if not _status_complete(closure[field])]
    blockers = [{"item": f"{field}_blocked"} for field in CLOSURE_ITEMS if closure[field] == "blocked"]
    blockers.extend({"item": item} for item in invalid_statuses)
    if not env[APPROVAL_ENV]:
        blockers.append({"item": f"{APPROVAL_ENV}=1_missing"})
    if not env[CONFIG_REVIEW_ENV]:
        blockers.append({"item": f"{CONFIG_REVIEW_ENV}=1_missing"})
    if not env[BACKEND_ENV]:
        blockers.append({"item": f"{BACKEND_ENV}=sqlalchemy_missing"})
    if not env[PRODUCTION_DB_ENV]:
        blockers.append({"item": f"{PRODUCTION_DB_ENV}_missing"})
    if not env["--read-only"] or not env["--confirm-no-writes"]:
        blockers.append({"item": "read_only_no_write_args_missing"})
    ready = (
        not missing
        and not blockers
        and env[APPROVAL_ENV]
        and env[CONFIG_REVIEW_ENV]
        and env[BACKEND_ENV]
        and env[PRODUCTION_DB_ENV]
        and env["--read-only"]
        and env["--confirm-no-writes"]
    )
    return {
        "ready_for_phase_4z_readonly_dry_run_execution": ready,
        "missing_items": missing,
        "blockers": blockers,
        "next_owner_actions": _items_for_action(OWNER_ITEMS, closure) or [{"item": "owner closure complete"}],
        "next_config_actions": _items_for_action(CONFIG_ITEMS, closure) or [{"item": "config closure complete"}],
        "next_evidence_actions": _items_for_action(EVIDENCE_ITEMS, closure) or [{"item": "evidence closure complete"}],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    closure = _default_closure()
    phase4x_loaded = PHASE4X_YAML.exists()
    closure, invalid_statuses = _merge_status_file(closure, args.closure_status_file)
    _apply_env_and_args(closure, args)
    env = _env_summary(args)
    readiness = _build_readiness(closure, invalid_statuses, env)
    return {
        "ok": True,
        "status": "phase_4y_production_readonly_preflight_no_execution",
        "timestamp": datetime.now(UTC).isoformat(),
        "phase_4x_yaml_loaded": phase4x_loaded,
        "closure_status_file": args.closure_status_file or "",
        "ready_for_phase_4z_readonly_dry_run_execution": readiness["ready_for_phase_4z_readonly_dry_run_execution"],
        "closure_items": closure,
        "env_and_arg_summary": env,
        "missing_items": readiness["missing_items"],
        "blockers": readiness["blockers"],
        "next_owner_actions": readiness["next_owner_actions"],
        "next_config_actions": readiness["next_config_actions"],
        "next_evidence_actions": readiness["next_evidence_actions"],
        "production_data_connected": False,
        "dry_run_executed": False,
        "writes_attempted": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "db_url_secret_redacted": True,
        "raw_payload_exported": False,
        "raw_pii_exported": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4Y Profile Segment Template Production Read-Only Preflight",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- ready_for_phase_4z_readonly_dry_run_execution: {str(report.get('ready_for_phase_4z_readonly_dry_run_execution')).lower()}",
        f"- production_data_connected: {str(report.get('production_data_connected')).lower()}",
        f"- dry_run_executed: {str(report.get('dry_run_executed')).lower()}",
        f"- writes_attempted: {str(report.get('writes_attempted')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- db_url_secret_redacted: {str(report.get('db_url_secret_redacted')).lower()}",
        "",
        "## Missing Items",
    ]
    missing = report.get("missing_items") or []
    lines.extend(f"- {item.get('item')}" for item in missing) if missing else lines.append("- none")
    lines.extend(["", "## Blockers"])
    blockers = report.get("blockers") or []
    lines.extend(f"- {item.get('item')}" for item in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Next Owner Actions"])
    lines.extend(f"- {item.get('item')}" for item in report.get("next_owner_actions", []))
    lines.extend(["", "## Next Config Actions"])
    lines.extend(f"- {item.get('item')}" for item in report.get("next_config_actions", []))
    lines.extend(["", "## Next Evidence Actions"])
    lines.extend(f"- {item.get('item')}" for item in report.get("next_evidence_actions", []))
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Phase 4Y production read-only dry-run preflight evidence without DB access.")
    parser.add_argument("--closure-status-file")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--confirm-no-writes", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"overall: {'PASS' if report.get('ok') else 'FAIL'}")
    print(f"ready_for_phase_4z_readonly_dry_run_execution: {str(report.get('ready_for_phase_4z_readonly_dry_run_execution')).lower()}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
