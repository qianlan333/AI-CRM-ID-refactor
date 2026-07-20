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
    assert 'git merge-base --is-ancestor "$EXPECTED_RELEASE_SHA" FETCH_HEAD' in source
    assert 'test "$(git rev-parse FETCH_HEAD)" = "$EXPECTED_RELEASE_SHA"' not in source
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
    assert "ID_VALIDATION_WECOM_CHANNEL_ASSET_B64" in source
    assert "ID_VALIDATION_WECOM_CALLBACK_EVENT_B64" in source
    assert "WECOM_CANARY_SPEC_B64" in source
    assert "WECOM_CHANNEL_ASSET_B64" in source
    assert "WECOM_CALLBACK_EVENT_B64" in source
    job_env = source[source.index("    env:") : source.index("    steps:")]
    assert "ID_VALIDATION_WECOM_CANARY_SPEC_B64" not in job_env
    assert "ID_VALIDATION_WECOM_CHANNEL_ASSET_B64" not in job_env
    assert "ID_VALIDATION_WECOM_CALLBACK_EVENT_B64" not in job_env
    assert "Execute guarded canary-spec queue operation on 49" in source
    assert "import_canary_media" in source
    assert "Import guarded production canary channel asset on 49" in source
    assert "Ingest guarded production canary callback transcript on 49" in source
    assert "Arm guarded real-time callback canary on 49" in source
    assert "upstream_welcome_delivery_attested:" in source
    assert "QUEUE_UPSTREAM_WELCOME_DELIVERY_ATTESTED" in source
    assert "Execute guarded non-spec queue operation on 49" in source
    assert "cancel-in-progress: false" in source


def test_customer_refresh_diagnostic_is_read_only_redacted_and_exact_release_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    diagnostic = source[
        source.index("  diagnose_customer_refresh:") : source.index("  diagnose_callback_canary:")
    ]

    assert "- diagnose_customer_refresh" in source
    assert "inputs.operation == 'diagnose_customer_refresh'" in diagnostic
    assert "environment: id-validation" in diagnostic
    assert "EXPECTED_DEPLOY_HOST: 49.232.57.128" in diagnostic
    assert "PUBLIC_HEALTH_URL: https://id-dev.youcangogogo.com/health" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_HOST" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_USER" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_SSH_KEY" in diagnostic
    assert 'git rev-parse HEAD)" = "$EXPECTED_RELEASE_SHA"' in diagnostic
    assert 'actual_public_sha" = "$EXPECTED_RELEASE_SHA"' in diagnostic
    assert "git status --porcelain=v1 --untracked-files=all" in diagnostic
    assert "redact_sensitive_text" in diagnostic
    assert 'session.execute(text("SET TRANSACTION READ ONLY"))' in diagnostic
    assert "customer_read_model_refresh_intent" in diagnostic
    assert "internal_event_consumer_attempt" in diagnostic
    assert "internal_event_outbox" in diagnostic
    for forbidden in (
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "qyapi.weixin.qq.com",
        "journalctl",
        "WECOM_CANARY_SPEC_B64",
    ):
        assert forbidden not in diagnostic


def test_callback_canary_diagnostic_is_read_only_redacted_and_exact_release_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    diagnostic = source[
        source.index("  diagnose_callback_canary:") : source.index("  diagnose_soak_failure:")
    ]

    assert "- diagnose_callback_canary" in source
    assert "inputs.operation == 'diagnose_callback_canary'" in diagnostic
    assert "environment: id-validation" in diagnostic
    assert "EXPECTED_DEPLOY_HOST: 49.232.57.128" in diagnostic
    assert "PUBLIC_HEALTH_URL: https://id-dev.youcangogogo.com/health" in diagnostic
    assert "EXPECTED_POLICY_VERSION: ${{ inputs.policy_version }}" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_HOST" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_USER" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_SSH_KEY" in diagnostic
    assert 'git rev-parse HEAD)" = "$EXPECTED_RELEASE_SHA"' in diagnostic
    assert 'actual_public_sha" = "$EXPECTED_RELEASE_SHA"' in diagnostic
    assert "git status --porcelain=v1 --untracked-files=all" in diagnostic
    assert 'session.execute(text("SET TRANSACTION READ ONLY"))' in diagnostic
    assert "processing_summary_json->'external_effect_job_ids'" in diagnostic
    assert "provider_boundary_count" in diagnostic
    assert "side_effect_executed_count" in diagnostic
    assert "target_values_redacted" in diagnostic
    for forbidden in (
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "qyapi.weixin.qq.com",
        "payload_xml",
        "payload_json AS",
        "raw_body",
        "external_userid",
        "corp_id",
        "WECOM_CANARY_SPEC_B64",
    ):
        assert forbidden not in diagnostic


def test_soak_failure_diagnostic_is_read_only_redacted_and_exact_release_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    diagnostic = source[
        source.index("  diagnose_soak_failure:") : source.index("  operate:")
    ]

    assert "- diagnose_soak_failure" in source
    assert "inputs.operation == 'diagnose_soak_failure'" in diagnostic
    assert "environment: id-validation" in diagnostic
    assert "EXPECTED_DEPLOY_HOST: 49.232.57.128" in diagnostic
    assert "PUBLIC_HEALTH_URL: https://id-dev.youcangogogo.com/health" in diagnostic
    assert "EXPECTED_POLICY_VERSION: ${{ inputs.policy_version }}" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_HOST" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_USER" in diagnostic
    assert "secrets.ID_VALIDATION_DEPLOY_SSH_KEY" in diagnostic
    assert 'git rev-parse HEAD)" = "$EXPECTED_RELEASE_SHA"' in diagnostic
    assert 'actual_public_sha" = "$EXPECTED_RELEASE_SHA"' in diagnostic
    assert "git status --porcelain=v1 --untracked-files=all" in diagnostic
    assert 'session.execute(text("SET TRANSACTION READ ONLY"))' in diagnostic
    assert "queue_runtime_soak_snapshot" in diagnostic
    assert "metric_deltas" in diagnostic
    assert "terminal_rows_during_soak" in diagnostic
    assert "redact_sensitive_text" in diagnostic
    assert "target_values_redacted" in diagnostic
    for evaluator_metric in (
        "lost_lease_count",
        "duplicate_provider_call_count",
        "unexpected_real_target_count",
        "worker_release_mismatch_count",
        "fresh_listener_count",
        "external_effect_eligible_oldest_pending_age_seconds",
        "internal_event_actionable_oldest_pending_age_seconds",
        "webhook_eligible_oldest_pending_age_seconds",
    ):
        assert evaluator_metric in diagnostic
    assert diagnostic.count("unknown_after_dispatch") >= 2
    for forbidden in (
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "qyapi.weixin.qq.com",
        "payload_xml",
        "payload_json AS",
        "raw_body",
        "external_userid",
        "corp_id",
        "WECOM_CANARY_SPEC_B64",
    ):
        assert forbidden not in diagnostic


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
        "import_wecom_canary_media_asset.py",
        "import_wecom_canary_channel_asset.py",
        "ingest_wecom_canary_callback.py",
        "arm_wecom_callback_canary.py",
        "transition_queue_runtime_scope.py",
        "plan_wecom_canary.py",
        "authorize_wecom_canary_execution.py",
        "attest_queue_runtime_validation.py",
        "run_queue_runtime_fault_drill.py",
        "manage_queue_runtime_soak.py",
    ):
        assert f"scripts/ops/{script}" in source
    assert "--upstream-welcome-delivery-attested" in source
    for forbidden in (
        "qyapi.weixin.qq.com",
        "run-due",
        "dispatch_one",
        "AI-CRM.git",
        "150.158.82.186",
    ):
        assert forbidden not in source


def test_real_time_callback_arm_is_private_asset_bound_and_never_receives_transcript_secret() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    arm_step = source[
        source.index("Arm guarded real-time callback canary on 49") :
        source.index("Record operation provenance")
    ]

    assert "ID_VALIDATION_WECOM_CANARY_SPEC_B64" in arm_step
    assert "ID_VALIDATION_WECOM_CHANNEL_ASSET_B64" in arm_step
    assert "WECOM_CANARY_SPEC_B64" in arm_step
    assert "WECOM_CHANNEL_ASSET_B64" in arm_step
    assert "WECOM_CALLBACK_EVENT_B64" not in arm_step
    assert "command_timeout: 25m" in arm_step


def test_remote_rollback_blocks_wecom_before_returning_to_test_loopback() -> None:
    source = REMOTE_SCRIPT.read_text(encoding="utf-8")
    rollback = source[source.index("rollback_test_loopback)") : source.index("soak_start)")]

    disable_index = rollback.index("--mode disable")
    transition_index = rollback.index("--target-scope test_loopback")
    assert disable_index < transition_index
