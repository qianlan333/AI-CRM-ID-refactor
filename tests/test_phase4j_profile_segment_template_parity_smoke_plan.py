from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tools import check_phase4j_profile_segment_template_parity_smoke_plan as checker


ROOT = Path(__file__).resolve().parents[1]


def test_phase4j_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report.get("blockers")


def test_top_level_authorization_flags_are_false() -> None:
    data = checker.load_yaml()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_read_parity_includes_required_cases() -> None:
    matrix = checker.load_yaml()["parity_matrix"]
    names = {item["name"] for item in matrix["read"]}
    assert checker.READ_PARITY <= names


def test_write_parity_includes_required_cases() -> None:
    matrix = checker.load_yaml()["parity_matrix"]
    names = {item["name"] for item in matrix["write"]}
    assert checker.WRITE_PARITY <= names


def test_smoke_levels_zero_to_four_exist_and_only_zero_authorized() -> None:
    levels = {int(item["level"]): item for item in checker.load_yaml()["smoke_levels"]}
    assert set(levels) == {0, 1, 2, 3, 4}
    assert levels[0]["authorized_now"] is True
    for level in (1, 2, 3, 4):
        assert levels[level]["authorized_now"] is False
        assert levels[level]["requires_owner_approval"] is True


def test_feature_flags_preserve_memory_default() -> None:
    flags = checker.load_yaml()["feature_flags"]
    assert flags["default_backend"] == "memory"
    assert "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND" in flags["sql_backend_flags"]
    assert "PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND" in flags["sql_backend_flags"]
    assert "AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL" in flags["database_url_flags"]
    assert "AICRM_NEXT_TEST_DATABASE_URL" in flags["database_url_flags"]
    assert flags["production_auto_enable"] is False


def test_owner_approvals_pending() -> None:
    approval = checker.load_yaml()["owner_approval"]
    for field in checker.OWNER_FIELDS:
        assert approval[field] == "pending"


def test_phase4k_recommendation_keeps_production_switch_blocked() -> None:
    recommendation = checker.load_yaml()["phase_4k_recommendation"]
    assert recommendation["recommended_next_step"]
    assert recommendation["direct_route_switch_allowed"] is False
    assert recommendation["production_write_canary_allowed"] is False
    assert recommendation["production_repository_enablement_without_owner_approval"] is False


def test_no_runtime_files_changed_if_git_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    forbidden = [
        path
        for path in changed
        if checker._is_protected_runtime_file(path)
        and path not in checker.ALLOWED_CHANGED_FILES
    ]
    assert not forbidden


def test_docs_do_not_claim_execution_or_cutover() -> None:
    text = checker.PLAN_MD.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"production repository enabled",
        r"production route switch authorized",
        r"smoke executed",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, text)
