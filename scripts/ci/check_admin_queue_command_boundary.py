#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTES = {
    "aicrm_next/platform_foundation/internal_events/api.py": (
        "run_internal_event_due",
        "run_internal_event_consumer",
    ),
    "aicrm_next/platform_foundation/external_effects/api.py": (
        "run_external_effect_due",
    ),
    "aicrm_next/platform_foundation/webhook_inbox/api.py": (
        "dispatch_webhook_inbox_item",
        "run_webhook_inbox_due",
    ),
}
FORBIDDEN_CALLS = {
    "dispatch_one",
    "dispatch_one_consumer",
    "dispatch_row",
    "run_due",
    "_adapter_registry",
    "_continuation_registry",
    "_worker",
}
FORBIDDEN_NAMES = {
    "ExternalEffectWorker",
    "InternalEventWorker",
    "WeComCallbackInboxWorker",
}
COMMAND_CALLS = {
    "_accepted_command_response",
    "submit_manual_queue_command",
}


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def collect_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative_path, route_names in ROUTES.items():
        path = root / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for route_name in route_names:
            route = functions.get(route_name)
            if route is None:
                errors.append(f"{relative_path}:{route_name}: execute route is missing")
                continue
            calls = {
                _call_name(node)
                for node in ast.walk(route)
                if isinstance(node, ast.Call)
            }
            names = {
                node.id
                for node in ast.walk(route)
                if isinstance(node, ast.Name)
            }
            forbidden_calls = sorted(calls & FORBIDDEN_CALLS)
            forbidden_names = sorted(names & FORBIDDEN_NAMES)
            if forbidden_calls:
                errors.append(
                    f"{relative_path}:{route_name}: inline queue/provider calls are forbidden: {forbidden_calls}"
                )
            if forbidden_names:
                errors.append(
                    f"{relative_path}:{route_name}: provider worker ownership is forbidden: {forbidden_names}"
                )
            if not (calls & COMMAND_CALLS or names & COMMAND_CALLS):
                errors.append(
                    f"{relative_path}:{route_name}: execute route must submit a QueueRuntimeCommandService command"
                )
    return errors


def main() -> int:
    violations = collect_errors()
    if violations:
        print("\n".join(violations))
        return 1
    print("admin queue execute routes are durable-command only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
