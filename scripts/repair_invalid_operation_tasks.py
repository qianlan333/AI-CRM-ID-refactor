from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import operation_task_repo as task_repo


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run/apply bounded repair for invalid active operation tasks.")
    parser.add_argument("--program-id", type=int, required=True)
    parser.add_argument("--task-id", type=int, action="append", required=True)
    parser.add_argument("--action", choices=["pause", "patch-agent-fallback"], required=True)
    parser.add_argument("--fallback-content", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--operator-id", default="invalid_operation_task_repair")
    return parser.parse_args(argv)


def repair(args: argparse.Namespace) -> dict[str, Any]:
    dry_run = not bool(args.apply) or bool(args.dry_run)
    results: list[dict[str, Any]] = []
    for task_id in sorted(dict.fromkeys(int(item) for item in args.task_id or [])):
        task = task_repo.get_task(task_id)
        if not task or int(task.get("program_id") or 0) != int(args.program_id):
            results.append({"task_id": task_id, "ok": False, "reason": "task_not_found"})
            continue
        after = dict(task)
        if args.action == "pause":
            after["status"] = "paused"
        elif args.action == "patch-agent-fallback":
            fallback = str(args.fallback_content or "").strip()
            if not fallback:
                results.append({"task_id": task_id, "ok": False, "reason": "fallback_content_required"})
                continue
            agent = dict(after.get("agent_config_json") or {})
            agent["fallback_content"] = fallback
            after["agent_config_json"] = agent
        after["updated_by"] = args.operator_id
        result = {
            "task_id": task_id,
            "task_name": task.get("task_name") or "",
            "action": args.action,
            "dry_run": dry_run,
            "before": {"status": task.get("status"), "agent_config_json": task.get("agent_config_json")},
            "after": {"status": after.get("status"), "agent_config_json": after.get("agent_config_json")},
            "ok": True,
        }
        if not dry_run:
            task_repo.update_task(task_id, after)
        results.append(result)
    if not dry_run:
        get_db().commit()
    return {"ok": True, "dry_run": dry_run, "program_id": int(args.program_id), "results": results}


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    app = create_app()
    with app.app_context():
        result = repair(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
