from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import tools.check_phase4af_action_templates_local_parity_harness as checker
import tools.run_phase4af_action_templates_local_parity as harness


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/run_phase4af_action_templates_local_parity.py"
DOC = ROOT / "docs/development/phase_4af_action_templates_local_parity_harness.md"
YAML = ROOT / "docs/development/phase_4af_action_templates_local_parity_harness.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_harness_tool_exists_and_supports_outputs() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    assert "--output-json" in text
    assert "--output-md" in text


def test_default_harness_report_is_fixture_evidence_only() -> None:
    report = harness.run_harness()
    assert report["ok"] is True
    assert report["mode"] == "local_fixture_parity"
    assert report["fixture_evidence_only"] is True
    assert report["production_data_used"] is False
    assert report["production_route_owner_changed"] is False
    assert report["production_compat_changed"] is False


def test_harness_never_connects_db_or_falls_back_to_database_url() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    forbidden = ["create_engine", "psycopg", "sqlalchemy", "DATABASE_URL"]
    for token in forbidden:
        assert token not in text


def test_harness_does_not_call_legacy_service() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    assert "wecom_ability_service" not in text
    assert "DeepSeek" not in text
    assert "llm_adapter" not in text


def test_local_parity_matrix_complete() -> None:
    data = checker.load_yaml(YAML)
    read_items = set(data["harness_matrix"]["read"])
    create_items = set(data["harness_matrix"]["create"])

    assert checker.REQUIRED_READ_MATRIX <= read_items
    assert checker.REQUIRED_CREATE_MATRIX <= create_items


def test_production_fixture_post_success_blocked() -> None:
    import pytest

    pytest.importorskip("fastapi")
    report = harness.run_harness()
    production_guard = [
        item for item in report["details"] if item["name"] == "production_fixture_write_blocked" and item["status"] == "passed"
    ]
    assert production_guard


def test_excluded_routes_remain_excluded() -> None:
    data = checker.load_yaml(YAML)
    assert all(data["excluded"][field] is True for field in checker.REQUIRED_EXCLUDED_TRUE)
    text = HARNESS.read_text(encoding="utf-8")
    for forbidden in ("action-templates/generate", "action-templates/from-workflow", ".delete(", ".put("):
        assert forbidden not in text


def test_side_effect_safety_false() -> None:
    report = harness.run_harness()
    safety = report["side_effect_safety"]
    assert safety
    assert all(value is False for value in safety.values())


def test_no_runtime_files_changed_if_git_diff_available() -> None:
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
    assert "aicrm_next/main.py" not in changed
    assert "aicrm_next/production_compat/api.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"production parity",
        r"production repository enabled",
        r"production write authorized",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text) is None, pattern
