from __future__ import annotations

import subprocess
from pathlib import Path

import tools.check_phase4a_internal_write_candidate_selection as checker


ROOT = Path(__file__).resolve().parents[1]
PHASE4A_YAML = ROOT / "docs/development/phase_4a_internal_write_candidate_selection.yaml"
PHASE4A_MD = ROOT / "docs/development/phase_4a_internal_write_candidate_selection.md"


def _phase4a_data() -> dict:
    return checker.load_yaml(PHASE4A_YAML)


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_authorization_flags_are_false() -> None:
    phase4a = _phase4a_data()["phase_4a"]
    for field in checker.REQUIRED_AUTH_FALSE:
        assert phase4a[field] is False


def test_forbidden_first_batch_includes_required_categories() -> None:
    data = _phase4a_data()
    forbidden = set(data["forbidden_first_batch"])
    assert checker.REQUIRED_FORBIDDEN_FIRST_BATCH <= forbidden


def test_candidate_rules_all_true() -> None:
    rules = _phase4a_data()["candidate_rules"]
    for field in checker.REQUIRED_CANDIDATE_RULES:
        assert rules[field] is True


def test_candidates_count_and_required_fields() -> None:
    candidates = _phase4a_data()["candidates"]
    assert 2 <= len(candidates) <= 4
    for candidate in candidates:
        for field in checker.REQUIRED_CANDIDATE_FIELDS:
            assert candidate.get(field), f"{candidate.get('id')} missing {field}"
        assert candidate["required_rollback"]
        assert candidate["required_idempotency"]
        assert candidate["required_audit_operator_identity"]
        assert candidate["required_checker"]
        assert candidate["required_smoke"]
        assert candidate["fallback_required_until"]
        assert candidate["business_continuity_requirement"]


def test_recommended_candidate_requires_approval_and_avoids_forbidden_scope() -> None:
    data = _phase4a_data()
    recommended = data["recommended_phase_4b"]
    assert recommended["approval_required"] is True
    assert recommended["implementation_pr_required"] is True
    candidate_id = recommended["candidate_id"]
    candidate = next(item for item in data["candidates"] if item["id"] == candidate_id)
    assert candidate["decision"] == "recommended"

    actual_scope = f"{candidate['route_family']} {candidate['capability_owner']}".lower()
    forbidden_actual_scope_terms = (
        "payment",
        "oauth",
        "wecom external",
        "callback",
        "run-due",
        "timer",
        "execution",
        "send",
        "upload",
        "openclaw",
        "mcp",
        "public submit",
        "external push",
    )
    assert not any(term in actual_scope for term in forbidden_actual_scope_terms)


def test_candidates_are_traceable_to_backlog() -> None:
    report = checker.check_backlog_traceability()
    assert report["ok"], report
    for matches in report["traces"].values():
        assert matches


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    report = checker.check_no_runtime_changes()
    assert report["ok"], report


def test_docs_do_not_claim_runtime_or_production_authorization() -> None:
    text = "\n".join([PHASE4A_MD.read_text(encoding="utf-8"), PHASE4A_YAML.read_text(encoding="utf-8")]).lower()
    forbidden_claims = (
        "implementation_authorized: true",
        "production_cutover_authorized: true",
        "fallback_removal_authorized: true",
        "production approved",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    )
    for claim in forbidden_claims:
        assert claim not in text


def test_cli_outputs_json_and_markdown(tmp_path: Path) -> None:
    json_path = tmp_path / "phase4a.json"
    md_path = tmp_path / "phase4a.md"
    completed = subprocess.run(
        [
            "python3",
            "tools/check_phase4a_internal_write_candidate_selection.py",
            "--output-json",
            str(json_path),
            "--output-md",
            str(md_path),
        ],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "overall: PASS" in completed.stdout
    assert json_path.exists()
    assert md_path.exists()
