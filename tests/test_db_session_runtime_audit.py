from __future__ import annotations

import re
from pathlib import Path


RUNTIME_SQLALCHEMY_FACTORY_ALLOWLIST = {
    Path("aicrm_next/shared/db_session.py"): "single process-level Engine and SessionFactory owner",
}


def test_runtime_create_engine_and_sessionmaker_are_centralized() -> None:
    root = Path("aicrm_next")
    pattern = re.compile(r"\b(create_engine|sessionmaker)\s*\(")
    hits: list[str] = []
    for path in root.rglob("*.py"):
        relative_path = path.relative_to(Path("."))
        if "migrations" in relative_path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line) and relative_path not in RUNTIME_SQLALCHEMY_FACTORY_ALLOWLIST:
                hits.append(f"{relative_path}:{line_no}: {line.strip()}")

    assert hits == []
