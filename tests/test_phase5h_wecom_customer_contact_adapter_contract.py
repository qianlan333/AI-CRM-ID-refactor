from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase5h_wecom_customer_contact_adapter_contract as checker
import tools.run_phase5h_wecom_customer_contact_adapter_contract_evidence as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5h_wecom_customer_contact_adapter_contract.md"
PLAN_YAML = ROOT / "docs/development/phase_5h_wecom_customer_contact_adapter_contract.yaml"
RUNNER = ROOT / "tools/run_phase5h_wecom_customer_contact_adapter_contract_evidence.py"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_runner_default_fake_stub_evidence_passes(tmp_path: Path) -> None:
    output_json = tmp_path / "evidence.json"
    output_md = tmp_path / "evidence.md"
    proc = subprocess.run(
        [
            "python3",
            str(RUNNER),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    evidence = json.loads(output_json.read_text(encoding="utf-8"))
    assert evidence["ok"] is True
    assert evidence["mode"] == "fake_stub_contract"
    assert output_md.exists()


def test_runner_does_not_process_live_callback_or_write_side_effects() -> None:
    evidence = runner.build_report()
    assert evidence["live_callback_processed"] is False
    assert evidence["production_write_executed"] is False
    assert evidence["production_contact_write_executed"] is False
    assert evidence["production_identity_mapping_write_executed"] is False
    assert evidence["production_tag_write_executed"] is False
    assert evidence["outbound_send_executed"] is False
    assert evidence["token_used"] is False
    assert evidence["aes_key_used"] is False
    assert evidence["production_behavior_changed"] is False
    assert evidence["production_compat_changed"] is False
    assert evidence["fallback_removed"] is False
    assert all(value is False for value in evidence["side_effect_safety"].values())


def test_yaml_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]
    assert all(value is False for value in data["authorizations"].values())


def test_error_mapping_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_ERROR_CODES <= set(data["error_mapping"]["required_error_codes"])


def test_side_effect_safety_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["side_effect_safety"]
    assert all(value is False for value in data["side_effect_safety"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text


def test_adapter_methods_complete_and_no_live_callback_allowed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    methods = data["adapter_contract"]["methods"]
    assert checker.REQUIRED_METHODS == {item["name"] for item in methods}
    assert all(item["live_callback_allowed"] is False for item in methods)
    dry_runs = {item["name"]: item for item in methods if item["name"].startswith("dry_run_")}
    assert dry_runs["dry_run_record_contact_event"]["idempotency_required"] is True
    assert dry_runs["dry_run_identity_mapping"]["idempotency_required"] is True


def test_runner_source_has_no_live_network_secret_or_aes_access() -> None:
    blockers = checker._runner_static_report()
    assert blockers == []


def test_changed_files_are_phase5h_allowed_if_git_diff_available() -> None:
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
    assert changed <= checker.ALLOWED_CHANGED_FILES
    assert not any(path.startswith("aicrm_next/production_compat/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
