from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        target_name = None
        value = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_name = target.id
                    value = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        if target_name == name and value is not None:
            return ast.literal_eval(value)
    raise AssertionError(f"{name} assignment not found")


def _migration_revisions() -> dict[str, Any]:
    revisions: dict[str, Any] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _literal_assignment(tree, "revision")
        down_revision = _literal_assignment(tree, "down_revision")
        assert revision not in revisions, f"duplicate Alembic revision id {revision}"
        revisions[revision] = {"path": path, "down_revision": down_revision}
    return revisions


def _parents(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)):
        return [str(item) for item in value]
    raise AssertionError(f"unsupported down_revision value: {value!r}")


def test_all_alembic_down_revisions_exist() -> None:
    revisions = _migration_revisions()

    missing = {
        revision: parent
        for revision, item in revisions.items()
        for parent in _parents(item["down_revision"])
        if parent not in revisions
    }

    assert missing == {}


def test_alembic_chain_keeps_0014_parent_available() -> None:
    revisions = _migration_revisions()

    assert "0013" in revisions
    assert revisions["0014"]["down_revision"] == "0013"
    assert revisions["0013"]["down_revision"] == "0012_wechat_pay_products"


def test_alembic_commands_can_walk_revision_graph() -> None:
    for args in (("heads",), ("history", "--verbose")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "is not present" not in result.stderr
        assert "KeyError" not in result.stderr
