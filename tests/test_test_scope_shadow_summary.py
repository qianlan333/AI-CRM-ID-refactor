from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.summarize_test_scope_shadow import (
    load_reviewed_legacy_only_tests,
    render_markdown,
    summarize_shadow_reports,
)


pytestmark = pytest.mark.unit


def _report(
    *,
    legacy_tests: list[str],
    candidate_tests: list[str],
    candidate_full: bool,
    high_risk_reasons: list[str] | None = None,
    fallback_reasons: list[str] | None = None,
) -> dict:
    return {
        "mode": "shadow",
        "legacy": {
            "python_tests": legacy_tests,
            "needs_full_ci": candidate_full,
        },
        "candidate": {
            "python_tests": candidate_tests,
            "needs_full_ci": candidate_full,
            "high_risk_reasons": high_risk_reasons or [],
            "fallback_reasons": fallback_reasons or [],
        },
        "comparison": {
            "legacy_only_python_tests": sorted(set(legacy_tests) - set(candidate_tests)),
        },
    }


def _criteria(**overrides: int) -> dict[str, int]:
    values = {
        "minimum_pull_request_samples": 2,
        "minimum_observation_days": 1,
        "minimum_scoped_samples": 1,
        "minimum_high_risk_samples": 1,
        "maximum_normal_path_fallback_samples": 0,
        "maximum_high_risk_downgrades": 0,
        "maximum_unreviewed_legacy_only_tests": 0,
    }
    values.update(overrides)
    return values


def test_summary_deduplicates_pull_requests_and_requires_diverse_reviewed_evidence() -> None:
    reports = {
        101: _report(
            legacy_tests=["tests/test_context.py", "tests/test_global.py"],
            candidate_tests=["tests/test_context.py"],
            candidate_full=False,
        ),
        102: _report(
            legacy_tests=["tests/test_context.py", "tests/test_global.py"],
            candidate_tests=["tests/test_context.py"],
            candidate_full=False,
        ),
        201: _report(
            legacy_tests=["tests/test_callback.py", "tests/test_global.py"],
            candidate_tests=["tests/test_callback.py"],
            candidate_full=True,
            high_risk_reasons=["callbacks_and_external_effects"],
        ),
    }
    metadata = {
        101: {
            "run_id": 101,
            "event": "pull_request",
            "conclusion": "success",
            "pull_request_number": 10,
            "created_at": "2026-07-01T00:00:00Z",
            "head_sha": "a" * 40,
        },
        102: {
            "run_id": 102,
            "event": "pull_request",
            "conclusion": "success",
            "pull_request_number": 10,
            "created_at": "2026-07-02T00:00:00Z",
            "head_sha": "b" * 40,
        },
        201: {
            "run_id": 201,
            "event": "pull_request",
            "conclusion": "success",
            "pull_request_number": 20,
            "created_at": "2026-07-03T00:00:00Z",
            "head_sha": "c" * 40,
        },
    }

    summary = summarize_shadow_reports(
        reports,
        metadata,
        criteria=_criteria(),
        reviewed_legacy_only_tests={"tests/test_global.py"},
    )

    assert summary["eligible_pull_request_samples"] == 2
    assert [sample["run_id"] for sample in summary["samples"]] == [102, 201]
    assert [sample["pull_request_key"] for sample in summary["samples"]] == ["pr:10", "pr:20"]
    assert summary["observation_days"] == 1
    assert summary["scoped_samples"] == 1
    assert summary["high_risk_samples"] == 1
    assert summary["candidate_selection_reduction_ratio"] == 0.5
    assert summary["unreviewed_legacy_only_tests"] == []
    assert summary["automated_ready_for_explicit_cutover_review"] is True
    assert "READY FOR EXPLICIT REVIEW" in render_markdown(summary)


def test_summary_stays_in_shadow_for_fallbacks_unreviewed_tests_and_short_window() -> None:
    reports = {
        301: _report(
            legacy_tests=["tests/test_context.py", "tests/test_global.py"],
            candidate_tests=["tests/test_context.py"],
            candidate_full=True,
            fallback_reasons=["runtime_path_without_test_match"],
        )
    }
    metadata = {
        301: {
            "run_id": 301,
            "event": "pull_request",
            "conclusion": "success",
            "pull_request_number": 30,
            "created_at": "2026-07-03T00:00:00Z",
            "head_sha": "d" * 40,
        }
    }

    summary = summarize_shadow_reports(
        reports,
        metadata,
        criteria=_criteria(minimum_pull_request_samples=1, minimum_scoped_samples=0, minimum_high_risk_samples=0),
    )

    assert summary["fallback_samples"] == 1
    assert summary["unreviewed_legacy_only_tests"] == ["tests/test_global.py"]
    assert summary["gates"]["observation_days"]["passed"] is False
    assert summary["gates"]["normal_path_fallback_samples"]["passed"] is False
    assert summary["automated_ready_for_explicit_cutover_review"] is False
    assert "KEEP SHADOW MODE" in render_markdown(summary)


def test_summary_uses_head_branch_when_github_no_longer_links_a_merged_pr() -> None:
    reports = {
        401: _report(
            legacy_tests=["tests/test_context.py"],
            candidate_tests=["tests/test_context.py"],
            candidate_full=False,
        )
    }
    metadata = {
        401: {
            "run_id": 401,
            "event": "pull_request",
            "conclusion": "success",
            "pull_request_number": None,
            "head_branch": "codex/context-read-model",
            "created_at": "2026-07-03T00:00:00Z",
            "head_sha": "e" * 40,
        }
    }

    summary = summarize_shadow_reports(
        reports,
        metadata,
        criteria=_criteria(
            minimum_pull_request_samples=1,
            minimum_observation_days=0,
            minimum_high_risk_samples=0,
        ),
    )

    assert summary["eligible_pull_request_samples"] == 1
    assert summary["samples"][0]["pull_request_key"] == "branch:codex/context-read-model"


def test_review_inventory_requires_explicit_disposition_and_rationale(tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    review.write_text(
        '{"version":1,"reviews":[{"test_path":"tests/test_global.py","disposition":"legacy_overcoverage","rationale":"global contract stays in nightly"}]}',
        encoding="utf-8",
    )

    assert load_reviewed_legacy_only_tests(review) == {"tests/test_global.py"}

    review.write_text(
        '{"version":1,"reviews":[{"test_path":"tests/test_global.py","disposition":"legacy_overcoverage","rationale":""}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rationale"):
        load_reviewed_legacy_only_tests(review)
