from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "id-validation-queue-operations.yml"
REMOTE_SCRIPT = ROOT / "scripts" / "ops" / "run_id_validation_queue_operation.sh"


def test_queue_operations_workflow_is_manual_id_only_and_exact_release_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    trigger = source[source.index("on:") : source.index("permissions:")]

    assert "workflow_dispatch:" in trigger
    for forbidden in ("push:", "schedule:", "workflow_run:", "workflow_call:"):
        assert forbidden not in trigger
    assert "github.repository == 'qianlan333/AI-CRM-ID-refactor'" in source
    assert "EXPECTED_DEPLOY_HOST: 49.232.57.128" in source
    assert "PUBLIC_BASE_URL: https://id-dev.youcangogogo.com" in source
    assert "PUBLIC_HEALTH_URL: https://id-dev.youcangogogo.com/health" in source
    assert "environment: id-validation" in source
    assert "group: aicrm-id-validation-deploy" in source
    assert "git rev-parse FETCH_HEAD" in source
    assert 'values != [sys.argv[2]]' in source
    assert "150.158.82.186" not in source
    assert "www.youcangogogo.com" not in source
    assert "secrets.DEPLOY_HOST" not in source
    assert "secrets.TEST_DEPLOY_HOST" not in source


def test_queue_operations_workflow_uses_pinned_ssh_and_private_canary_spec() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0" in source
    assert "appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2" in source
    assert "fingerprint: ${{ env.EXPECTED_SSH_HOST_FINGERPRINT }}" in source
    assert "script_path: scripts/ops/run_id_validation_queue_operation.sh" in source
    assert "ID_VALIDATION_WECOM_CANARY_SPEC_B64" in source
    assert "WECOM_CANARY_SPEC_B64" in source
    job_env = source[source.index("    env:") : source.index("    steps:")]
    assert "ID_VALIDATION_WECOM_CANARY_SPEC_B64" not in job_env
    assert "Execute guarded private-spec queue operation on 49" in source
    assert "Execute guarded non-spec queue operation on 49" in source
    assert "cancel-in-progress: false" in source


def test_remote_queue_operation_has_server_lock_release_attestation_and_no_direct_provider() -> None:
    source = REMOTE_SCRIPT.read_text(encoding="utf-8")

    assert "/tmp/aicrm-deploy-${deploy_target}.lock" in source
    assert 'git rev-parse HEAD)" != "$expected_release_sha"' in source
    assert "/home/ubuntu/.aicrm-releases/id-validation.json" in source
    assert 'values != [expected]' in source
    assert "ID_VALIDATION_WECOM_CANARY_SPEC_B64 is not configured" in source
    assert "base64.b64decode" in source
    assert "chmod 0600" in source
    for script in (
        "cutover_queue_runtime_generation.py",
        "run_test_loopback_canary.py",
        "configure_wecom_canary.py",
        "transition_queue_runtime_scope.py",
        "plan_wecom_canary.py",
        "authorize_wecom_canary_execution.py",
        "attest_queue_runtime_validation.py",
        "run_queue_runtime_fault_drill.py",
        "manage_queue_runtime_soak.py",
    ):
        assert f"scripts/ops/{script}" in source
    for forbidden in (
        "qyapi.weixin.qq.com",
        "run-due",
        "dispatch_one",
        "AI-CRM.git",
        "150.158.82.186",
    ):
        assert forbidden not in source


def test_remote_rollback_blocks_wecom_before_returning_to_test_loopback() -> None:
    source = REMOTE_SCRIPT.read_text(encoding="utf-8")
    rollback = source[source.index("rollback_test_loopback)") : source.index("soak_start)")]

    disable_index = rollback.index("--mode disable")
    transition_index = rollback.index("--target-scope test_loopback")
    assert disable_index < transition_index
