from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_repo_root_on_path() -> Path:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return REPO_ROOT


def print_json(payload: Any, *, indent: int | None = None) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str, indent=indent))
