from __future__ import annotations

import json
from typing import Any

from .service import LegacyWebhookCleanupService


def run_due_cli(*, dry_run: bool = True, limit: int = 50, operator: str = "cli") -> dict[str, Any]:
    return LegacyWebhookCleanupService().run_due(dry_run=dry_run, limit=limit, operator=operator)


def print_run_due_result(*, dry_run: bool = True, limit: int = 50, operator: str = "cli") -> None:
    print(json.dumps(run_due_cli(dry_run=dry_run, limit=limit, operator=operator), ensure_ascii=False, default=str))
