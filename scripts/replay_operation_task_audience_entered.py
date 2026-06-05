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
from wecom_ability_service.domains.automation_conversion.operation_task_replay_service import (
    replay_audience_entered_operation_task,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run/apply a bounded operation_task audience_entered replay.")
    parser.add_argument("--program-id", type=int, required=True)
    parser.add_argument("--external-userid", default="")
    parser.add_argument("--member-id", type=int, default=0)
    parser.add_argument("--audience-entry-id", type=int, default=0)
    parser.add_argument("--task-id", type=int, action="append", required=True)
    parser.add_argument("--apply", action="store_true", help="Write retry execution/job. Omitted means dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run; default when --apply is omitted.")
    parser.add_argument("--allow-failed-empty-execution-retry", action="store_true")
    parser.add_argument("--operator-id", default="operation_task_replay")
    return parser.parse_args(argv)


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    dry_run = not bool(args.apply)
    if args.dry_run:
        dry_run = True
    app = create_app()
    with app.app_context():
        result = replay_audience_entered_operation_task(
            program_id=int(args.program_id),
            external_userid=args.external_userid,
            member_id=int(args.member_id or 0),
            audience_entry_id=int(args.audience_entry_id or 0),
            task_ids=[int(item) for item in args.task_id or []],
            dry_run=dry_run,
            allow_failed_empty_execution_retry=bool(args.allow_failed_empty_execution_retry),
            operator_id=args.operator_id,
        )
    _emit(result)


if __name__ == "__main__":
    main()
