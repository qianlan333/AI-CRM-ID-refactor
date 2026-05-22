from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_DOCS = [
    "docs/legacy_retirement_plan.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
    "docs/legacy_delete_batches.md",
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_legacy_shell_dependency_inventory.md",
    "docs/d8_legacy_shell_allowed_fallback_matrix.md",
    "docs/d8_1_legacy_fallback_route_matrix.md",
    "docs/d8_slim_duplicate_inventory.md",
]
FORBIDDEN_STATUS_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _status_text() -> str:
    return "\n".join(_read(path) for path in STATUS_DOCS)


def test_openclaw_repo_path_status_matches_d9_6_deletion_record() -> None:
    text = _status_text()
    assert not (REPO_ROOT / "openclaw_service").exists()
    assert "D9.6 records `openclaw_service/` as absent" in text
    assert "repo-side `openclaw_service/` is absent" in text
    assert "no reintroduction is allowed" in text

    stale_patterns = [
        r"`openclaw_service/`[^.\n|]*(?:remains|remain|retained|frozen|still exists|in place)",
        r"OpenClaw service retained",
        r"`openclaw_service/LEGACY_FROZEN.md` remain",
    ]
    for pattern in stale_patterns:
        assert not re.search(pattern, text, flags=re.IGNORECASE), pattern


def test_openclaw_postgres_service_is_only_db_env_service() -> None:
    text = _status_text()
    assert "openclaw-wecom-postgres.service" in text
    assert "database/environment service" in text
    assert "is not the OpenClaw adapter or repo shim" in text


def test_d8_legacy_shell_fallback_remains_retained_without_openclaw_repo_shim() -> None:
    text = _status_text()
    assert (REPO_ROOT / "legacy_flask_app.py").exists()
    assert (REPO_ROOT / "wecom_ability_service").exists()
    assert "legacy Flask fallback package" in text
    assert "D8.2 preflight" in text
    assert "does not register runtime enforcement" in text
    assert "D8.3-D8.5" in text
    assert "not restored on current main" in text


def test_status_docs_do_not_claim_forbidden_readiness_markers() -> None:
    for path in STATUS_DOCS:
        text = _read(path)
        for marker in FORBIDDEN_STATUS_MARKERS:
            assert marker not in text, path
