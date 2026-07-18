from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ("wecom_ability" + "_service")
RUNTIME_UNITS_HELPER = "python3 scripts/ops/manage_production_runtime_units.py"
TEST_DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
REMOTE_DEPLOY_SCRIPT = ROOT / "scripts" / "ops" / "deploy_id_validation_remote.sh"
GENERATION_MARKER_NORMALIZER = (
    ROOT / "scripts" / "ops" / "normalize_queue_runtime_generation_marker.sh"
)
PRODUCTION_PROMOTION_WORKFLOW = ROOT / ".github" / "workflows" / "promote-production.yml"


def _deploy_contract_source() -> str:
    remote_script = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")
    indented_remote_script = "\n".join(
        f"            {line}" for line in remote_script.splitlines()
    )
    return (
        TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        + "\n# deploy_id_validation_remote.sh\n"
        + indented_remote_script
        + "\n"
    )


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _runtime_units_phase(phase: str) -> str:
    return f"{RUNTIME_UNITS_HELPER} --phase {phase} --execute"


def test_id_validation_deploy_serializes_without_cancelling_active_release() -> None:
    deploy = _deploy_contract_source()

    assert "group: aicrm-id-validation-deploy" in deploy
    assert "cancel-in-progress: false" in deploy
    assert not PRODUCTION_PROMOTION_WORKFLOW.exists()


def test_remote_deploy_is_an_executable_script_path_with_explicit_environment() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    remote_script = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_step = workflow[workflow.index("      - name: Deploy via SSH") :]
    expected_envs = (
        "EXPECTED_REPOSITORY,DEPLOY_TARGET,RUNTIME_TARGET_ENVIRONMENT,"
        "PUBLIC_BASE_URL,PUBLIC_HEALTH_URL,ALLOW_MISSING_WECHAT_SHOP_CALLBACK_TOKEN,"
        "RELEASE_REPOSITORY,RELEASE_RUN_ID,RELEASE_RUN_ATTEMPT,SOURCE_CI_RUN_ID,"
        "VERIFIED_SHA,BASE_SHA,BASE_SOURCE,BUNDLE_SHA256"
    )

    assert "script: |" not in deploy_step
    assert "script_path: scripts/ops/deploy_id_validation_remote.sh" in deploy_step
    assert f"envs: {expected_envs}" in deploy_step
    assert "RELEASE_REPOSITORY: ${{ github.repository }}" in deploy_step
    assert "RELEASE_RUN_ID: ${{ github.run_id }}" in deploy_step
    assert "RELEASE_RUN_ATTEMPT: ${{ github.run_attempt }}" in deploy_step
    assert "SOURCE_CI_RUN_ID: ${{ github.event.workflow_run.id }}" in deploy_step
    assert "VERIFIED_SHA: ${{ github.event.workflow_run.head_sha }}" in deploy_step
    assert "BASE_SHA: ${{ steps.release.outputs.base_sha }}" in deploy_step
    assert "BASE_SOURCE: ${{ steps.release.outputs.base_source }}" in deploy_step
    assert "BUNDLE_SHA256: ${{ steps.release.outputs.bundle_sha256 }}" in deploy_step
    assert REMOTE_DEPLOY_SCRIPT.stat().st_mode & 0o111
    assert remote_script.startswith("#!/usr/bin/env bash\nset -e\nset -o pipefail\n")
    assert "${{" not in remote_script


def test_remote_deploy_repairs_legacy_generation_marker_ownership_before_runtime_control() -> None:
    remote_script = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    normalizer = GENERATION_MARKER_NORMALIZER.read_text(encoding="utf-8")
    repair_index = remote_script.index(
        'bash "$release_control_dir/scripts/ops/normalize_queue_runtime_generation_marker.sh"'
    )
    source_index = remote_script.index(
        "source /home/ubuntu/.openclaw-wecom-pg.env",
        repair_index,
    )
    noop_start = workflow.index("      - name: Verify already active ID release")
    noop_end = workflow.index("      - name: Record successful no-op provenance", noop_start)
    noop = workflow[noop_start:noop_end]

    assert repair_index < source_index
    assert "bash scripts/ops/normalize_queue_runtime_generation_marker.sh" in noop
    assert noop.index("normalize_queue_runtime_generation_marker.sh") < noop.index(
        "python3 scripts/ops/manage_production_runtime_units.py --phase verify --execute"
    )
    assert 'sudo test -e "$runtime_generation_marker" || sudo test -L' in normalizer
    assert 'sudo test -L "$runtime_generation_marker"' in normalizer
    assert 'sudo test -f "$runtime_generation_marker"' in normalizer
    assert 'sudo chown --no-dereference ubuntu:ubuntu "$runtime_generation_marker"' in normalizer
    assert 'chmod 0600 "$runtime_generation_marker"' in normalizer
    assert "stat -c '%U:%G:%a'" in normalizer
    assert '!= "ubuntu:ubuntu:600"' in normalizer
    assert normalizer.index("sudo test -L") < normalizer.index("sudo chown --no-dereference")
    assert normalizer.index("sudo chown --no-dereference") < normalizer.index("chmod 0600")


def test_remote_deploy_snapshots_immutable_inputs_before_sourcing_server_environment(
    tmp_path: Path,
) -> None:
    remote_script = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")
    snapshot_start = remote_script.index('readonly deploy_target="${DEPLOY_TARGET}"')
    snapshot_end = remote_script.index(
        'if [ "$release_repository" != "$expected_repository" ]; then',
        snapshot_start,
    )
    first_source = remote_script.index(
        "source /home/ubuntu/.openclaw-wecom-pg.env",
        snapshot_end,
    )
    snapshot_block = remote_script[snapshot_start:snapshot_end]
    source_tail = remote_script[first_source:]

    assert remote_script.count('${PUBLIC_BASE_URL}') == 1
    assert remote_script.count('${PUBLIC_HEALTH_URL}') == 1
    assert remote_script.count('${ALLOW_MISSING_WECHAT_SHOP_CALLBACK_TOKEN}') == 1
    assert snapshot_block.count("readonly ") == 11
    assert 'readonly verified_sha="${VERIFIED_SHA}"' in remote_script[:first_source]
    assert 'readonly base_sha="${BASE_SHA}"' in remote_script[:first_source]
    assert 'readonly base_source="${BASE_SOURCE}"' in remote_script[:first_source]
    assert '${PUBLIC_BASE_URL}' not in source_tail
    assert '${PUBLIC_HEALTH_URL}' not in source_tail
    assert '${ALLOW_MISSING_WECHAT_SHOP_CALLBACK_TOKEN}' not in source_tail
    assert 'auth_issuer="${public_base_url}"' in source_tail
    assert '"${public_health_url}" \\' in source_tail

    hostile_environment = tmp_path / "hostile.env"
    hostile_environment.write_text(
        "PUBLIC_BASE_URL=https://attacker.invalid\n"
        "PUBLIC_HEALTH_URL=https://attacker.invalid/health\n"
        "ALLOW_MISSING_WECHAT_SHOP_CALLBACK_TOKEN=1\n",
        encoding="utf-8",
    )
    harness = f"""
set -e
DEPLOY_TARGET=id-validation
RUNTIME_TARGET_ENVIRONMENT=production
PUBLIC_BASE_URL=https://id-dev.youcangogogo.com
PUBLIC_HEALTH_URL=https://id-dev.youcangogogo.com/health
ALLOW_MISSING_WECHAT_SHOP_CALLBACK_TOKEN=0
EXPECTED_REPOSITORY=qianlan333/AI-CRM-ID-refactor
RELEASE_REPOSITORY=qianlan333/AI-CRM-ID-refactor
RELEASE_RUN_ID=1
RELEASE_RUN_ATTEMPT=1
SOURCE_CI_RUN_ID=2
BUNDLE_SHA256={'a' * 64}
VERIFIED_SHA={'b' * 40}
BASE_SHA={'c' * 40}
{snapshot_block}
source {hostile_environment}
printf '%s\n' "$public_base_url" "$public_health_url" "$allow_missing_wechat_shop_callback_token"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "https://id-dev.youcangogogo.com",
        "https://id-dev.youcangogogo.com/health",
        "0",
    ]

    lowercase_hostile_environment = tmp_path / "lowercase-hostile.env"
    lowercase_hostile_environment.write_text(
        "public_base_url=https://attacker.invalid\n",
        encoding="utf-8",
    )
    lowercase_result = subprocess.run(
        [
            "bash",
            "-c",
            harness.replace(
                f"source {hostile_environment}",
                f"source {lowercase_hostile_environment}",
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert lowercase_result.returncode != 0
    assert "readonly variable" in lowercase_result.stderr


def test_remote_deploy_holds_target_specific_server_lock_before_sha_checks() -> None:
    workflow = _deploy_contract_source()

    target_index = workflow.index('deploy_target="${DEPLOY_TARGET}"', workflow.index("Deploy via SSH"))
    lock_file_index = workflow.index('deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"', target_index)
    lock_fd_index = workflow.index('exec 9>"$deploy_lock_file"', lock_file_index)
    flock_index = workflow.index("if ! flock -n 9; then", lock_fd_index)
    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"', flock_index)
    migration_index = workflow.index("python3 -m alembic upgrade head", before_sha_index)

    assert target_index < lock_file_index < lock_fd_index < flock_index < before_sha_index < migration_index
    assert 'echo "another $deploy_target deployment holds $deploy_lock_file"' in workflow


def test_failed_uncommitted_deploy_restores_previous_exact_sha_and_dependencies() -> None:
    workflow = _deploy_contract_source()

    switched_init = workflow.index("release_switched=0")
    committed_init = workflow.index("release_committed=0", switched_init)
    cleanup_index = workflow.index("cleanup_deploy()", committed_init)
    transaction_guard = workflow.index('[ "${runtime_mutation_started:-0}" = "1" ]', cleanup_index)
    stop_index = workflow.index("--phase ensure-stopped-for-rollback --execute", transaction_guard)
    rollback_guard = workflow.index('[ "${release_switched:-0}" = "1" ]', stop_index)
    reset_index = workflow.index('git reset --hard "$before_sha"', rollback_guard)
    release_file_index = workflow.index("printf '%s\\n' \"$before_sha\" > .release-sha", reset_index)
    dependency_guard = workflow.index('git diff --quiet "$before_sha" "$verified_sha" -- requirements.lock', release_file_index)
    dependency_restore = workflow.index("--require-hashes -r requirements.lock", dependency_guard)
    exact_health = workflow.index('grep -i "x-aicrm-release-sha: $restore_expected_sha"', dependency_restore)
    restore_units = workflow.index("--phase install-enable-after-web-health --execute", exact_health)

    assert switched_init < committed_init < cleanup_index < transaction_guard < stop_index < rollback_guard
    assert rollback_guard < reset_index < release_file_index
    assert release_file_index < dependency_guard < dependency_restore < exact_health < restore_units
    assert 'restore_expected_sha="$before_sha"' in workflow
    assert "alembic downgrade" not in workflow


def test_full_runtime_rollback_uses_staged_runtime_verification_contract() -> None:
    workflow = _deploy_contract_source()

    cleanup_index = workflow.index("cleanup_deploy()")
    restoring_index = workflow.index(
        'echo "restoring runtime units for $restore_expected_sha"', cleanup_index
    )
    full_restore_index = workflow.rfind(
        'if [ "${runtime_units_stopped:-0}" = "1" ]; then',
        cleanup_index,
        restoring_index,
    )
    partial_restore_index = workflow.index(
        'if [ "${runtime_transaction_partial:-0}" = "1" ]', full_restore_index
    )
    full_restore = workflow[full_restore_index:partial_restore_index]
    helper_start = workflow.index("restore_runtime_from_guard() {")
    helper_end = workflow.index("resecure_runtime_guard() {", helper_start)
    helper = workflow[helper_start:helper_end]
    install_index = helper.index("--phase install-enable-after-web-health --execute")
    verify_index = helper.index("--phase verify-staged-runtime --execute")
    release_index = helper.index("--phase release-runtime-guard --execute")

    assert install_index < verify_index < release_index
    assert "restore_runtime_from_guard authorize-runtime-start" in full_restore
    assert "--phase verify --execute" not in helper


def test_failed_deploy_drain_restores_timers_without_killing_active_oneshots() -> None:
    workflow = _deploy_contract_source()

    partial_init = workflow.index("runtime_transaction_partial=0")
    mutation_index = workflow.index("runtime_mutation_started=1", partial_init)
    partial_start = workflow.index("runtime_transaction_partial=1", mutation_index)
    stop_index = workflow.index("--phase stop-for-migration --execute", partial_start)
    stopped_index = workflow.index("runtime_units_stopped=1", stop_index)
    partial_clear = workflow.index("runtime_transaction_partial=0", stopped_index)
    cleanup_index = workflow.index("cleanup_deploy()")
    preserve_index = workflow.index("preserving active one-shot workers during rollback", cleanup_index)
    conditional_web_stop = workflow.index('if [ "${runtime_units_stopped:-0}" = "1" ]; then', preserve_index)
    rollback_index = workflow.index('git reset --hard "$before_sha"', conditional_web_stop)
    restore_index = workflow.index("restore_runtime_from_guard authorize-runtime-restore", rollback_index)
    install_index = workflow.index("--phase install-enable-after-web-health --execute", restore_index)
    release_index = workflow.index("--phase release-runtime-guard --execute", install_index)

    assert partial_init < mutation_index < partial_start < stop_index < stopped_index < partial_clear
    assert cleanup_index < preserve_index < conditional_web_stop < rollback_index < restore_index < install_index < release_index


def test_deploy_recovers_only_exact_identity_worker_self_deadlock_under_transaction_guard() -> None:
    workflow = _deploy_contract_source()

    mutation_index = workflow.index("runtime_mutation_started=1")
    begin_index = workflow.index("--phase begin-transaction --execute", mutation_index)
    recovery_index = workflow.index("scripts/ops/recover_identity_resolution_worker_deadlock.py", begin_index)
    execute_index = workflow.index("--execute", recovery_index)
    evidence_index = workflow.index("/tmp/aicrm-identity-worker-deadlock-recovery.json", execute_index)
    stop_index = workflow.index("--phase stop-for-migration --execute", evidence_index)

    assert mutation_index < begin_index < recovery_index < execute_index < evidence_index < stop_index


def test_success_marks_release_committed_only_after_public_exact_sha_verification() -> None:
    workflow = _deploy_contract_source()

    switch_index = workflow.index("release_switched=1")
    local_exact_sha_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"', switch_index)
    production_exact_sha_index = workflow.index('--expected-sha "$after_sha"', local_exact_sha_index)
    test_exact_sha_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"', production_exact_sha_index)
    committed_index = workflow.index("release_committed=1", test_exact_sha_index)

    assert switch_index < local_exact_sha_index < production_exact_sha_index < test_exact_sha_index < committed_index


def test_deploy_requires_runtime_units_and_application_readiness_before_commit() -> None:
    workflow = _deploy_contract_source()

    verify_units_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    readiness_index = workflow.index(
        "curl -sSf http://127.0.0.1:5001/api/system/health",
        verify_units_index,
    )
    restored_flag_index = workflow.index("runtime_units_stopped=0", readiness_index)
    committed_index = workflow.index("release_committed=1", restored_flag_index)

    assert verify_units_index < readiness_index < restored_flag_index < committed_index
    assert "tee /tmp/aicrm-runtime-readiness.json" in workflow


def _deploy_runtime_phase_index(workflow: str, phase: str) -> int:
    if phase == "stop-for-migration":
        mutation_index = workflow.index("runtime_mutation_started=1")
        return workflow.index(f"--phase {phase} --execute", mutation_index)
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    return workflow.index(_runtime_units_phase(phase), reset_index)


def test_production_deploy_loads_postgres_env_before_alembic_upgrade():
    workflow = _deploy_contract_source()

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")

    assert env_source_index < database_url_guard_index < alembic_upgrade_index
    assert "python3 app.py init-db" not in workflow
    assert "python app.py init-db" not in workflow
    assert "init-db-legacy" not in workflow
    assert "alembic stamp head" not in workflow
    assert "legacy_flask_app" not in workflow


def test_production_deploy_stashes_dirty_worktree_before_remote_update():
    workflow = _deploy_contract_source()

    stash_index = workflow.index("git stash push --include-untracked")
    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"')
    verified_sha_index = workflow.index('verified_sha="${VERIFIED_SHA}"', before_sha_index)
    fetch_index = workflow.index('git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/deploy/main"')
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    stop_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")

    assert before_sha_index < verified_sha_index < stash_index < fetch_index < reset_index < stop_index
    assert 'release_bundle="/tmp/aicrm-release-$verified_sha/aicrm-release.bundle"' in workflow
    remote_script = workflow[workflow.index("Deploy via SSH") :]
    assert "git fetch --no-tags origin" not in remote_script
    assert "GIT_SSH_COMMAND" not in workflow


def test_production_deploy_retires_callback_hotfix_overlay_before_migration_and_restart():
    workflow = _deploy_contract_source()

    reset_index = workflow.index('git reset --hard "$verified_sha"')
    marker_index = workflow.index("printf '%s\\n' \"$after_sha\" > .release-sha")
    retire_index = workflow.index(_runtime_units_phase("retire-legacy-overlays"))
    stop_runtime_units_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    web_start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))

    assert reset_index < marker_index < retire_index < stop_runtime_units_index < alembic_upgrade_index < web_start_index < install_index


def test_production_deploy_installs_dependencies_only_when_hashed_lock_changes():
    workflow = _deploy_contract_source()

    fetch_index = workflow.index('git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/deploy/main"')
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    requirements_guard_index = workflow.index('git diff --quiet "$before_sha" "$after_sha" -- requirements.lock')
    pip_install_index = workflow.index("python -m pip install --require-hashes -r requirements.lock")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")

    assert fetch_index < reset_index < after_sha_index < requirements_guard_index < pip_install_index < alembic_upgrade_index
    assert "requirements.lock unchanged; skipping pip install" in workflow


def test_production_deploy_fails_closed_unless_checkout_matches_verified_workflow_sha():
    workflow = _deploy_contract_source()

    deploy_step_index = workflow.index("- name: Deploy via SSH")
    remote_deploy_index = workflow.index(
        "uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2",
        deploy_step_index,
    )
    verified_sha_index = workflow.index('verified_sha="${VERIFIED_SHA}"', remote_deploy_index)
    release_head_index = workflow.index('release_head_sha="$(git rev-parse refs/remotes/deploy/main)"')
    head_guard_index = workflow.index('if [ "$release_head_sha" != "$verified_sha" ]; then')
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    checkout_guard_index = workflow.index('if [ "$after_sha" != "$verified_sha" ]; then')
    stop_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")

    assert verified_sha_index < release_head_index < head_guard_index < reset_index < after_sha_index < checkout_guard_index < stop_index
    assert "invalid verified workflow sha" in workflow
    assert "verified workflow sha is no longer the repository main head" in workflow
    assert "deployed checkout does not match verified workflow sha" in workflow


def test_production_deploy_verifies_local_bundle_before_fetch_and_stopping_services():
    workflow = _deploy_contract_source()

    deploy_step_index = workflow.index("- name: Deploy via SSH")
    remote_deploy_index = workflow.index(
        "uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2",
        deploy_step_index,
    )
    bundle_index = workflow.index('release_bundle="/tmp/aicrm-release-$verified_sha/aicrm-release.bundle"')
    checksum_index = workflow.index("sha256sum -c aicrm-release.bundle.sha256")
    verify_index = workflow.index('git bundle verify "$release_bundle"')
    head_guard_index = workflow.index('git bundle list-heads "$release_bundle"')
    fetch_index = workflow.index('git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/deploy/main"')
    stop_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")

    assert bundle_index < checksum_index < verify_index < head_guard_index < fetch_index < stop_index
    assert "release bundle does not advertise the verified workflow sha" in workflow
    remote_script = workflow[remote_deploy_index:]
    assert "git fetch --no-tags origin" not in remote_script
    assert "GIT_SSH_COMMAND" not in workflow


def test_production_deploy_builds_and_transfers_incremental_exact_sha_bundle_before_remote_deploy():
    workflow = _deploy_contract_source()

    checkout_index = workflow.index("uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0")
    probe_index = workflow.index("- name: Probe active ID release")
    discover_index = workflow.index('public_health_url="$PUBLIC_HEALTH_URL"', probe_index)
    recovery_index = workflow.index("- name: Resolve guarded ID recovery base", discover_index)
    build_index = workflow.index("git bundle create release/aicrm-release.bundle refs/deploy/release ^refs/deploy/base")
    transfer_index = workflow.index("uses: appleboy/scp-action@ff85246acaad7bdce478db94a363cd2bf7c90345")
    remote_deploy_index = workflow.index(
        "uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2",
        transfer_index,
    )

    assert checkout_index < probe_index < discover_index < recovery_index < build_index
    assert build_index < transfer_index < remote_deploy_index
    assert "permissions:\n  contents: read" in workflow
    assert "ref: ${{ github.event.workflow_run.head_sha }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert 'verified_sha="${{ github.event.workflow_run.head_sha }}"' in workflow
    assert "git fetch --no-tags origin main" in workflow
    assert 'if [ "$(git rev-parse FETCH_HEAD)" != "$verified_sha" ]; then' in workflow
    assert 'public_health_url="$PUBLIC_HEALTH_URL"' in workflow
    assert 'active_sha="$(python3 - /tmp/aicrm_current_release_headers.txt' in workflow
    assert 'if len(candidates) != 1 or re.fullmatch(r"[0-9a-f]{40}", candidates[0]) is None:' in workflow
    assert "ATTESTED_RELEASE_STDOUT: ${{ steps.attested_release.outputs.stdout }}" in workflow
    assert 'base_source="guarded_server_checkout"' in workflow
    assert 'git merge-base --is-ancestor "$base_sha" "$verified_sha"' in workflow
    assert 'git update-ref refs/deploy/release "$verified_sha"' in workflow
    assert 'git update-ref refs/deploy/base "$base_sha"' in workflow
    assert 'echo "base_sha=$base_sha" >> "$GITHUB_OUTPUT"' in workflow
    assert "sha256sum aicrm-release.bundle" in workflow
    assert "git bundle verify release/aicrm-release.bundle" in workflow
    assert "git bundle create release/aicrm-release.bundle HEAD" not in workflow
    assert "target: /tmp/aicrm-release-${{ github.event.workflow_run.head_sha }}" in workflow
    assert "strip_components: 1" in workflow
    assert "overwrite: true" in workflow


def test_active_release_probe_fails_closed_except_explicit_gateway_unavailability() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    probe_index = workflow.index("      - name: Probe active ID release")
    recovery_index = workflow.index("      - name: Resolve guarded ID recovery base", probe_index)
    probe = workflow[probe_index:recovery_index]

    curl_index = probe.index("curl --retry 3 --retry-all-errors")
    status_output_index = probe.index("-w '%{http_code}'", curl_index)
    transport_guard_index = probe.index('if [ "$curl_exit" -ne 0 ]; then', status_output_index)
    transport_exit_index = probe.index("exit 1", transport_guard_index)
    status_case_index = probe.index('case "$http_status" in', transport_exit_index)
    ok_index = probe.index("200)", status_case_index)
    active_sha_index = probe.index('active_sha="$(python3', ok_index)
    unique_header_index = probe.index("if len(candidates) != 1", active_sha_index)
    active_sha_guard_index = probe.index(
        "if ! printf '%s' \"$active_sha\" | grep -Eq '^[0-9a-f]{40}$'; then",
        unique_header_index,
    )
    malformed_exit_index = probe.index("exit 1", active_sha_guard_index)
    healthy_output_index = probe.index('echo "health_available=true"', malformed_exit_index)
    recoverable_index = probe.index("502|503|504)", healthy_output_index)
    fallback_output_index = probe.index('echo "health_available=false"', recoverable_index)
    default_index = probe.index("*)", fallback_output_index)
    default_exit_index = probe.index("exit 1", default_index)

    assert curl_index < status_output_index < transport_guard_index < transport_exit_index
    assert transport_exit_index < status_case_index < ok_index < active_sha_index
    assert active_sha_index < unique_header_index < active_sha_guard_index
    assert active_sha_guard_index < malformed_exit_index < healthy_output_index
    assert healthy_output_index < recoverable_index < fallback_output_index < default_index < default_exit_index
    assert "-sSf" not in probe
    assert "401" not in probe
    assert "403" not in probe
    assert 'if [ "$curl_exit" -eq 28 ]' not in probe
    assert probe.count('echo "health_available=false"') == 1


def test_guarded_release_base_attestation_uses_only_pinned_id_credentials() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    probe_index = workflow.index("      - name: Probe active ID release")
    recovery_index = workflow.index("      - name: Resolve guarded ID recovery base", probe_index)
    build_step_index = workflow.index("      - name: Build verified release bundle", recovery_index)
    recovery = workflow[recovery_index:build_step_index]

    assert probe_index < recovery_index < build_step_index
    assert "id: attested_release" in recovery
    assert "if: steps.active_release.outputs.health_available != 'true'" in recovery
    assert (
        "uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2"
        in recovery
    )
    assert "host: ${{ secrets.ID_VALIDATION_DEPLOY_HOST }}" in recovery
    assert "username: ${{ secrets.ID_VALIDATION_DEPLOY_USER }}" in recovery
    assert "key: ${{ secrets.ID_VALIDATION_DEPLOY_SSH_KEY }}" in recovery
    assert "fingerprint: ${{ env.EXPECTED_SSH_HOST_FINGERPRINT }}" in recovery
    assert "envs: EXPECTED_REPOSITORY,DEPLOY_TARGET,PUBLIC_HEALTH_URL" in recovery
    assert "script_path: scripts/ops/resolve_id_validation_release_base.sh" in recovery
    assert "capture_stdout: true" in recovery
    assert "script: |" not in recovery
    assert "secrets.TEST_DEPLOY_" not in recovery
    assert "secrets.DEPLOY_" not in recovery


def test_attested_current_head_is_strict_incremental_base_and_never_an_unhealthy_noop() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    build_step_index = workflow.index("      - name: Build verified release bundle")
    noop_step_index = workflow.index("      - name: Verify already active ID release", build_step_index)
    build = workflow[build_step_index:noop_step_index]

    attested_env_index = build.index(
        "ATTESTED_RELEASE_STDOUT: ${{ steps.attested_release.outputs.stdout }}"
    )
    unavailable_case_index = build.index("false)", attested_env_index)
    extractor_index = build.index(
        "python3 scripts/ops/extract_id_validation_release_base.py",
        unavailable_case_index,
    )
    guarded_source_index = build.index('base_source="guarded_server_checkout"', extractor_index)
    same_sha_index = build.index('if [ "$base_sha" = "$verified_sha" ]; then', guarded_source_index)
    public_only_index = build.index('if [ "$base_source" != "public_health" ]; then', same_sha_index)
    unhealthy_exit_index = build.index("exit 1", public_only_index)
    noop_output_index = build.index('echo "noop=true"', unhealthy_exit_index)
    commit_guard_index = build.index('git cat-file -e "$base_sha^{commit}"', noop_output_index)
    ancestry_index = build.index(
        'git merge-base --is-ancestor "$base_sha" "$verified_sha"',
        commit_guard_index,
    )
    base_ref_index = build.index('git update-ref refs/deploy/base "$base_sha"', ancestry_index)
    incremental_bundle_index = build.index(
        "git bundle create release/aicrm-release.bundle refs/deploy/release ^refs/deploy/base",
        base_ref_index,
    )

    assert attested_env_index < unavailable_case_index < extractor_index
    assert extractor_index < guarded_source_index < same_sha_index < public_only_index
    assert public_only_index < unhealthy_exit_index < noop_output_index < commit_guard_index
    assert commit_guard_index < ancestry_index < base_ref_index < incremental_bundle_index
    assert 'bundle_mode="full"' not in build
    assert "git bundle create release/aicrm-release.bundle HEAD" not in build


def test_id_validation_rejects_orphaned_or_non_ancestor_base_without_full_bundle_fallback() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    missing_base_index = workflow.index('if ! git cat-file -e "$base_sha^{commit}"; then')
    missing_base_exit = workflow.index("exit 1", missing_base_index)
    ancestor_index = workflow.index(
        'if ! git merge-base --is-ancestor "$base_sha" "$verified_sha"; then',
        missing_base_exit,
    )
    ancestor_exit = workflow.index("exit 1", ancestor_index)
    incremental_bundle_index = workflow.index(
        "git bundle create release/aicrm-release.bundle refs/deploy/release ^refs/deploy/base",
        ancestor_exit,
    )

    assert missing_base_index < missing_base_exit < ancestor_index < ancestor_exit
    assert ancestor_exit < incremental_bundle_index
    assert "target environment release is not present in repository history" in workflow[
        missing_base_index:missing_base_exit
    ]
    assert "target environment release is not an ancestor of the requested release" in workflow[
        ancestor_index:ancestor_exit
    ]
    assert "An orphaned base must be" in workflow
    assert 'bundle_mode="full"' not in workflow
    assert "full release bundle recovery" not in workflow
    assert "test environment release is orphaned" not in workflow
    assert workflow.count("git bundle create release/aicrm-release.bundle") == 1
    assert "git bundle create release/aicrm-release.bundle refs/deploy/release\n" not in workflow


def test_id_validation_deploy_treats_already_active_sha_as_successful_noop() -> None:
    workflow = _deploy_contract_source()

    active_sha_index = workflow.index('if [ "$base_sha" = "$verified_sha" ]; then')
    public_source_guard_index = workflow.index(
        'if [ "$base_source" != "public_health" ]; then',
        active_sha_index,
    )
    unhealthy_exit_index = workflow.index("exit 1", public_source_guard_index)
    noop_output_index = workflow.index('echo "noop=true" >> "$GITHUB_OUTPUT"', active_sha_index)
    successful_message_index = workflow.index("successful no-op", noop_output_index)
    exit_zero_index = workflow.index("exit 0", successful_message_index)
    bundle_index = workflow.index("git bundle create release/aicrm-release.bundle", exit_zero_index)
    transfer_index = workflow.index("- name: Transfer verified release bundle", bundle_index)
    ssh_index = workflow.index("- name: Deploy via SSH", transfer_index)

    assert active_sha_index < public_source_guard_index < unhealthy_exit_index < noop_output_index
    assert noop_output_index < successful_message_index < exit_zero_index < bundle_index
    assert "same-SHA no-op is forbidden while public health is unavailable" in workflow[
        public_source_guard_index:noop_output_index
    ]
    assert "if: steps.release.outputs.noop != 'true'" in workflow[transfer_index:ssh_index]
    assert "if: steps.release.outputs.noop != 'true'" in workflow[ssh_index:]
    assert "Record successful no-op provenance" in workflow


def test_id_validation_noop_revalidates_origin_checkout_provenance_and_runtime() -> None:
    workflow = _deploy_contract_source()

    noop_index = workflow.index("- name: Verify already active ID release")
    summary_index = workflow.index("- name: Record successful no-op provenance", noop_index)
    transfer_index = workflow.index("- name: Transfer verified release bundle", summary_index)

    assert "if: steps.release.outputs.noop == 'true'" in workflow[noop_index:summary_index]
    lock_index = workflow.index('deploy_lock_file="/tmp/aicrm-deploy-${{ env.DEPLOY_TARGET }}.lock"', noop_index)
    flock_index = workflow.index("if ! flock -n 9; then", lock_index)
    assert 'remote_origin_url="$(git remote get-url origin)"' in workflow[noop_index:summary_index]
    assert 'test "$(git rev-parse HEAD)" = "$verified_sha"' in workflow[noop_index:summary_index]
    assert 'test "$(tr -d \'\\r\\n\' < .release-sha)" = "$verified_sha"' in workflow[noop_index:summary_index]
    assert "/home/ubuntu/.aicrm-releases/id-validation.json" in workflow[noop_index:summary_index]
    assert 'git status --porcelain=v1 --untracked-files=all' in workflow[noop_index:summary_index]
    assert "same-SHA verification refuses a dirty server checkout" in workflow[noop_index:summary_index]
    verify_index = workflow.index(_runtime_units_phase("verify"), noop_index)
    readiness_index = workflow.index("scripts/ops/check_id_validation_release_readiness.py", verify_index)
    recovery_index = workflow.index("scripts/ops/recover_id_validation_provenance.py", readiness_index)
    assert "id-validation.pending.json" in workflow[recovery_index:summary_index]
    assert '--expected-release-sha "$verified_sha"' in workflow[recovery_index:summary_index]
    assert '--expected-source-ci-run-id "${{ github.event.workflow_run.id }}"' in workflow[recovery_index:summary_index]
    assert '--expected-deploy-run-id "${{ github.run_id }}"' in workflow[recovery_index:summary_index]
    assert "--promote-pending" in workflow[recovery_index:summary_index]
    assert "--allow-prepared-recovery" in workflow[recovery_index:summary_index]
    assert verify_index < readiness_index < recovery_index
    assert "id-validation-last-verified.json" in workflow[noop_index:summary_index]
    assert noop_index < lock_index < flock_index < summary_index < transfer_index


def test_id_validation_deploy_pins_authenticated_server_host_key() -> None:
    workflow = _deploy_contract_source()
    expected = "SHA256:NXSJUveGoNy1lDsa+eOKho1h0ythB+pKTyijv8/KfU0"

    assert f"EXPECTED_SSH_HOST_FINGERPRINT: {expected}" in workflow
    assert workflow.count("fingerprint: ${{ env.EXPECTED_SSH_HOST_FINGERPRINT }}") == 4


def test_id_validation_deploy_records_exact_repository_run_and_bundle_provenance() -> None:
    workflow = _deploy_contract_source()

    remote_index = workflow.index("- name: Deploy via SSH")
    repository_guard_index = workflow.index('if [ "$release_repository" != "$expected_repository" ]; then', remote_index)
    origin_guard_index = workflow.index('remote_origin_url="$(git remote get-url origin)"', repository_guard_index)
    lock_index = workflow.index('deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"', origin_guard_index)
    checksum_index = workflow.index('if [ "$actual_bundle_sha256" != "$bundle_sha256" ]; then', lock_index)
    mutation_index = workflow.index("runtime_mutation_started=1", checksum_index)
    public_sha_index = workflow.index(
        'grep -i "x-aicrm-release-sha: $after_sha"',
        workflow.index("public_release_ready=0", mutation_index),
    )
    final_readiness_index = workflow.index(
        "scripts/ops/check_id_validation_release_readiness.py", public_sha_index
    )
    provenance_index = workflow.index('RELEASE_REPOSITORY="$release_repository"', final_readiness_index)
    prepared_stage_index = workflow.index(
        'mv -f "$release_provenance_tmp" "$release_provenance_prepared"', provenance_index
    )
    file_fsync_index = workflow.index('fsync_provenance_file "$release_provenance_tmp"', provenance_index)
    release_guard_index = workflow.index(_runtime_units_phase("release-runtime-guard"), provenance_index)
    pending_commit_index = workflow.index(
        'mv -f "$release_provenance_prepared" "$release_provenance_pending"', release_guard_index
    )
    provenance_commit_index = workflow.index(
        'mv -f "$release_provenance_pending" /home/ubuntu/.aicrm-releases/id-validation.json',
        release_guard_index,
    )
    runtime_commit_index = workflow.index("runtime_committed=1", release_guard_index)
    release_commit_index = workflow.index("release_committed=1", provenance_commit_index)

    assert repository_guard_index < origin_guard_index < lock_index < checksum_index < mutation_index
    assert public_sha_index < final_readiness_index < provenance_index < file_fsync_index
    assert file_fsync_index < prepared_stage_index
    assert prepared_stage_index < release_guard_index < runtime_commit_index
    assert runtime_commit_index < pending_commit_index < provenance_commit_index < release_commit_index
    assert '"repository": os.environ["RELEASE_REPOSITORY"]' in workflow
    assert '"deploy_run_id": os.environ["RELEASE_RUN_ID"]' in workflow
    assert '"source_ci_run_id": os.environ["SOURCE_CI_RUN_ID"]' in workflow
    assert '"bundle_sha256": os.environ["BUNDLE_SHA256"]' in workflow
    assert '"environment": "id-validation"' in workflow


def test_newer_main_recovers_active_release_provenance_before_switching_checkout() -> None:
    workflow = _deploy_contract_source()

    fetch_index = workflow.index(
        'git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/deploy/main"'
    )
    recovery_guard_index = workflow.index(
        'if [ -e "$release_provenance_pending" ]', fetch_index
    )
    runtime_verify_index = workflow.index(_runtime_units_phase("verify"), recovery_guard_index)
    readiness_index = workflow.index(
        "scripts/ops/check_id_validation_release_readiness.py", runtime_verify_index
    )
    recovery_index = workflow.index(
        '"$release_control_dir/scripts/ops/recover_id_validation_provenance.py"', readiness_index
    )
    reset_index = workflow.index('git reset --hard "$verified_sha"', recovery_index)

    assert fetch_index < recovery_guard_index < runtime_verify_index < readiness_index < recovery_index
    assert recovery_index < reset_index
    recovery_block = workflow[recovery_guard_index:reset_index]
    assert '--expected-release-sha "$before_sha"' in recovery_block
    assert "--repository-path '/home/ubuntu/极简 crm'" in recovery_block
    assert "--require-canonical-base-chain" in recovery_block
    assert "--allow-prepared-recovery" in recovery_block
    assert "rerun its same-SHA deployment before a new release" not in workflow


def test_production_deploy_requires_remote_head_to_match_bundle_prerequisite_before_fetch():
    workflow = _deploy_contract_source()

    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"')
    base_sha_index = workflow.index('base_sha="${BASE_SHA}"')
    base_guard_index = workflow.index('if [ "$before_sha" != "$base_sha" ]; then')
    bundle_verify_index = workflow.index('git bundle verify "$release_bundle"')
    stash_index = workflow.index("git stash push --include-untracked")
    fetch_index = workflow.index('git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/deploy/main"')
    stop_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")

    assert before_sha_index < base_sha_index < base_guard_index < bundle_verify_index < stash_index < fetch_index < stop_index
    assert "target checkout moved after the incremental release bundle was built" in workflow


def test_guarded_base_is_re_attested_under_final_remote_lock_before_any_mutation() -> None:
    remote_script = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")

    lock_index = remote_script.index('deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"')
    flock_index = remote_script.index("if ! flock -n 9; then", lock_index)
    before_sha_index = remote_script.index('before_sha="$(git rev-parse HEAD)"', flock_index)
    source_index = remote_script.index('readonly base_source="${BASE_SOURCE}"', before_sha_index)
    source_guard_index = remote_script.index('case "$base_source" in', source_index)
    head_cas_index = remote_script.index('if [ "$before_sha" != "$base_sha" ]; then', source_guard_index)
    guarded_index = remote_script.index(
        'if [ "$base_source" = "guarded_server_checkout" ]; then',
        head_cas_index,
    )
    origin_index = remote_script.index('remote_origin_url="$(git remote get-url origin)"', guarded_index)
    marker_symlink_index = remote_script.index('if [ -L .release-sha ]', origin_index)
    marker_bytes_index = remote_script.index('raw = Path(".release-sha").read_bytes()', marker_symlink_index)
    marker_regex_index = remote_script.index(
        're.fullmatch(rb"[0-9a-f]{40}", raw)',
        marker_bytes_index,
    )
    marker_cas_index = remote_script.index(
        'if [ "$release_marker_sha" != "$base_sha" ]; then',
        marker_regex_index,
    )
    clean_index = remote_script.index(
        'git status --porcelain=v1 --untracked-files=all',
        marker_cas_index,
    )
    bundle_index = remote_script.index('release_bundle_dir="/tmp/aicrm-release-$verified_sha"', clean_index)
    stash_index = remote_script.index("git stash push --include-untracked", bundle_index)

    assert lock_index < flock_index < before_sha_index < source_index < source_guard_index
    assert source_guard_index < head_cas_index < guarded_index < origin_index < marker_symlink_index
    assert marker_symlink_index < marker_bytes_index < marker_regex_index < marker_cas_index
    assert marker_cas_index < clean_index < bundle_index < stash_index
    guarded_block = remote_script[guarded_index:bundle_index]
    assert "guarded release base origin changed after attestation" in guarded_block
    assert "guarded release marker changed after attestation" in guarded_block
    assert "guarded release checkout became dirty after attestation" in guarded_block
    assert "tr -d" not in guarded_block


def test_guarded_checkout_uses_idempotent_runtime_stop_without_weakening_normal_deploy() -> None:
    remote_script = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")

    identity_preflight_index = remote_script.index(
        "python3 scripts/ops/check_unionid_identity_cutover.py"
    )
    begin_index = remote_script.index(
        "--phase begin-transaction --execute",
        identity_preflight_index,
    )
    guarded_branch_index = remote_script.index(
        'if [ "$base_source" = "guarded_server_checkout" ]; then',
        begin_index,
    )
    recovery_stop_index = remote_script.index(
        "--phase stop-for-migration-recovery --execute",
        guarded_branch_index,
    )
    normal_stop_index = remote_script.index(
        "--phase stop-for-migration --execute",
        recovery_stop_index,
    )
    stopped_index = remote_script.index("runtime_units_stopped=1", normal_stop_index)

    assert begin_index < guarded_branch_index < recovery_stop_index < normal_stop_index
    assert normal_stop_index < stopped_index
    branch = remote_script[guarded_branch_index:stopped_index]
    assert "guarded recovery accepts enabled runtime units that are already inactive" in branch
    assert branch.count("--phase stop-for-migration-recovery --execute") == 1
    assert branch.count("--phase stop-for-migration --execute") == 1


def test_incremental_release_bundle_requires_live_base_and_fetches_exact_merge_sha(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "AI CRM CI")
    _git(source, "config", "user.email", "ci@example.invalid")

    (source / "root.txt").write_text("root\n", encoding="utf-8")
    _git(source, "add", "root.txt")
    _git(source, "commit", "-m", "root")
    root_sha = _git(source, "rev-parse", "HEAD").stdout.strip()
    _git(source, "branch", "feature")

    (source / "main.txt").write_text("main\n", encoding="utf-8")
    _git(source, "add", "main.txt")
    _git(source, "commit", "-m", "main")
    base_sha = _git(source, "rev-parse", "HEAD").stdout.strip()

    _git(source, "checkout", "feature")
    (source / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(source, "add", "feature.txt")
    _git(source, "commit", "-m", "feature")
    _git(source, "checkout", "main")
    _git(source, "merge", "--no-ff", "feature", "-m", "merge")
    verified_sha = _git(source, "rev-parse", "HEAD").stdout.strip()
    _git(source, "update-ref", "refs/deploy/release", verified_sha)
    _git(source, "update-ref", "refs/deploy/base", base_sha)
    _git(source, "branch", "release-root", root_sha)
    _git(source, "branch", "release-base", base_sha)

    bundle = tmp_path / "aicrm-release.bundle"
    _git(source, "bundle", "create", str(bundle), "refs/deploy/release", "^refs/deploy/base")

    missing_base = tmp_path / "missing-base"
    missing_base.mkdir()
    _git(missing_base, "init")
    _git(missing_base, "fetch", str(source), "release-root:refs/heads/release-root")
    missing_verify = _git(missing_base, "bundle", "verify", str(bundle), check=False)
    assert missing_verify.returncode != 0

    receiver = tmp_path / "receiver"
    receiver.mkdir()
    _git(receiver, "init")
    _git(receiver, "fetch", str(source), "release-base:refs/heads/release-base")
    _git(receiver, "bundle", "verify", str(bundle))
    _git(
        receiver,
        "fetch",
        "--no-tags",
        str(bundle),
        "refs/deploy/release:refs/remotes/aicrm-release/main",
    )
    release_sha = _git(receiver, "rev-parse", "refs/remotes/aicrm-release/main").stdout.strip()
    assert release_sha == verified_sha


def test_production_deploy_refreshes_release_marker_before_restart_and_checks_health_header():
    workflow = _deploy_contract_source()

    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    marker_index = workflow.index("printf '%s\\n' \"$after_sha\" > .release-sha")
    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    header_curl_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health")
    header_grep_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt')
    ready_guard_index = workflow.index('if [ "$release_ready" != "1" ]; then')

    assert after_sha_index < marker_index < start_index < header_curl_index < header_grep_index < ready_guard_index


def test_production_deploy_quiesces_web_before_alembic_and_service_restart():
    workflow = _deploy_contract_source()

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    begin_transaction_index = workflow.index("--phase begin-transaction --execute", workflow.index("runtime_mutation_started=1"))
    stop_runtime_units_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    stash_index = workflow.index("git stash push --include-untracked")
    reset_index = workflow.index('git reset --hard "$verified_sha"', stash_index)
    pip_install_index = workflow.index("python -m pip install --require-hashes -r requirements.lock", reset_index)
    preflight_index = workflow.index("--phase preflight", reset_index)
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    stale_listener_index = workflow.index("if sudo fuser -s 5001/tcp; then", stop_runtime_units_index)
    term_kill_index = workflow.index("sudo fuser -k -TERM 5001/tcp || true")
    force_kill_index = workflow.index("sudo fuser -k -KILL 5001/tcp || true")
    wait_for_free_index = workflow.index('echo "waiting for stale 5001 listener to exit"')
    reset_failed_index = workflow.index("sudo systemctl reset-failed openclaw-wecom-postgres.service || true", alembic_upgrade_index)
    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    alembic_table = "alembic_" + "version"

    assert env_source_index < database_url_guard_index < alembic_upgrade_index
    assert (
        stash_index
        < reset_index
        < pip_install_index
        < preflight_index
        < begin_transaction_index
        < stop_runtime_units_index
        < stale_listener_index
        < term_kill_index
        < force_kill_index
        < wait_for_free_index
        < alembic_upgrade_index
        < reset_failed_index
        < start_index
    )
    assert "sudo fuser -TERM 5001/tcp" not in workflow
    assert "sudo fuser -KILL 5001/tcp" not in workflow
    assert "python3 app.py init-db" not in workflow
    assert "python app.py init-db" not in workflow
    assert "alembic stamp head" not in workflow
    assert "systemctl mask --runtime" not in workflow
    assert "systemctl unmask --runtime" not in workflow
    assert f"ALTER TABLE IF EXISTS {alembic_table}" not in workflow
    assert f"ALTER TABLE {alembic_table}" not in workflow


def test_production_deploy_migrates_and_reconciles_secret_references_before_web_restart():
    workflow = _deploy_contract_source()

    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    migration_index = workflow.index("python3 scripts/ops/migrate_app_setting_secrets.py --execute")
    auth_bootstrap_index = workflow.index("python3 scripts/ops/bootstrap_auth_clients.py", migration_index)
    refreshed_env_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env", migration_index)
    auth_readiness_index = workflow.index("python3 scripts/ops/check_auth_readiness.py", refreshed_env_index)
    reconciliation_index = workflow.index("python3 scripts/ops/check_secret_reference_cutover.py")
    stop_web_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    start_web_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")

    assert (
        stop_web_index
        < alembic_upgrade_index
        < migration_index
        < auth_bootstrap_index
        < refreshed_env_index
        < auth_readiness_index
        < reconciliation_index
        < start_web_index
    )
    assert '--secret-store-dir "$AICRM_SECRET_STORE_DIR"' in workflow
    assert "--environment-file /home/ubuntu/.openclaw-wecom-pg.env" in workflow
    assert "tee /tmp/aicrm-secret-migration.json" in workflow
    assert "--apply" in workflow[auth_bootstrap_index:refreshed_env_index]
    assert '--issuer "$auth_issuer"' in workflow[auth_bootstrap_index:reconciliation_index]
    assert 'auth_issuer="${public_base_url}"' in workflow
    assert "tee /tmp/aicrm-auth-client-bootstrap.json" in workflow
    assert "tee /tmp/aicrm-auth-readiness.json" in workflow
    assert "tee /tmp/aicrm-secret-reconciliation.json" in workflow
    assert "set -x" not in workflow


def test_id_validation_deploy_serializes_workflow_and_host_transactions():
    workflow = _deploy_contract_source()

    assert "group: aicrm-id-validation-deploy" in workflow
    assert "cancel-in-progress: false" in workflow
    deploy_step_index = workflow.index("- name: Deploy via SSH")
    remote_deploy_index = workflow.index(
        "uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2",
        deploy_step_index,
    )
    lock_path_index = workflow.index('deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"', remote_deploy_index)
    lock_fd_index = workflow.index('exec 9>"$deploy_lock_file"', lock_path_index)
    flock_index = workflow.index("if ! flock -n 9; then", lock_fd_index)
    checkout_mutation_index = workflow.index("git stash push --include-untracked", flock_index)

    assert remote_deploy_index < lock_path_index < lock_fd_index < flock_index < checkout_mutation_index


def test_production_deploy_failure_after_quiesce_is_fail_closed():
    workflow = _deploy_contract_source()

    cleanup_index = workflow.index("cleanup_deploy()")
    trap_index = workflow.index("trap cleanup_deploy EXIT", cleanup_index)
    mutation_flag_index = workflow.index("runtime_mutation_started=1", trap_index)
    begin_runtime_index = workflow.index("--phase begin-transaction --execute", mutation_flag_index)
    stop_runtime_index = workflow.index("--phase stop-for-migration --execute", begin_runtime_index)
    cleanup_guard_index = workflow.index('[ "${runtime_mutation_started:-0}" = "1" ]', cleanup_index)
    cleanup_begin_index = workflow.index(
        "--phase begin-transaction --execute",
        cleanup_guard_index,
    )
    cleanup_stop_runtime_index = workflow.index("--phase ensure-stopped-for-rollback --execute", cleanup_begin_index)
    cleanup_stop_web_index = workflow.index("sudo systemctl stop openclaw-wecom-postgres.service || true", cleanup_guard_index)
    deploy_stop_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    install_web_index = workflow.index(_runtime_units_phase("install-primary-web"), reset_index)
    authorize_web_index = workflow.index(_runtime_units_phase("authorize-web-start"), install_web_index)
    start_web_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then", authorize_web_index)
    readiness_index = workflow.index("python scripts/ops/check_runtime_secret_readiness.py", start_web_index)
    authorize_runtime_index = workflow.index(_runtime_units_phase("authorize-runtime-start"), readiness_index)
    staged_verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"), authorize_runtime_index)
    public_health_index = workflow.index("public_release_ready=0", staged_verify_index)
    provenance_index = workflow.index('RELEASE_REPOSITORY="$release_repository"', public_health_index)
    release_guard_index = workflow.index(_runtime_units_phase("release-runtime-guard"), provenance_index)
    commit_index = workflow.index("runtime_committed=1", release_guard_index)

    assert cleanup_index < trap_index < mutation_flag_index < begin_runtime_index < stop_runtime_index
    assert cleanup_guard_index < cleanup_begin_index < cleanup_stop_runtime_index < cleanup_stop_web_index
    assert reset_index < deploy_stop_index < install_web_index < authorize_web_index < start_web_index
    assert start_web_index < readiness_index < authorize_runtime_index < staged_verify_index < public_health_index
    assert public_health_index < provenance_index < release_guard_index < commit_index
    assert release_guard_index < workflow.index("runtime_committed=1", release_guard_index)
    assert "systemctl mask --runtime" not in workflow


def test_production_deploy_installs_managed_web_and_checks_runtime_secret_readiness_before_workers():
    workflow = _deploy_contract_source()

    reconciliation_index = workflow.index("python3 scripts/ops/check_secret_reference_cutover.py")
    install_web_index = workflow.index(_runtime_units_phase("install-primary-web"), reconciliation_index)
    start_web_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then", install_web_index)
    readiness_index = workflow.index("python scripts/ops/check_runtime_secret_readiness.py", start_web_index)
    authorize_runtime_index = workflow.index(_runtime_units_phase("authorize-runtime-start"), readiness_index)
    worker_install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"), readiness_index)
    staged_verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"), worker_install_index)
    public_health_index = workflow.index("public_release_ready=0", staged_verify_index)
    release_guard_index = workflow.index(_runtime_units_phase("release-runtime-guard"), public_health_index)

    assert reconciliation_index < install_web_index < start_web_index < readiness_index < authorize_runtime_index
    assert authorize_runtime_index < worker_install_index < staged_verify_index < public_health_index < release_guard_index
    assert '--expected-sha "$after_sha"' in workflow[readiness_index:worker_install_index]
    assert '--expected-callback-url "$auth_issuer/auth/wecom/callback"' in workflow[readiness_index:worker_install_index]
    assert "tee /tmp/aicrm-runtime-secret-readiness.json" in workflow[readiness_index:worker_install_index]


def test_deploy_repairs_customer_projection_through_durable_runtime_before_guarding_workers() -> None:
    workflow = _deploy_contract_source()

    identity_preflight_index = workflow.index("python3 scripts/ops/check_unionid_identity_cutover.py")
    refresh_intent_index = workflow.index("python3 scripts/run_customer_read_model_refresh.py", identity_preflight_index)
    mutation_index = workflow.index("runtime_mutation_started=1", refresh_intent_index)
    begin_index = workflow.index("--phase begin-transaction --execute", mutation_index)
    refresh_block = workflow[refresh_intent_index:mutation_index]

    assert identity_preflight_index < refresh_intent_index < mutation_index < begin_index
    assert '--source-key "deploy_preflight:${release_run_id}:${release_run_attempt}"' in refresh_block
    assert "--wait-seconds 180" in refresh_block
    assert "run_customer_read_model_refresh.py --execute" not in workflow[mutation_index:]
    assert "CustomerReadModelRefreshService().run" not in refresh_block


def test_id_validation_deploy_keeps_public_route_read_only_and_requires_public_exact_sha():
    workflow = _deploy_contract_source()

    local_health_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"')
    runtime_verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    public_health_index = workflow.index("public_release_ready=0", runtime_verify_index)
    public_sha_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"', public_health_index)
    provenance_index = workflow.index('RELEASE_REPOSITORY="$release_repository"', public_sha_index)

    assert local_health_index < runtime_verify_index < public_health_index < public_sha_index < provenance_index
    assert "PUBLIC_HEALTH_URL: https://id-dev.youcangogogo.com/health" in workflow
    assert "scripts/ops/ensure_production_public_release_route.py" not in workflow
    assert "PUBLIC_SERVER_NAME" not in workflow
    assert "NGINX_CONFIG_PATH" not in workflow


def test_id_validation_deploy_uses_only_id_validation_secrets_and_public_health_check():
    workflow = _deploy_contract_source()

    runtime_verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    public_health_index = workflow.index('"${public_health_url}"', runtime_verify_index)

    assert runtime_verify_index < public_health_index
    assert "secrets.ID_VALIDATION_DEPLOY_HOST" in workflow
    assert "secrets.ID_VALIDATION_DEPLOY_USER" in workflow
    assert "secrets.ID_VALIDATION_DEPLOY_SSH_KEY" in workflow
    assert "secrets.TEST_DEPLOY_HOST" not in workflow
    assert "secrets.DEPLOY_HOST" not in workflow
    assert 'if [ "$deploy_target" = "production" ]; then' not in workflow
    assert 'grep -i "x-aicrm-release-sha: $after_sha"' in workflow


def test_production_deploy_polls_health_after_restart_instead_of_fixed_sleep():
    workflow = _deploy_contract_source()

    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    poll_index = workflow.index("for _ in $(seq 1 60); do", start_index)
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", poll_index)
    header_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt', health_index)
    ready_guard_index = workflow.index('if [ "$release_ready" != "1" ]; then', header_index)
    status_index = workflow.index("sudo systemctl status openclaw-wecom-postgres.service --no-pager || true", ready_guard_index)

    assert start_index < poll_index < health_index < header_index < status_index
    assert "sleep 3" not in workflow


def test_deploy_admin_smoke_uses_short_lived_server_session_without_logging_cookie():
    workflow = _deploy_contract_source()

    issue_index = workflow.index("python3 scripts/ops/create_deploy_smoke_session.py issue")
    smoke_index = workflow.index("python scripts/ops/check_admin_read_pages_smoke.py", issue_index)
    revoke_index = workflow.index('revoke_deploy_smoke_session "$deploy_smoke_session_file"', smoke_index)
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))

    assert issue_index < smoke_index < revoke_index < install_index < verify_index
    assert 'deploy_smoke_session_file="$(mktemp /tmp/aicrm-deploy-smoke-session.XXXXXX)"' in workflow
    assert '--output-file "$deploy_smoke_session_file"' in workflow
    assert "--ttl-seconds 300" in workflow
    assert '--admin-cookie-file "$deploy_smoke_session_file"' in workflow
    assert 'admin_smoke_sidebar_args=(--include-all-sidebar --require-all-data-health-green)' in workflow
    assert 'if [ "$deploy_target" = "production" ]; then' not in workflow[:smoke_index]
    assert '--cookie-file "$cookie_file"' in workflow
    assert "aicrm_next_admin_session=" not in workflow
    assert 'cat "$deploy_smoke_session_file"' not in workflow
    assert 'echo "$deploy_smoke_session_file"' not in workflow
    assert '| tee /tmp/aicrm-deploy-smoke-session-revoke.json' not in workflow
    assert 'report_file="$(mktemp /tmp/aicrm-deploy-smoke-session-revoke.XXXXXX)"' in workflow
    assert 'revoke_deploy_smoke_session "$deploy_smoke_session_file"' in workflow
    system_health_index = workflow.index("verify_system_health_for_runtime_release", revoke_index)
    authorize_index = workflow.index("--phase authorize-runtime-start --execute", system_health_index)
    assert revoke_index < system_health_index < authorize_index < install_index
    assert "aicrm-pre-runtime-release-system-health.json" in workflow[system_health_index:authorize_index]
    assert "print_runtime_release_diagnostics" in workflow[system_health_index:install_index]


def test_release_safe_system_health_helper_preserves_validator_exit_status_in_shell_condition(tmp_path: Path) -> None:
    workflow = _deploy_contract_source()
    start = workflow.index("            verify_system_health_for_runtime_release() {")
    end = workflow.index("            print_runtime_release_diagnostics() {", start)
    function_source = "\n".join(
        line.removeprefix("            ") for line in workflow[start:end].splitlines()
    )

    for validator_status, expected_status in ((0, 0), (7, 1)):
        report_file = tmp_path / f"system-health-{validator_status}.json"
        harness = f"""
set -euo pipefail
curl() {{
  local headers_file=""
  local report_file=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -D) shift; headers_file="$1" ;;
      -o) shift; report_file="$1" ;;
    esac
    shift
  done
  : > "$headers_file"
  printf '%s\n' '{{"ok":true}}' > "$report_file"
}}
python3() {{ return {validator_status}; }}
sleep() {{ :; }}
{function_source}
if verify_system_health_for_runtime_release "{'a' * 40}" "{report_file}"; then
  exit 0
fi
exit 1
"""
        completed = subprocess.run(["bash", "-c", harness], check=False, capture_output=True, text=True)
        assert completed.returncode == expected_status, completed.stderr


def test_schema_aligned_failure_never_reopens_an_incompatible_previous_release() -> None:
    workflow = _deploy_contract_source()

    archive_index = workflow.index('git archive "$before_sha" alembic.ini migrations')
    reset_index = workflow.index('git reset --hard "$verified_sha"', archive_index)
    preflight_index = workflow.index("refresh_schema_recovery_target", reset_index)
    migration_index = workflow.index("python3 -m alembic upgrade head", preflight_index)
    alignment_index = workflow.index("refresh_schema_recovery_target", migration_index)
    smoke_index = workflow.index("verified_release_web_smoke_passed=1", alignment_index)
    cleanup_index = workflow.index("cleanup_deploy() {")
    cleanup_refresh_index = workflow.index("refresh_schema_recovery_target", cleanup_index)
    cleanup_reset_index = workflow.index('git reset --hard "$before_sha"', cleanup_refresh_index)
    preserve_index = workflow.index(
        'schema already matches verified release; preserving smoke-verified checkout $verified_sha',
        cleanup_index,
    )
    guarded_index = workflow.index(
        "schema already matches verified release but Web smoke did not pass; keeping runtime guarded",
        cleanup_index,
    )

    assert archive_index < reset_index < preflight_index < migration_index < alignment_index < smoke_index
    assert cleanup_index < cleanup_refresh_index < cleanup_reset_index
    assert cleanup_index < preserve_index < guarded_index
    assert 'target="previous" if matches_previous else ("verified" if matches_verified else "unknown")' in workflow
    assert '[ "${schema_recovery_target:-unknown}" = "unknown" ]' in workflow
    assert '[ "${schema_recovery_target:-unknown}" = "verified" ]' in workflow
    assert 'restore_expected_sha="$verified_sha"' in workflow[preserve_index:guarded_index]
    assert "restore_runtime_allowed=0" in workflow[guarded_index:]
    assert "alembic downgrade" not in workflow


def test_runtime_commit_is_the_cleanup_point_of_no_return() -> None:
    workflow = _deploy_contract_source()

    guard_index = workflow.index(
        _runtime_units_phase("release-runtime-guard"),
        workflow.index('RELEASE_REPOSITORY="$release_repository"'),
    )
    runtime_commit_index = workflow.index("runtime_committed=1", guard_index)
    provenance_move_index = workflow.index(
        'mv -f "$release_provenance_pending" /home/ubuntu/.aicrm-releases/id-validation.json',
        runtime_commit_index,
    )
    release_commit_index = workflow.index("release_committed=1", provenance_move_index)
    cleanup = workflow[workflow.index("cleanup_deploy() {") : workflow.index("trap cleanup_deploy EXIT")]

    assert guard_index < runtime_commit_index < provenance_move_index < release_commit_index
    assert cleanup.count('[ "${runtime_committed:-0}" != "1" ]') >= 3
    assert "preserving validated pending provenance for same-SHA no-op recovery" in cleanup


def test_schema_recovery_classifier_prefers_previous_and_fails_closed(tmp_path: Path) -> None:
    workflow = _deploy_contract_source()
    start = workflow.index("            refresh_schema_recovery_target() {")
    end = workflow.index("            cleanup_deploy() {", start)
    function_source = "\n".join(
        line.removeprefix("            ") for line in workflow[start:end].splitlines()
    )

    scenarios = {
        "previous:0": ("previous", "0"),
        "previous:1": ("previous", "1"),
        "verified:1": ("verified", "1"),
        "unknown:0": ("unknown", "0"),
        "failure": ("unknown", "0"),
    }
    for classification, expected in scenarios.items():
        result_file = tmp_path / f"classification-{classification.replace(':', '-')}.txt"
        harness = f"""
set -euo pipefail
CLASSIFICATION={classification!r}
classify_schema_recovery_target() {{
  if [ "$CLASSIFICATION" = "failure" ]; then
    return 1
  fi
  printf '%s\n' "$CLASSIFICATION"
}}
{function_source}
refresh_schema_recovery_target
printf '%s:%s\n' "$schema_recovery_target" "$schema_aligned_to_verified_release" > {str(result_file)!r}
"""
        completed = subprocess.run(["bash", "-c", harness], check=False, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
        assert result_file.read_text(encoding="utf-8").strip() == ":".join(expected)


def test_cleanup_uses_live_schema_target_before_any_checkout_rollback(tmp_path: Path) -> None:
    workflow = _deploy_contract_source()
    start = workflow.index("            cleanup_deploy() {")
    end = workflow.index("            trap cleanup_deploy EXIT", start)
    cleanup_source = "\n".join(
        line.removeprefix("            ") for line in workflow[start:end].splitlines()
    )

    for recovery_target in ("previous", "verified", "unknown"):
        audit_file = tmp_path / f"cleanup-{recovery_target}.log"
        harness = f"""
set -u
AUDIT_FILE={str(audit_file)!r}
TARGET={recovery_target!r}
python3() {{ printf 'python3 %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
sudo() {{ printf 'sudo %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
git() {{ printf 'git %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
rm() {{ return 0; }}
refresh_schema_recovery_target() {{
  printf 'refresh %s\n' "$TARGET" >> "$AUDIT_FILE"
  schema_recovery_target="$TARGET"
  if [ "$TARGET" = "verified" ]; then
    schema_aligned_to_verified_release=1
  else
    schema_aligned_to_verified_release=0
  fi
}}
restore_runtime_from_guard() {{ printf 'restore %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
resecure_runtime_guard() {{ printf 'resecure\n' >> "$AUDIT_FILE"; return 0; }}
print_runtime_release_diagnostics() {{ :; }}
verify_system_health_for_runtime_release() {{ return 1; }}
revoke_deploy_smoke_session() {{ return 0; }}
{cleanup_source}
runtime_mutation_started=0
runtime_committed=0
runtime_units_stopped=0
runtime_transaction_partial=0
release_switched=1
release_committed=0
schema_recovery_target=unknown
schema_aligned_to_verified_release=0
verified_release_web_smoke_passed=0
restore_runtime_allowed=1
restore_expected_sha=before
before_sha=before
verified_sha=verified
release_control_manager=manager
release_control_manifest=manifest
release_control_dir=""
release_bundle_dir=""
release_provenance_tmp=""
deploy_smoke_session_file=""
false
cleanup_deploy
"""
        completed = subprocess.run(
            ["bash", "-c", harness], cwd=tmp_path, check=False, capture_output=True, text=True
        )
        assert completed.returncode == 1, completed.stderr
        audit = audit_file.read_text(encoding="utf-8")
        assert f"refresh {recovery_target}" in audit
        if recovery_target == "previous":
            assert "git reset --hard before" in audit
            assert "ensure-stopped-for-rollback" not in audit
        else:
            assert "ensure-stopped-for-rollback --execute" in audit
            assert "git reset --hard before" not in audit
            assert "restore " not in audit


def test_provenance_move_failure_after_runtime_commit_never_resecures_runtime(tmp_path: Path) -> None:
    workflow = _deploy_contract_source()
    start = workflow.index("            cleanup_deploy() {")
    end = workflow.index("            trap cleanup_deploy EXIT", start)
    cleanup_source = "\n".join(
        line.removeprefix("            ") for line in workflow[start:end].splitlines()
    )
    audit_file = tmp_path / "runtime-committed-cleanup.log"
    pending_file = tmp_path / "id-validation.pending.json"
    pending_file.write_text('{"validated":true}', encoding="utf-8")
    harness = f"""
set -u
AUDIT_FILE={str(audit_file)!r}
PENDING_FILE={str(pending_file)!r}
python3() {{ printf 'python3 %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
sudo() {{ printf 'sudo %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
git() {{ printf 'git %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
rm() {{
  for argument in "$@"; do
    if [ "$argument" = "$PENDING_FILE" ]; then printf 'remove-pending\n' >> "$AUDIT_FILE"; fi
  done
  return 0
}}
refresh_schema_recovery_target() {{ printf 'refresh\n' >> "$AUDIT_FILE"; return 0; }}
restore_runtime_from_guard() {{ printf 'restore\n' >> "$AUDIT_FILE"; return 0; }}
resecure_runtime_guard() {{ printf 'resecure\n' >> "$AUDIT_FILE"; return 0; }}
print_runtime_release_diagnostics() {{ :; }}
verify_system_health_for_runtime_release() {{ return 1; }}
revoke_deploy_smoke_session() {{ return 0; }}
{cleanup_source}
runtime_mutation_started=1
runtime_committed=1
runtime_units_stopped=0
runtime_transaction_partial=0
release_switched=1
release_committed=0
schema_recovery_target=verified
schema_aligned_to_verified_release=1
verified_release_web_smoke_passed=1
restore_runtime_allowed=1
restore_expected_sha=verified
before_sha=before
verified_sha=verified
release_control_manager=manager
release_control_manifest=manifest
release_control_dir=""
release_bundle_dir=""
release_provenance_tmp=""
release_provenance_pending="$PENDING_FILE"
release_provenance_pending_owned=1
deploy_smoke_session_file=""
false
cleanup_deploy
"""
    completed = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, check=False, capture_output=True, text=True
    )

    assert completed.returncode == 1, completed.stderr
    assert not audit_file.exists() or audit_file.read_text(encoding="utf-8") == ""
    assert pending_file.exists()


def test_dependency_rollback_failure_keeps_runtime_guarded(tmp_path: Path) -> None:
    workflow = _deploy_contract_source()
    start = workflow.index("            cleanup_deploy() {")
    end = workflow.index("            trap cleanup_deploy EXIT", start)
    cleanup_source = "\n".join(
        line.removeprefix("            ") for line in workflow[start:end].splitlines()
    ).replace("/home/ubuntu/venvs/openclaw/bin/python", "venv_python")

    for initially_stopped in (0, 1):
        audit_file = tmp_path / f"dependency-rollback-{initially_stopped}.log"
        harness = f"""
set -u
AUDIT_FILE={str(audit_file)!r}
python3() {{ printf 'python3 %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
venv_python() {{ printf 'venv-python %s\n' "$*" >> "$AUDIT_FILE"; return 1; }}
sudo() {{ printf 'sudo %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
git() {{
  printf 'git %s\n' "$*" >> "$AUDIT_FILE"
  if [ "${{1:-}}" = "diff" ]; then
    return 1
  fi
  return 0
}}
rm() {{ return 0; }}
refresh_schema_recovery_target() {{ schema_recovery_target=previous; schema_aligned_to_verified_release=0; }}
restore_runtime_from_guard() {{ printf 'restore %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
resecure_runtime_guard() {{ printf 'resecure\n' >> "$AUDIT_FILE"; return 0; }}
print_runtime_release_diagnostics() {{ :; }}
verify_system_health_for_runtime_release() {{ return 1; }}
revoke_deploy_smoke_session() {{ return 0; }}
{cleanup_source}
runtime_mutation_started=0
runtime_committed=0
runtime_units_stopped={initially_stopped}
runtime_transaction_partial=$((1 - runtime_units_stopped))
release_switched=1
release_committed=0
schema_recovery_target=previous
schema_aligned_to_verified_release=0
verified_release_web_smoke_passed=0
restore_runtime_allowed=1
restore_expected_sha=before
before_sha=before
verified_sha=verified
release_control_manager=manager
release_control_manifest=manifest
release_control_dir=""
release_bundle_dir=""
release_provenance_tmp=""
deploy_smoke_session_file=""
false
cleanup_deploy
"""
        completed = subprocess.run(
            ["bash", "-c", harness], cwd=tmp_path, check=False, capture_output=True, text=True
        )

        assert completed.returncode == 1, completed.stderr
        audit = audit_file.read_text(encoding="utf-8")
        assert "venv-python -m pip install --require-hashes -r requirements.lock" in audit
        assert "restore " not in audit
        if initially_stopped:
            assert "resecure" not in audit
        else:
            assert "resecure" in audit


def test_partial_restore_obeys_commit_policy_and_schema_gates(tmp_path: Path) -> None:
    workflow = _deploy_contract_source()
    start = workflow.index("            cleanup_deploy() {")
    end = workflow.index("            trap cleanup_deploy EXIT", start)
    cleanup_source = "\n".join(
        line.removeprefix("            ") for line in workflow[start:end].splitlines()
    )
    partial_index = cleanup_source.index('if [ "${runtime_transaction_partial:-0}" = "1" ]')
    partial_condition = cleanup_source[partial_index : cleanup_source.index("; then", partial_index)]

    assert '[ "${runtime_committed:-0}" != "1" ]' in partial_condition
    assert '[ "${restore_runtime_allowed:-1}" = "1" ]' in partial_condition
    assert '[ "${schema_recovery_target:-unknown}" = "previous" ]' in partial_condition

    scenarios = (
        ("verified", 0, 1),
        ("unknown", 0, 0),
        ("previous", 1, 1),
    )
    for recovery_target, runtime_committed, restore_allowed in scenarios:
        audit_file = tmp_path / f"partial-{recovery_target}-{runtime_committed}.log"
        harness = f"""
set -u
AUDIT_FILE={str(audit_file)!r}
TARGET={recovery_target!r}
python3() {{ printf 'python3 %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
sudo() {{ printf 'sudo %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
git() {{ printf 'git %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
rm() {{ return 0; }}
refresh_schema_recovery_target() {{
  schema_recovery_target="$TARGET"
  if [ "$TARGET" = "unknown" ]; then restore_runtime_allowed=0; fi
}}
restore_runtime_from_guard() {{ printf 'restore %s\n' "$*" >> "$AUDIT_FILE"; return 0; }}
resecure_runtime_guard() {{ printf 'resecure\n' >> "$AUDIT_FILE"; return 0; }}
print_runtime_release_diagnostics() {{ :; }}
verify_system_health_for_runtime_release() {{ return 1; }}
revoke_deploy_smoke_session() {{ return 0; }}
{cleanup_source}
runtime_mutation_started=0
runtime_committed={runtime_committed}
runtime_units_stopped=0
runtime_transaction_partial=1
release_switched=1
release_committed=0
schema_recovery_target="$TARGET"
schema_aligned_to_verified_release=1
verified_release_web_smoke_passed=1
restore_runtime_allowed={restore_allowed}
restore_expected_sha=verified
before_sha=before
verified_sha=verified
release_control_manager=manager
release_control_manifest=manifest
release_control_dir=""
release_bundle_dir=""
release_provenance_tmp=""
deploy_smoke_session_file=""
false
cleanup_deploy
"""
        completed = subprocess.run(
            ["bash", "-c", harness], cwd=tmp_path, check=False, capture_output=True, text=True
        )

        assert completed.returncode == 1, completed.stderr
        assert not audit_file.exists() or "restore " not in audit_file.read_text(encoding="utf-8")


def test_cleanup_runtime_restore_short_circuits_and_resecures_on_any_phase_failure() -> None:
    workflow = _deploy_contract_source()
    helper_start = workflow.index("restore_runtime_from_guard() {")
    helper_end = workflow.index("resecure_runtime_guard() {", helper_start)
    helper = workflow[helper_start:helper_end]
    cleanup = workflow[workflow.index("cleanup_deploy() {") : workflow.index("trap cleanup_deploy EXIT")]

    assert helper.count("&& python3") == 3
    assert helper.index("install-enable-after-web-health") < helper.index("verify-staged-runtime")
    assert helper.index("verify-staged-runtime") < helper.index("release-runtime-guard")
    assert "runtime restore failed; re-securing deploy guard" in cleanup
    assert "partial runtime restore failed; re-securing deploy guard" in cleanup
    assert cleanup.count("resecure_runtime_guard || true") == 2


def test_deploy_exit_trap_revokes_smoke_session_and_restores_runtime_units():
    workflow = _deploy_contract_source()

    cleanup_index = workflow.index("cleanup_deploy() {")
    stop_index = workflow.index("--phase ensure-stopped-for-rollback --execute", cleanup_index)
    restore_call_index = workflow.index("restore_runtime_from_guard authorize-runtime-start", stop_index)
    trap_index = workflow.index("trap cleanup_deploy EXIT", restore_call_index)
    restored_flag_index = workflow.index("runtime_units_stopped=0", trap_index)

    assert cleanup_index < stop_index < restore_call_index < trap_index < restored_flag_index
    cleanup = workflow[cleanup_index:trap_index]
    assert 'revoke_deploy_smoke_session "$deploy_smoke_session_file"' in cleanup
    assert "--phase stop-for-migration --execute" not in cleanup
    assert "--phase ensure-stopped-for-rollback --execute" in cleanup
    assert 'if [ "${runtime_units_stopped:-0}" = "1" ]; then' in cleanup
    assert 'echo "restoring runtime units for $restore_expected_sha"' in cleanup
    assert 'git reset --hard "$before_sha"' in cleanup
    assert 'grep -i "x-aicrm-release-sha: $restore_expected_sha"' in cleanup
    assert "verify_system_health_for_runtime_release" in cleanup
    assert "restored Web failed release-safe system health; runtime remains guarded" in cleanup
    assert "partially stopped runtime failed release-safe system health; runtime remains guarded" in cleanup
    assert "restore_runtime_from_guard authorize-runtime-start" in cleanup
    helper = workflow[workflow.index("restore_runtime_from_guard() {") : cleanup_index]
    assert "--phase install-enable-after-web-health --execute" in helper
    assert "--phase verify-staged-runtime --execute" in helper
    assert "--phase verify --execute" not in cleanup
    assert "restored_web_ready" in cleanup


def test_production_deploy_retires_legacy_external_push_worker():
    manifest = json.loads((ROOT / "deploy" / "production_runtime_units.json").read_text(encoding="utf-8"))
    active_timers = {item["timer"] for item in manifest["active_autostart"]}
    retired = set(manifest["retired_forbidden"])

    assert "openclaw-external-push-worker.timer" not in active_timers
    assert "openclaw-external-push-worker.timer" in retired
    assert "openclaw-external-push-worker.service" in retired


def test_production_deploy_installs_external_effect_queue_worker_timer_without_manual_execute():
    workflow = _deploy_contract_source()

    stop_runtime_units_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))

    assert stop_runtime_units_index < alembic_upgrade_index
    assert health_index < install_index < verify_index
    assert "sudo systemctl start openclaw-external-effect-worker.service" not in workflow


def test_production_deploy_installs_and_runs_broadcast_queue_worker_timer():
    workflow = _deploy_contract_source()

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    assert health_index < install_index < verify_index


def test_production_deploy_installs_and_runs_internal_event_worker_timer():
    workflow = _deploy_contract_source()

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    reconciliation_index = workflow.index("python scripts/ops/reconcile_internal_event_outbox.py")

    assert health_index < install_index < verify_index < reconciliation_index
    assert "python scripts/ops/reconcile_internal_event_outbox.py --repair" not in workflow


def test_production_deploy_runs_commerce_fulfillment_reconciliation_count_only():
    workflow = _deploy_contract_source()

    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    internal_event_index = workflow.index("python scripts/ops/reconcile_internal_event_outbox.py")
    commerce_index = workflow.index("python scripts/ops/reconcile_commerce_fulfillment.py")

    assert verify_index < internal_event_index < commerce_index
    assert "python scripts/ops/reconcile_commerce_fulfillment.py --repair" not in workflow


def test_production_deploy_runs_r09_and_r10_reconciliation_count_only():
    workflow = _deploy_contract_source()

    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))
    commerce_index = workflow.index("python scripts/ops/reconcile_commerce_fulfillment.py")
    questionnaire_index = workflow.index("python scripts/ops/reconcile_questionnaire_radar.py")
    group_ops_index = workflow.index("python scripts/ops/reconcile_group_ops_broadcast.py")

    assert verify_index < commerce_index < questionnaire_index < group_ops_index
    assert "python scripts/ops/reconcile_questionnaire_radar.py --repair" not in workflow
    assert "python scripts/ops/reconcile_group_ops_broadcast.py --repair" not in workflow
    assert "tee /tmp/aicrm-questionnaire-radar-reconciliation.json" in workflow
    assert "tee /tmp/aicrm-group-ops-broadcast-reconciliation.json" in workflow


def test_external_push_worker_systemd_units_are_not_deployable():
    assert not (ROOT / "deploy" / "openclaw-external-push-worker.service").exists()
    assert not (ROOT / "deploy" / "openclaw-external-push-worker.timer").exists()


def test_external_effect_queue_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-external-effect-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-external-effect-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_external_effect_queue_worker.py --execute" in service
    assert "OnCalendar=*-*-* *:*:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-external-effect-worker.service" in timer


def test_production_deploy_installs_payment_reconciliation_and_identity_workers():
    workflow = _deploy_contract_source()

    stop_runtime_units_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))

    assert stop_runtime_units_index < alembic_upgrade_index < install_index < verify_index


def test_payment_reconciliation_and_identity_worker_units_are_deployable():
    payment_service = (ROOT / "deploy" / "openclaw-wechat-pay-order-reconciliation-worker.service").read_text(encoding="utf-8")
    payment_timer = (ROOT / "deploy" / "openclaw-wechat-pay-order-reconciliation-worker.timer").read_text(encoding="utf-8")
    identity_service = (ROOT / "deploy" / "openclaw-identity-resolution-worker.service").read_text(encoding="utf-8")
    identity_timer = (ROOT / "deploy" / "openclaw-identity-resolution-worker.timer").read_text(encoding="utf-8")

    for service in (payment_service, identity_service):
        assert "After=network.target openclaw-wecom-postgres.service" in service
        assert "Requires=openclaw-wecom-postgres.service" in service
        assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
        assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
        assert "wecom_ability_service" not in service
        assert "legacy_flask_app" not in service
        assert "run-legacy" not in service

    assert "python scripts/run_wechat_pay_order_reconciliation_worker.py --execute" in payment_service
    assert "OnCalendar=*-*-* *:0/10:45" in payment_timer
    assert "Persistent=true" in payment_timer
    assert "Unit=openclaw-wechat-pay-order-reconciliation-worker.service" in payment_timer

    assert "python scripts/run_identity_resolution_backfill_worker.py --execute --limit 20" in identity_service
    assert "OnCalendar=*-*-* *:0/2:20" in identity_timer
    assert "Persistent=true" in identity_timer
    assert "Unit=openclaw-identity-resolution-worker.service" in identity_timer


def test_internal_event_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-internal-event-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-internal-event-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_ENABLED=1" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=1" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_QUESTIONNAIRE_ENABLED=1" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_AUTO_EXECUTE=1" in service
    assert "Environment=AICRM_INTERNAL_EVENT_RELAY_ROLE=owner" in service
    assert "Environment=AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE=50" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_WORKER_BATCH_SIZE=50" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE=50" in service
    assert "payment.succeeded:service_period_entitlement_consumer" in service
    assert "payment.succeeded:webhook_order_paid_consumer" in service
    assert "questionnaire.submitted:questionnaire_projection_consumer" in service
    assert "questionnaire.submitted:questionnaire_webhook_consumer" in service
    assert "questionnaire.submitted:questionnaire_tag_consumer" in service
    assert "questionnaire.submitted:automation_questionnaire_consumer" in service
    assert "questionnaire.submitted:customer_summary_consumer" in service
    for pair in (
        "payment.succeeded:customer_timeline_projection_consumer",
        "questionnaire.submitted:customer_timeline_projection_consumer",
        "channel_entry.entered:customer_timeline_projection_consumer",
        "radar.opened:customer_timeline_projection_consumer",
        "commerce.product_enrolled:customer_timeline_projection_consumer",
        "customer_read_model.refresh.requested:customer_read_model_refresh_intent_consumer",
    ):
        assert pair in service
    assert "external_effect.completed" in service
    assert "external_effect.completed:external_effect_identity_continuation_consumer" in service
    assert "external_effect.completed:external_effect_group_ops_continuation_consumer" in service
    assert "external_effect.completed:external_effect_welcome_media_continuation_consumer" in service
    assert "external_effect.completed:external_effect_broadcast_continuation_consumer" in service
    assert "external_effect.completed:external_effect_questionnaire_continuation_consumer" in service
    assert "external_effect.completed:external_effect_external_push_continuation_consumer" in service
    assert "external_effect.completed:external_effect_automation_continuation_consumer" in service
    # Kept only while held pre-0131 runs may require an audited manual release.
    assert "external_effect.completed:external_effect_completion_continuation_consumer" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "ExecStart=/usr/bin/env" in service
    assert "/home/ubuntu/venvs/openclaw/bin/python scripts/run_internal_event_worker.py --execute --limit 50" in service
    assert "/bin/bash -lc" not in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:*:40" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-internal-event-worker.service" in timer


def test_production_deploy_installs_callback_ingress_and_worker_isolated_runtime():
    workflow = _deploy_contract_source()

    stop_runtime_units_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    smoke_index = workflow.index("python scripts/ops/check_wecom_callback_deploy_smoke.py")
    smoke_evidence_index = workflow.index("tee /tmp/wecom-callback-deploy-smoke.json")
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))

    assert stop_runtime_units_index < alembic_upgrade_index
    assert health_index < install_index < smoke_index < smoke_evidence_index < verify_index
    assert "python scripts/ops/check_wecom_callback_deploy_smoke.py | tee /tmp/wecom-callback-deploy-smoke.json" in workflow
    assert "nginx-wecom-callback-ingress.conf.example /etc" not in workflow


def test_wecom_callback_ingress_systemd_unit_is_deployable():
    service = (ROOT / "deploy" / "openclaw-wecom-callback-ingress.service").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=WECOM_CALLBACK_INGRESS_HOST=127.0.0.1" in service
    assert "Environment=WECOM_CALLBACK_INGRESS_PORT=5002" in service
    assert "Environment=APP_PORT=5002" not in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_wecom_callback_ingress.py" in service
    assert "Restart=always" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service


def test_wecom_callback_inbox_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-wecom-callback-inbox-worker.service").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_EXECUTE=1" in service
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE=20" in service
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_MAX_EXECUTE_BATCH_SIZE=20" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "Type=simple" in service
    assert "python scripts/run_wecom_callback_inbox_worker.py --execute --loop" in service
    assert "AICRM_WECOM_CALLBACK_INBOX_WORKER_POLL_INTERVAL_SECONDS=0.25" in service
    assert "Restart=always" in service
    assert "WantedBy=multi-user.target" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert not (ROOT / "deploy" / "openclaw-wecom-callback-inbox-worker.timer").exists()


def test_aicrm_canonical_runtime_isolation_systemd_units_are_deployable():
    web = (ROOT / "deploy" / "openclaw-wecom-postgres.service").read_text(encoding="utf-8")
    ingress = (ROOT / "deploy" / "aicrm-wecom-ingress.service").read_text(encoding="utf-8")
    callback_worker = (ROOT / "deploy" / "aicrm-wecom-callback-worker.service").read_text(encoding="utf-8")
    internal_worker = (ROOT / "deploy" / "aicrm-internal-event-worker.service").read_text(encoding="utf-8")
    external_worker = (ROOT / "deploy" / "aicrm-external-effect-worker.service").read_text(encoding="utf-8")

    for service in (ingress, callback_worker, internal_worker, external_worker):
        assert "After=network.target openclaw-wecom-postgres.service" in service
        assert "Requires=openclaw-wecom-postgres.service" in service
        assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
        assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
        assert "wecom_ability_service" not in service
        assert "legacy_flask_app" not in service
        assert "run-legacy" not in service

    assert not (ROOT / "deploy" / "aicrm-web.service").exists()
    assert "After=network.target postgresql.service" in web
    assert "User=ubuntu" in web
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in web
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in web
    assert "python app.py run" in web
    assert "Environment=APP_PORT=5002" in ingress
    assert "python scripts/run_wecom_callback_ingress.py" in ingress
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE=20" in callback_worker
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_MAX_EXECUTE_BATCH_SIZE=20" in callback_worker
    assert "python scripts/run_wecom_callback_inbox_worker.py --execute --loop" in callback_worker
    assert "Restart=always" in callback_worker
    assert "python scripts/run_internal_event_worker.py --execute" in internal_worker
    assert "python scripts/run_external_effect_queue_worker.py --execute" in external_worker


def test_wechat_shop_order_sync_systemd_units_are_deployable():
    workflow = _deploy_contract_source()
    service = (ROOT / "deploy" / "aicrm-wechat-shop-order-sync.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "aicrm-wechat-shop-order-sync.timer").read_text(encoding="utf-8")

    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))

    assert install_index < verify_index
    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python -m scripts.run_wechat_shop_order_sync --mode incremental" in service
    assert "OnCalendar=*-*-* *:0/10:30" in timer
    assert "Persistent=true" in timer
    assert "Unit=aicrm-wechat-shop-order-sync.service" in timer


def test_broadcast_queue_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-broadcast-queue-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-broadcast-queue-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=AICRM_GROUP_OPS_MATERIAL_UPLOAD_MODE=real" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_broadcast_queue_worker.py" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:*:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-broadcast-queue-worker.service" in timer


def test_archive_sync_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "aicrm-archive-sync.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "aicrm-archive-sync.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=APP_HOST=127.0.0.1" in service
    assert "Environment=APP_PORT=5001" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python -m scripts.run_incremental_archive_sync" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:00/5:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=aicrm-archive-sync.service" in timer


def test_pg_only_ops_tools_do_not_expose_sqlite_entrypoints():
    assert not (ROOT / "scripts" / "backup_sqlite.sh").exists()
    retired_seed_demo = ROOT / "scripts" / ("seed_" + "automation_conversion_demo.py")
    assert not retired_seed_demo.exists()
    assert not (ROOT / ("wecom_ability" + "_service") / "http").exists()

    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(encoding="utf-8")
    alembic_env = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "DATABASE_PATH`` / ``DATABASE_URL" not in broadcast_worker
    assert "DATABASE_PATH" not in alembic_env
    assert "data.sqlite3" not in alembic_env
    assert "sqlite:///" not in alembic_env


def test_makefile_check_uses_existing_quality_gate_targets():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "check: lint typecheck build" in makefile
    assert "customer-pulse-quality" not in makefile
    assert "scripts/run_customer_pulse_quality_gates.py" not in makefile
    assert "tests/test_customer_pulse_inbox.py" not in makefile
    assert "tests/test_customer_pulse_quality_gates.py" not in makefile


def test_postgres_backup_restore_share_database_url_guard():
    helper = (ROOT / "scripts" / "_postgres_env.sh").read_text(encoding="utf-8")
    backup = (ROOT / "scripts" / "backup_postgres.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "restore_postgres.sh").read_text(encoding="utf-8")

    assert "require_database_url()" in helper
    assert 'echo "DATABASE_URL is required" >&2' in helper
    assert 'source "${SCRIPT_DIR}/_postgres_env.sh"' in backup
    assert 'source "${SCRIPT_DIR}/_postgres_env.sh"' in restore
    assert "require_database_url" in backup
    assert "require_database_url" in restore


def test_batch_scripts_share_int_env_reader():
    runtime = (ROOT / "scripts" / "script_runtime.py").read_text(encoding="utf-8")
    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(encoding="utf-8")

    assert "def read_int_env" in runtime
    assert 'read_int_env("BROADCAST_QUEUE_BATCH_SIZE", 50)' in broadcast_worker
    assert "int(os.environ.get" not in broadcast_worker


def test_due_runner_scripts_share_int_env_reader():
    external_push_worker = (ROOT / "scripts" / "run_external_push_worker.py").read_text(encoding="utf-8")
    internal_event_worker = (ROOT / "scripts" / "run_internal_event_worker.py").read_text(encoding="utf-8")
    ai_audience_scheduler = (ROOT / "scripts" / "run_ai_audience_scheduler.py").read_text(encoding="utf-8")
    ai_audience_scheduler_runtime = (ROOT / "aicrm_next" / "ai_audience_ops" / "scheduler.py").read_text(encoding="utf-8")

    assert not (ROOT / "scripts" / "run_automation_sop.py").exists()
    assert 'read_int_env("EXTERNAL_PUSH_WORKER_BATCH_SIZE", DEFAULT_BATCH_SIZE)' in external_push_worker
    assert "CommerceFulfillmentReconciliationService().diagnose()" in external_push_worker
    assert "run_due_external_push_events" not in external_push_worker
    assert "run_due_external_push_retries" not in external_push_worker
    assert 'read_int_env("AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE", DEFAULT_WORKER_BATCH_SIZE)' in internal_event_worker
    assert "build_internal_event_consumer_registry" in internal_event_worker
    assert 'read_int_env("AICRM_AI_AUDIENCE_SCHEDULER_BATCH_SIZE", 20)' in ai_audience_scheduler
    assert "--execute" in internal_event_worker
    assert 'relay_role="owner"' in internal_event_worker
    assert 'relay_role="consumer_only"' in ai_audience_scheduler_runtime
    assert "int(os.environ.get" not in external_push_worker
    assert "int(os.environ.get" not in internal_event_worker
    assert "int(os.environ.get" not in ai_audience_scheduler


def test_ai_audience_scheduler_runs_through_internal_event_queue_only():
    workflow = _deploy_contract_source()
    scheduler = (ROOT / "scripts" / "run_ai_audience_scheduler.py").read_text(encoding="utf-8")
    legacy_service = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.service").read_text(encoding="utf-8")
    legacy_timer = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.timer").read_text(encoding="utf-8")
    daily_service = (ROOT / "deploy" / "aicrm-ai-audience-daily-intent.service").read_text(encoding="utf-8")
    daily_timer = (ROOT / "deploy" / "aicrm-ai-audience-daily-intent.timer").read_text(encoding="utf-8")
    stop_runtime_units_index = _deploy_runtime_phase_index(workflow, "stop-for-migration")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify-staged-runtime"))

    assert stop_runtime_units_index < alembic_upgrade_index < install_index < verify_index
    assert "register_ai_audience_event_consumers()" in scheduler
    assert "assert_legacy_owner_allowed()" in scheduler
    assert "run_due_ai_audience_consumers" in scheduler
    assert "--run-consumers --execute" in legacy_service
    assert "AICRM_INTERNAL_EVENT_RELAY_ROLE=consumer_only" in legacy_service
    assert "*:0/3:00" in legacy_timer
    assert "check_ai_audience_refresh_owner.py --code-only" in daily_service
    assert "run_ai_audience_scheduler.py --daily-only" in daily_service
    assert "--run-consumers" not in daily_service
    assert "--execute" not in daily_service
    assert "AICRM_INTERNAL_EVENT_RELAY_ROLE" not in daily_service
    assert "ExternalEffectWorker" not in daily_service
    assert "run_external_effect_queue_worker.py" not in daily_service
    assert "OnCalendar=*-*-* 02:00:00 Asia/Shanghai" in daily_timer
    assert "*:0/3:00" not in daily_timer


def test_production_runtime_declares_exactly_one_internal_event_relay_owner():
    manifest = json.loads((ROOT / "deploy" / "production_runtime_units.json").read_text(encoding="utf-8"))
    declared = {
        item["service"]: item["internal_event_relay_role"]
        for item in manifest["active_autostart"]
        if item.get("internal_event_relay_role")
    }

    assert declared == {}

    cutover_pairs = {
        item["timer"]: item["service"]
        for item in manifest["cutover_managed_legacy"]["timers"]
    }
    assert cutover_pairs["openclaw-internal-event-worker.timer"] == "openclaw-internal-event-worker.service"

    owner_sources = [
        path.relative_to(ROOT).as_posix()
        for root in (ROOT / "aicrm_next", ROOT / "scripts")
        for path in root.rglob("*.py")
        if 'relay_role="owner"' in path.read_text(encoding="utf-8")
    ]
    assert owner_sources == ["scripts/run_internal_event_worker.py"]


def _calls_utcnow(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "utcnow":
            return True
        if isinstance(node.func, ast.Name) and node.func.id == "utcnow":
            return True
    return False


def test_runtime_code_does_not_use_deprecated_utcnow():
    offenders = sorted(path.relative_to(ROOT).as_posix() for path in RUNTIME_DIR.rglob("*.py") if "__pycache__" not in path.parts and _calls_utcnow(path))

    assert not offenders, f"Runtime code must use explicit timezone-aware UTC helpers instead of datetime.utcnow(). Offenders: {offenders}"


def test_alembic_0002_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0002_perf_indexes_and_trace.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "TIMESTAMPTZ" in migration


def test_alembic_0003_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0003_member_segment_columns.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "information_schema.columns" in migration
    assert "DROP COLUMN IF EXISTS" in migration


def test_alembic_0004_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0004_cloud_orchestrator.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "datetime('now'" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "workflow_id BIGINT NOT NULL" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP" in migration
    assert "next_node_id BIGINT" in migration
    assert "DROP COLUMN IF EXISTS" in migration


def test_alembic_0005_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0005_segments_and_campaigns.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "sql_dialect TEXT NOT NULL DEFAULT 'postgres'" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "ADD COLUMN IF NOT EXISTS segment_id BIGINT" in migration


def test_alembic_0006_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0006_miniprogram_library.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration


def test_alembic_0007_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0007_image_library.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "thumb_image_id BIGINT" in migration
    assert "TIMESTAMPTZ" in migration


def test_alembic_0008_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0008_broadcast_jobs.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "BOOLEAN NOT NULL DEFAULT FALSE" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "WHERE source_id <> ''" in migration


def test_alembic_0009_is_pg_only():
    migration = (ROOT / "migrations" / "versions" / "0009_image_library_semantic.py").read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "TEXT NOT NULL DEFAULT '[]'" not in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "USING GIN (tags)" in migration


def test_deploy_runs_runtime_environment_as_repository_module():
    workflow = _deploy_contract_source()

    assert "python3 -m scripts.ops.ensure_runtime_environment" in workflow
    assert "python3 scripts/ops/ensure_runtime_environment.py" not in workflow
    assert "RUNTIME_TARGET_ENVIRONMENT: production" in workflow
    assert 'runtime_target_environment="${RUNTIME_TARGET_ENVIRONMENT}"' in workflow
    assert '--target-environment "$runtime_target_environment"' in workflow
    assert '--target-environment "$deploy_target"' not in workflow
    persistence_index = workflow.index("python3 -m scripts.ops.ensure_runtime_environment")
    deprecated_key_source_index = workflow.index(
        "from scripts.ops.ensure_runtime_environment import DEPRECATED_RUNTIME_ENV_KEYS",
        persistence_index,
    )
    deprecated_key_unset_index = workflow.index(
        'unset "$deprecated_runtime_env_key"',
        deprecated_key_source_index,
    )
    environment_reload_index = workflow.index(
        "source /home/ubuntu/.openclaw-wecom-pg.env",
        deprecated_key_unset_index,
    )
    wecom_preflight_index = workflow.index(
        "WeCom execution config remains conflicting after deprecated environment cleanup",
        environment_reload_index,
    )
    runtime_mutation_index = workflow.index("runtime_mutation_started=1", wecom_preflight_index)
    runtime_start_index = workflow.index("sudo systemctl start openclaw-wecom-postgres.service", persistence_index)
    flag_index = workflow.index("runtime_environment_args+=(--allow-missing-wechat-shop-callback-token)")

    assert flag_index < persistence_index < deprecated_key_source_index
    assert deprecated_key_source_index < deprecated_key_unset_index < environment_reload_index
    assert environment_reload_index < wecom_preflight_index < runtime_mutation_index
    assert wecom_preflight_index < runtime_start_index
    assert '"${runtime_environment_args[@]}"' in workflow[persistence_index:runtime_start_index]


def test_id_validation_release_marker_is_a_canonical_ignored_runtime_file():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    workflow = _deploy_contract_source()

    assert "/.release-sha" in ignored
    assert "printf '%s\\n' \"$after_sha\" > .release-sha" in workflow
    assert 'test "$(tr -d \'\\r\\n\' < .release-sha)" = "$verified_sha"' in workflow
