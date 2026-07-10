from __future__ import annotations

from pathlib import Path

from scripts.ops import manage_production_runtime_units as runtime_units


ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return runtime_units.load_manifest()


def test_runtime_units_manifest_classifies_every_deploy_timer() -> None:
    manifest = _manifest()
    active = {item["timer"] for item in manifest["active_autostart"]}
    approval_required = set(manifest["approval_required"])
    retired_forbidden = set(manifest["retired_forbidden"])
    deploy_timers = {path.name for path in (ROOT / "deploy").glob("*.timer")}

    assert deploy_timers == active | approval_required
    assert active.isdisjoint(approval_required)
    assert active.isdisjoint(retired_forbidden)
    assert approval_required.isdisjoint(retired_forbidden)
    assert "aicrm-archive-sync.timer" in approval_required
    assert "openclaw-external-effect-worker.timer" in active
    assert "openclaw-external-push-worker.timer" in retired_forbidden
    assert "openclaw-external-push-worker.service" in retired_forbidden
    assert "openclaw-external-push-worker.timer" not in deploy_timers
    assert "openclaw-wecom-callback-inbox-worker.timer" in retired_forbidden
    assert "openclaw-wecom-callback-inbox-worker.timer" not in deploy_timers
    assert "aicrm-automation-jobs-run-due.timer" in retired_forbidden


def test_runtime_units_manifest_validates_units_and_calendar_persistence() -> None:
    runtime_units.validate_manifest(_manifest())


def test_runtime_units_manifest_retires_callback_hotfix_overlay_dropins() -> None:
    retired = {
        (item["unit"], item["dropin"])
        for item in _manifest()["retired_dropins"]
    }

    assert retired == {
        ("openclaw-wecom-postgres.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-wecom-callback-ingress.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-wecom-callback-inbox-worker.service", "10-aicrm-callback-hotfix-runtime.conf"),
    }


def test_runtime_units_retire_legacy_overlays_is_idempotent_and_verified(capsys) -> None:
    assert runtime_units.main(["--phase", "retire-legacy-overlays", "--dry-run"]) == 0
    output = capsys.readouterr().out

    for unit in (
        "openclaw-wecom-postgres.service",
        "openclaw-wecom-callback-ingress.service",
        "openclaw-wecom-callback-inbox-worker.service",
    ):
        path = f"/etc/systemd/system/{unit}.d/10-aicrm-callback-hotfix-runtime.conf"
        assert f"sudo rm -f {path}" in output
        assert f"sudo test '!' -e {path}" in output
    assert output.index("sudo rm -f") < output.index("sudo systemctl daemon-reload") < output.index("sudo test '!' -e")


def test_runtime_units_install_dry_run_copies_and_enables_only_active_units(capsys) -> None:
    assert runtime_units.main(["--phase", "install-enable-after-web-health", "--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "sudo cp deploy/openclaw-external-effect-worker.service /etc/systemd/system/" in output
    assert "sudo cp deploy/openclaw-external-effect-worker.timer /etc/systemd/system/" in output
    assert "sudo systemctl enable openclaw-external-effect-worker.timer" in output
    assert "sudo systemctl restart openclaw-external-effect-worker.timer" in output
    assert "sudo systemctl is-active openclaw-external-effect-worker.timer" not in output
    assert "sudo systemctl enable aicrm-archive-sync.timer" not in output
    assert "sudo cp deploy/aicrm-archive-sync.timer /etc/systemd/system/" not in output
    assert "curl -sSf http://127.0.0.1:5002/health" in output
    assert "sudo cp deploy/openclaw-wecom-callback-inbox-worker.service /etc/systemd/system/" in output
    assert "sudo systemctl enable openclaw-wecom-callback-inbox-worker.service" in output
    assert "sudo systemctl restart openclaw-wecom-callback-inbox-worker.service" in output
    assert "sudo systemctl disable --now openclaw-wecom-callback-inbox-worker.timer" in output
    assert "sudo systemctl disable --now openclaw-external-push-worker.timer" in output
    assert "sudo systemctl disable --now openclaw-external-push-worker.service" in output


def test_runtime_units_stop_and_verify_dry_runs_are_manifest_driven(capsys) -> None:
    assert runtime_units.main(["--phase", "stop-for-migration", "--dry-run"]) == 0
    stop_output = capsys.readouterr().out

    assert "sudo systemctl stop openclaw-external-effect-worker.timer" in stop_output
    assert "sudo systemctl stop openclaw-external-effect-worker.service" in stop_output
    assert "sudo systemctl stop openclaw-wecom-callback-inbox-worker.service" in stop_output
    assert "sudo systemctl stop aicrm-archive-sync.timer" not in stop_output

    assert runtime_units.main(["--phase", "verify", "--dry-run"]) == 0
    verify_output = capsys.readouterr().out

    assert "sudo systemctl is-active openclaw-external-effect-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-ingress.service" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-inbox-worker.service" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-inbox-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-external-push-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-external-push-worker.service" in verify_output
    assert "sudo test '!' -e /etc/systemd/system/openclaw-wecom-callback-ingress.service.d/10-aicrm-callback-hotfix-runtime.conf" in verify_output
    assert "approval_required_timers=aicrm-archive-sync.timer" in verify_output
