from __future__ import annotations

import json
from pathlib import Path

import tools.run_codex_autopilot_tick as runner


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/run_codex_autopilot_tick.py"
SCRIPT = ROOT / "scripts/codex_autopilot_tick.sh"
RUNBOOK = ROOT / "docs/development/codex_autopilot_runtime_runbook.md"


def test_runner_exists_and_mentions_required_preflight_docs() -> None:
    text = TOOL.read_text(encoding="utf-8")
    for path in runner.REQUIRED_PREFLIGHT_DOCS:
        assert path in text


def test_runner_generates_prompt_without_github_when_no_open_pr(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    report = runner.main(["--skip-github", "--prompt-output", str(prompt), "--lock-file", str(tmp_path / "lock")])
    assert report == 0
    assert prompt.exists()
    prompt_text = prompt.read_text(encoding="utf-8")
    assert "phase_execution_state.yaml" in prompt_text
    assert "check_autonomous_development_loop.py" in prompt_text
    assert "check_automerge_eligibility.py" in prompt_text


def test_runner_owner_decision_package_on_stop_condition(tmp_path: Path) -> None:
    owner_package = tmp_path / "owner.md"
    result = runner.main(
        [
            "--skip-github",
            "--action",
            "production write",
            "--owner-decision-output",
            str(owner_package),
            "--lock-file",
            str(tmp_path / "lock"),
        ]
    )
    assert result == 0
    assert owner_package.exists()
    text = owner_package.read_text(encoding="utf-8")
    assert "auto_merge_allowed: false" in text
    assert "production_write_allowed: false" in text


def test_runner_uses_single_flight_lock(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    with lock.open("w", encoding="utf-8") as handle:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output = tmp_path / "report.json"
        result = runner.main(["--skip-github", "--lock-file", str(lock), "--output-json", str(output)])
        assert result == 0
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["result_status"] == "already_running"


def test_script_uses_configurable_codex_command_and_logs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AICRM_CODEX_COMMAND" in text
    assert "logs/codex-autopilot" in text
    assert "git fetch origin main --prune" in text
    assert "tools/run_codex_autopilot_tick.py" in text


def test_runner_admin_merge_is_env_gated(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AICRM_AUTOPILOT_ADMIN_MERGE_APPROVED", raising=False)
    prompt = tmp_path / "prompt.md"
    args = runner.parse_args(["--skip-github", "--prompt-output", str(prompt), "--lock-file", str(tmp_path / "lock")])
    report = runner.build_tick_report(args)
    assert report["admin_merge_allowed"] is False
    monkeypatch.setenv("AICRM_AUTOPILOT_ADMIN_MERGE_APPROVED", "1")
    report = runner.build_tick_report(args)
    assert report["admin_merge_allowed"] is True


def test_runbook_declares_runtime_boundaries() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for phrase in (
        "does not change production routes",
        "Default behavior is PR creation only",
        "does not authorize production route switch",
        "Risk / rollback",
        "Autopilot runtime decision",
    ):
        assert phrase in text


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed = runner.changed_files()
    assert "aicrm_next/main.py" not in changed
    assert "aicrm_next/production_compat/api.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)


def test_shell_script_is_not_hardcoded_to_one_codex_binary() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'CODEX_COMMAND="${AICRM_CODEX_COMMAND:-codex}"' in text
    assert "$CODEX_COMMAND" in text


def test_runner_does_not_import_runtime_modules() -> None:
    text = TOOL.read_text(encoding="utf-8")
    forbidden = ("import aicrm_next", "from aicrm_next", "import wecom_ability_service", "from wecom_ability_service")
    for item in forbidden:
        assert item not in text
