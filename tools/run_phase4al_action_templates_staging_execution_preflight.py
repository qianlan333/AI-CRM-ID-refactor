#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
YAML_DOC = ROOT / "docs/development/phase_4al_action_templates_staging_execution_ready_gate.yaml"
MODE = "staging_execution_preflight"
STAGING_DB_ENV = "AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL"
REPO_BACKEND_ENV = "AICRM_ACTION_TEMPLATES_REPO_BACKEND"
SMOKE_APPROVAL_ENV = "AICRM_PHASE4AK_STAGING_SMOKE_APPROVED"
WRITE_APPROVAL_ENV = "AICRM_PHASE4AK_STAGING_WRITE_APPROVED"
ALLOWED_DB_MARKERS = ("staging", "stage", "test", "local", "dev")
FORBIDDEN_DB_MARKERS = ("prod", "production", "primary", "master")
REQUIRED_CLOSURE_ITEMS = (
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "staging_db_config_owner_approval",
    "rollback_owner_assigned",
    "smoke_operator_assigned",
    "staging_db_env_confirmed",
    "staging_db_url_safety_confirmed",
    "repo_backend_confirmed",
    "read_only_preflight_confirmed",
    "write_smoke_approval_confirmed",
    "safe_namespace_confirmed",
    "evidence_path_confirmed",
    "cleanup_strategy_confirmed",
    "side_effect_safety_confirmed",
)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "None"}:
        return None
    if value == "[]":
        return []
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


def _load_yaml_without_dependency(text: str) -> dict[str, Any]:
    data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
    return data if isinstance(data, dict) else {}


def _load_structured_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(text)


def _redact_url(value: str) -> str:
    if not value:
        return ""
    if "@" in value and "://" in value:
        scheme, rest = value.split("://", 1)
        host_part = rest.split("@", 1)[1]
        return f"{scheme}://<redacted>@{host_part}"
    return value[:16] + "<redacted>" if len(value) > 24 else "<redacted>"


def db_url_safety(db_url: str | None = None) -> dict[str, Any]:
    value = str(db_url if db_url is not None else os.getenv(STAGING_DB_ENV, "") or "").strip()
    lowered = value.lower()
    allowed_hits = [marker for marker in ALLOWED_DB_MARKERS if marker in lowered]
    forbidden_hits = [marker for marker in FORBIDDEN_DB_MARKERS if marker in lowered]
    present = bool(value)
    safe = present and bool(allowed_hits) and not forbidden_hits
    if not present:
        reason = "missing_staging_db_url"
    elif forbidden_hits:
        reason = "forbidden_marker_present"
    elif not allowed_hits:
        reason = "missing_allowed_marker"
    else:
        reason = "safe_staging_db_url"
    return {
        "present": present,
        "safe": safe,
        "reason": reason,
        "allowed_markers": list(ALLOWED_DB_MARKERS),
        "forbidden_markers": list(FORBIDDEN_DB_MARKERS),
        "allowed_hits": allowed_hits,
        "forbidden_hits": forbidden_hits,
        "redacted_url": _redact_url(value),
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "approved", "confirmed", "assigned", "complete", "completed", "ready"}


def _closure_items_from_status(status: dict[str, Any]) -> dict[str, str]:
    source = status.get("closure_form") if isinstance(status.get("closure_form"), dict) else status
    return {item: "complete" if _truthy((source or {}).get(item)) else "pending" for item in REQUIRED_CLOSURE_ITEMS}


def _default_closure_items() -> dict[str, str]:
    return {item: "pending" for item in REQUIRED_CLOSURE_ITEMS}


def _action_list(items: list[str], prefix: str) -> list[str]:
    return [f"{prefix}: {item}" for item in items]


def run_preflight(
    *,
    closure_status_file: str | None = None,
    read_only: bool = False,
    confirm_no_production: bool = False,
    confirm_no_external_calls: bool = False,
) -> dict[str, Any]:
    status_data: dict[str, Any] = {}
    if closure_status_file:
        status_data = _load_structured_file(Path(closure_status_file))
    closure_items = _closure_items_from_status(status_data) if status_data else _default_closure_items()
    missing_items = [item for item, value in closure_items.items() if value != "complete"]
    blockers: list[str] = []
    if missing_items:
        blockers.extend(missing_items)
    safety = db_url_safety()
    if not safety["safe"]:
        blockers.append(f"db_url_safety:{safety['reason']}")
    if str(os.getenv(REPO_BACKEND_ENV, "") or "").strip().lower() != "sqlalchemy":
        blockers.append("repo_backend:not_sqlalchemy")
    if not _truthy(os.getenv(SMOKE_APPROVAL_ENV)):
        blockers.append("staging_smoke_approval:missing")
    if not read_only:
        blockers.append("cli:read_only_confirmation_missing")
    if not confirm_no_production:
        blockers.append("cli:no_production_confirmation_missing")
    if not confirm_no_external_calls:
        blockers.append("cli:no_external_calls_confirmation_missing")
    if _truthy(os.getenv(WRITE_APPROVAL_ENV)) and closure_items.get("write_smoke_approval_confirmed") != "complete":
        blockers.append("write_approval_env_present_without_closure_confirmation")
    ready = not blockers
    return {
        "ok": True,
        "mode": MODE,
        "ready_for_phase_4am_staging_execution": ready,
        "closure_items": closure_items,
        "missing_items": missing_items,
        "blockers": blockers,
        "next_owner_actions": _action_list([item for item in missing_items if "owner" in item or "operator" in item], "complete owner approval"),
        "next_config_actions": _action_list([item for item in missing_items if "env" in item or "backend" in item or "db" in item], "complete staging config"),
        "next_evidence_actions": _action_list([item for item in missing_items if "evidence" in item or "preflight" in item or "safety" in item or "cleanup" in item], "complete evidence guard"),
        "db_url_safety": safety,
        "production_data_connected": False,
        "staging_smoke_executed": False,
        "writes_attempted": False,
        "lower_runner_called": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "production_approval_claimed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4AL Action Templates Staging Execution Preflight",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- ready_for_phase_4am_staging_execution: {str(report['ready_for_phase_4am_staging_execution']).lower()}",
        f"- production_data_connected: {str(report['production_data_connected']).lower()}",
        f"- staging_smoke_executed: {str(report['staging_smoke_executed']).lower()}",
        f"- lower_runner_called: {str(report['lower_runner_called']).lower()}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- none")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4AL action templates staging execution preflight.")
    parser.add_argument("--closure-status-file")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--confirm-no-production", action="store_true")
    parser.add_argument("--confirm-no-external-calls", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = run_preflight(
        closure_status_file=args.closure_status_file,
        read_only=args.read_only,
        confirm_no_production=args.confirm_no_production,
        confirm_no_external_calls=args.confirm_no_external_calls,
    )
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"ready_for_phase_4am_staging_execution: {str(report['ready_for_phase_4am_staging_execution']).lower()}")
    print(f"ok: {str(report['ok']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
