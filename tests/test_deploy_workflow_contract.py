from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ("wecom_ability" + "_service")
RUNTIME_UNITS_HELPER = "python3 scripts/ops/manage_production_runtime_units.py"
TEST_DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
PRODUCTION_PROMOTION_WORKFLOW = ROOT / ".github" / "workflows" / "promote-production.yml"


def _runtime_units_phase(phase: str) -> str:
    return f"{RUNTIME_UNITS_HELPER} --phase {phase} --execute"


def test_deploy_workflows_serialize_without_cancelling_active_release() -> None:
    deploy = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    promotion = PRODUCTION_PROMOTION_WORKFLOW.read_text(encoding="utf-8")

    assert "group: aicrm-deploy-${{ inputs.target_environment || 'test' }}" in deploy
    assert "group: aicrm-production-promotion" in promotion
    assert "cancel-in-progress: false" in deploy
    assert "cancel-in-progress: false" in promotion


def test_remote_deploy_holds_target_specific_server_lock_before_sha_checks() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    target_index = workflow.index('deploy_target="${{ inputs.target_environment || \'test\' }}"', workflow.index("Deploy via SSH"))
    lock_file_index = workflow.index('deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"', target_index)
    lock_fd_index = workflow.index('exec 9>"$deploy_lock_file"', lock_file_index)
    flock_index = workflow.index("if ! flock -n 9; then", lock_fd_index)
    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"', flock_index)
    migration_index = workflow.index("python3 -m alembic upgrade head", before_sha_index)

    assert target_index < lock_file_index < lock_fd_index < flock_index < before_sha_index < migration_index
    assert 'echo "another $deploy_target deployment holds $deploy_lock_file"' in workflow


def test_failed_uncommitted_deploy_restores_previous_exact_sha_and_dependencies() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    switched_init = workflow.index("release_switched=0")
    committed_init = workflow.index("release_committed=0", switched_init)
    cleanup_index = workflow.index("cleanup_deploy()", committed_init)
    rollback_guard = workflow.index('[ "${release_switched:-0}" = "1" ]', cleanup_index)
    stop_index = workflow.index("--phase stop-for-migration --execute", rollback_guard)
    reset_index = workflow.index('git reset --hard "$before_sha"', stop_index)
    release_file_index = workflow.index("printf '%s\\n' \"$before_sha\" > .release-sha", reset_index)
    dependency_guard = workflow.index('git diff --quiet "$before_sha" "$verified_sha" -- requirements.lock', release_file_index)
    dependency_restore = workflow.index("--require-hashes -r requirements.lock", dependency_guard)
    exact_health = workflow.index('grep -i "x-aicrm-release-sha: $restore_expected_sha"', dependency_restore)
    restore_units = workflow.index("--phase install-enable-after-web-health --execute", exact_health)

    assert switched_init < committed_init < cleanup_index < rollback_guard
    assert rollback_guard < stop_index < reset_index < release_file_index
    assert release_file_index < dependency_guard < dependency_restore < exact_health < restore_units
    assert 'restore_expected_sha="$before_sha"' in workflow
    assert "alembic downgrade" not in workflow


def test_success_marks_release_committed_only_after_public_exact_sha_verification() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    switch_index = workflow.index("release_switched=1")
    local_exact_sha_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"', switch_index)
    production_exact_sha_index = workflow.index('--expected-sha "$after_sha"', local_exact_sha_index)
    test_exact_sha_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"', production_exact_sha_index)
    committed_index = workflow.index("release_committed=1", test_exact_sha_index)

    assert switch_index < local_exact_sha_index < production_exact_sha_index < test_exact_sha_index < committed_index


def test_deploy_requires_runtime_units_and_application_readiness_before_commit() -> None:
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    verify_units_index = workflow.index(_runtime_units_phase("verify"))
    readiness_index = workflow.index(
        "curl -sSf http://127.0.0.1:5001/api/system/health",
        verify_units_index,
    )
    restored_flag_index = workflow.index("runtime_units_stopped=0", readiness_index)
    committed_index = workflow.index("release_committed=1", restored_flag_index)

    assert verify_units_index < readiness_index < restored_flag_index < committed_index
    assert "tee /tmp/aicrm-runtime-readiness.json" in workflow


def test_production_deploy_loads_postgres_env_before_alembic_upgrade():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

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
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stash_index = workflow.index("git stash push --include-untracked")
    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"')
    verified_sha_index = workflow.index(
        'verified_sha="${{ inputs.release_sha || github.event.workflow_run.head_sha }}"', before_sha_index
    )
    fetch_index = workflow.index(
        'git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/aicrm-id-refactor/main"'
    )
    reset_index = workflow.index('git reset --hard "$verified_sha"')

    assert before_sha_index < verified_sha_index < stash_index < fetch_index < reset_index
    assert 'release_bundle="/tmp/aicrm-release-$verified_sha/aicrm-release.bundle"' in workflow
    assert "git@github.com" not in workflow
    assert "GIT_SSH_COMMAND" not in workflow


def test_production_deploy_installs_dependencies_only_when_hashed_lock_changes():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    fetch_index = workflow.index(
        'git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/aicrm-id-refactor/main"'
    )
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    requirements_guard_index = workflow.index('git diff --quiet "$before_sha" "$after_sha" -- requirements.lock')
    pip_install_index = workflow.index("python -m pip install --require-hashes -r requirements.lock")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")

    assert fetch_index < reset_index < after_sha_index < requirements_guard_index < pip_install_index < alembic_upgrade_index
    assert "requirements.lock unchanged; skipping pip install" in workflow


def test_production_deploy_fails_closed_unless_checkout_matches_verified_workflow_sha():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    remote_deploy_index = workflow.index("uses: appleboy/ssh-action@v1.2.0")
    verified_sha_index = workflow.index(
        'verified_sha="${{ inputs.release_sha || github.event.workflow_run.head_sha }}"', remote_deploy_index
    )
    release_head_index = workflow.index('release_head_sha="$(git rev-parse refs/remotes/aicrm-id-refactor/main)"')
    head_guard_index = workflow.index('if [ "$release_head_sha" != "$verified_sha" ]; then')
    reset_index = workflow.index('git reset --hard "$verified_sha"')
    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    checkout_guard_index = workflow.index('if [ "$after_sha" != "$verified_sha" ]; then')
    stop_index = workflow.index(_runtime_units_phase("stop-for-migration"))

    assert verified_sha_index < release_head_index < head_guard_index < reset_index < after_sha_index < checkout_guard_index < stop_index
    assert "invalid verified workflow sha" in workflow
    assert "verified workflow sha is no longer the ID-refactor main head" in workflow
    assert "deployed checkout does not match verified workflow sha" in workflow


def test_production_deploy_verifies_local_bundle_before_fetch_and_stopping_services():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    bundle_index = workflow.index('release_bundle="/tmp/aicrm-release-$verified_sha/aicrm-release.bundle"')
    checksum_index = workflow.index("sha256sum -c aicrm-release.bundle.sha256")
    verify_index = workflow.index('git bundle verify "$release_bundle"')
    head_guard_index = workflow.index('git bundle list-heads "$release_bundle"')
    fetch_index = workflow.index(
        'git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/aicrm-id-refactor/main"'
    )
    stop_index = workflow.index(_runtime_units_phase("stop-for-migration"))

    assert bundle_index < checksum_index < verify_index < head_guard_index < fetch_index < stop_index
    assert "release bundle does not advertise the verified workflow sha" in workflow
    assert "git@github.com" not in workflow
    assert "GIT_SSH_COMMAND" not in workflow


def test_production_deploy_builds_and_transfers_incremental_exact_sha_bundle_before_remote_deploy():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    checkout_index = workflow.index("uses: actions/checkout@v4")
    discover_index = workflow.index('public_health_url="https://id-dev.youcangogogo.com/health"')
    build_index = workflow.index(
        'git bundle create release/aicrm-release.bundle refs/deploy/release ^refs/deploy/base'
    )
    transfer_index = workflow.index("uses: appleboy/scp-action@ff85246acaad7bdce478db94a363cd2bf7c90345")
    remote_deploy_index = workflow.index("uses: appleboy/ssh-action@v1.2.0")

    assert checkout_index < discover_index < build_index < transfer_index < remote_deploy_index
    assert "permissions:\n  contents: read" in workflow
    assert "ref: ${{ inputs.release_sha || github.event.workflow_run.head_sha }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert 'verified_sha="${{ inputs.release_sha || github.event.workflow_run.head_sha }}"' in workflow
    assert 'git fetch --no-tags origin main' in workflow
    assert 'if [ "$(git rev-parse FETCH_HEAD)" != "$verified_sha" ]; then' in workflow
    assert 'public_health_url="https://www.youcangogogo.com/health"' in workflow
    assert 'base_sha="$(awk \'tolower($1) == "x-aicrm-release-sha:" {print $2}\'' in workflow
    assert 'git merge-base --is-ancestor "$base_sha" "$verified_sha"' in workflow
    assert 'git update-ref refs/deploy/release "$verified_sha"' in workflow
    assert 'git update-ref refs/deploy/base "$base_sha"' in workflow
    assert 'echo "base_sha=$base_sha" >> "$GITHUB_OUTPUT"' in workflow
    assert "sha256sum aicrm-release.bundle" in workflow
    assert "git bundle verify release/aicrm-release.bundle" in workflow
    assert "git bundle create release/aicrm-release.bundle HEAD" not in workflow
    assert "target: /tmp/aicrm-release-${{ inputs.release_sha || github.event.workflow_run.head_sha }}" in workflow
    assert "strip_components: 1" in workflow
    assert "overwrite: true" in workflow


def test_production_deploy_requires_remote_head_to_match_bundle_prerequisite_before_fetch():
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"')
    base_sha_index = workflow.index('base_sha="${{ steps.release.outputs.base_sha }}"')
    base_guard_index = workflow.index('if [ "$before_sha" != "$base_sha" ]; then')
    bundle_verify_index = workflow.index('git bundle verify "$release_bundle"')
    stash_index = workflow.index("git stash push --include-untracked")
    fetch_index = workflow.index(
        'git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/aicrm-id-refactor/main"'
    )
    stop_index = workflow.index(_runtime_units_phase("stop-for-migration"))

    assert before_sha_index < base_sha_index < base_guard_index < bundle_verify_index < stash_index < fetch_index < stop_index
    assert "target checkout moved after the incremental release bundle was built" in workflow


def test_production_deploy_refreshes_release_marker_before_restart_and_checks_health_header():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    marker_index = workflow.index('printf \'%s\\n\' "$after_sha" > .release-sha')
    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    header_curl_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health")
    header_grep_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt')
    ready_guard_index = workflow.index('if [ "$release_ready" != "1" ]; then')

    assert after_sha_index < marker_index < start_index < header_curl_index < header_grep_index < ready_guard_index


def test_production_deploy_runs_alembic_upgrade_before_service_restart():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    pip_install_index = workflow.index("python -m pip install --require-hashes -r requirements.lock")
    stop_runtime_units_index = workflow.index(_runtime_units_phase("stop-for-migration"))
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    stop_canonical_web_index = workflow.index("sudo systemctl stop aicrm-web.service || true", alembic_upgrade_index)
    stop_compatible_web_index = workflow.index(
        "sudo systemctl stop openclaw-wecom-postgres.service || true", stop_canonical_web_index
    )
    stale_listener_index = workflow.index('if sudo fuser -s 5001/tcp; then')
    term_kill_index = workflow.index("sudo fuser -k -TERM 5001/tcp || true")
    force_kill_index = workflow.index("sudo fuser -k -KILL 5001/tcp || true")
    wait_for_free_index = workflow.index('echo "waiting for stale 5001 listener to exit"')
    reset_failed_index = workflow.index("sudo systemctl reset-failed openclaw-wecom-postgres.service || true")
    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    alembic_table = "alembic_" + "version"

    assert env_source_index < database_url_guard_index < alembic_upgrade_index
    assert (
        pip_install_index
        < stop_runtime_units_index
        < alembic_upgrade_index
        < stop_canonical_web_index
        < stop_compatible_web_index
        < stale_listener_index
        < term_kill_index
        < force_kill_index
        < wait_for_free_index
        < reset_failed_index
        < start_index
    )
    assert "sudo fuser -TERM 5001/tcp" not in workflow
    assert "sudo fuser -KILL 5001/tcp" not in workflow
    assert "python3 app.py init-db" not in workflow
    assert "python app.py init-db" not in workflow
    assert "alembic stamp head" not in workflow
    assert f"ALTER TABLE IF EXISTS {alembic_table}" not in workflow
    assert f"ALTER TABLE {alembic_table}" not in workflow


def test_production_deploy_migrates_and_reconciles_secret_references_before_web_restart():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    migration_index = workflow.index("python3 scripts/ops/migrate_app_setting_secrets.py --execute")
    auth_bootstrap_index = workflow.index("python3 scripts/ops/bootstrap_auth_clients.py", migration_index)
    refreshed_env_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env", migration_index)
    auth_readiness_index = workflow.index("python3 scripts/ops/check_auth_readiness.py", refreshed_env_index)
    reconciliation_index = workflow.index("python3 scripts/ops/check_secret_reference_cutover.py")
    stop_web_index = workflow.index("sudo systemctl stop aicrm-web.service || true", alembic_upgrade_index)
    start_web_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")

    assert (
        alembic_upgrade_index
        < stop_web_index
        < migration_index
        < auth_bootstrap_index
        < refreshed_env_index
        < auth_readiness_index
        < reconciliation_index
        < start_web_index
    )
    assert "--secret-store-dir \"$AICRM_SECRET_STORE_DIR\"" in workflow
    assert "--environment-file /home/ubuntu/.openclaw-wecom-pg.env" in workflow
    assert "tee /tmp/aicrm-secret-migration.json" in workflow
    assert "--apply" in workflow[auth_bootstrap_index:refreshed_env_index]
    assert '--issuer "$auth_issuer"' in workflow[auth_bootstrap_index:reconciliation_index]
    assert 'auth_issuer="https://www.youcangogogo.com"' in workflow
    assert 'auth_issuer="https://id-dev.youcangogogo.com"' in workflow
    assert "tee /tmp/aicrm-auth-client-bootstrap.json" in workflow
    assert "tee /tmp/aicrm-auth-readiness.json" in workflow
    assert "tee /tmp/aicrm-secret-reconciliation.json" in workflow
    assert "set -x" not in workflow


def test_production_deploy_repairs_only_approved_legacy_nginx_web_route_and_requires_public_exact_sha():
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    local_health_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha"')
    runtime_verify_index = workflow.index(_runtime_units_phase("verify"))
    public_route_index = workflow.index("scripts/ops/ensure_production_public_release_route.py --execute")
    public_sha_index = workflow.index('--expected-sha "$after_sha"', public_route_index)

    assert local_health_index < runtime_verify_index < public_route_index < public_sha_index
    assert "--server-name www.youcangogogo.com" in workflow
    assert "--public-health-url https://www.youcangogogo.com/health" in workflow
    assert "--nginx-config /etc/nginx/sites-enabled/youcangogogo.conf" in workflow
    assert "tee /tmp/aicrm-public-release-route.json" in workflow


def test_automatic_test_deploy_uses_test_secrets_and_read_only_test_public_health_check():
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    runtime_verify_index = workflow.index(_runtime_units_phase("verify"))
    public_health_index = workflow.index("https://id-dev.youcangogogo.com/health", runtime_verify_index)

    assert runtime_verify_index < public_health_index
    assert "secrets.TEST_DEPLOY_HOST" in workflow
    assert "secrets.TEST_DEPLOY_USER" in workflow
    assert "secrets.TEST_DEPLOY_SSH_KEY" in workflow
    assert "inputs.target_environment == 'production' && secrets.DEPLOY_HOST || secrets.TEST_DEPLOY_HOST" in workflow
    assert 'if [ "$deploy_target" = "production" ]; then' in workflow
    assert workflow.index('if [ "$deploy_target" = "production" ]; then') < workflow.index(
        "ensure_production_public_release_route.py"
    )
    assert 'grep -i "x-aicrm-release-sha: $after_sha"' in workflow


def test_production_deploy_polls_health_after_restart_instead_of_fixed_sleep():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    poll_index = workflow.index("for _ in $(seq 1 60); do", start_index)
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", poll_index)
    header_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt', health_index)
    ready_guard_index = workflow.index('if [ "$release_ready" != "1" ]; then', header_index)
    status_index = workflow.index("sudo systemctl status openclaw-wecom-postgres.service --no-pager || true", ready_guard_index)

    assert start_index < poll_index < health_index < header_index < status_index
    assert "sleep 3" not in workflow


def test_deploy_admin_smoke_uses_short_lived_server_session_without_logging_cookie():
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    issue_index = workflow.index("python3 scripts/ops/create_deploy_smoke_session.py issue")
    smoke_index = workflow.index("python scripts/ops/check_admin_read_pages_smoke.py", issue_index)
    revoke_index = workflow.index("python3 scripts/ops/create_deploy_smoke_session.py revoke", smoke_index)
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))

    assert issue_index < smoke_index < revoke_index < install_index
    assert 'deploy_smoke_session_file="$(mktemp /tmp/aicrm-deploy-smoke-session.XXXXXX)"' in workflow
    assert '--output-file "$deploy_smoke_session_file"' in workflow
    assert "--ttl-seconds 300" in workflow
    assert '--admin-cookie-file "$deploy_smoke_session_file"' in workflow
    assert '--cookie-file "$deploy_smoke_session_file"' in workflow
    assert "aicrm_next_admin_session=" not in workflow
    assert 'cat "$deploy_smoke_session_file"' not in workflow
    assert 'echo "$deploy_smoke_session_file"' not in workflow


def test_deploy_exit_trap_revokes_smoke_session_and_restores_runtime_units():
    workflow = TEST_DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    cleanup_index = workflow.index("cleanup_deploy() {")
    trap_index = workflow.index("trap cleanup_deploy EXIT", cleanup_index)
    stop_index = workflow.index(_runtime_units_phase("stop-for-migration"))
    stopped_flag_index = workflow.index("runtime_units_stopped=1", stop_index)
    verify_index = workflow.index(_runtime_units_phase("verify"), stopped_flag_index)
    restored_flag_index = workflow.index("runtime_units_stopped=0", verify_index)

    assert cleanup_index < trap_index < stop_index < stopped_flag_index < verify_index < restored_flag_index
    cleanup = workflow[cleanup_index:trap_index]
    assert "create_deploy_smoke_session.py revoke" in cleanup
    assert 'if [ "${runtime_units_stopped:-0}" = "1" ]; then' in cleanup
    assert 'echo "restoring runtime units for $restore_expected_sha"' in cleanup
    assert 'git reset --hard "$before_sha"' in cleanup
    assert 'grep -i "x-aicrm-release-sha: $restore_expected_sha"' in cleanup
    assert "--phase install-enable-after-web-health --execute" in cleanup
    assert "--phase verify --execute" in cleanup
    assert "restored_web_ready" in cleanup


def test_production_deploy_retires_legacy_external_push_worker():
    manifest = json.loads((ROOT / "deploy" / "production_runtime_units.json").read_text(encoding="utf-8"))
    active_timers = {item["timer"] for item in manifest["active_autostart"]}
    retired = set(manifest["retired_forbidden"])

    assert "openclaw-external-push-worker.timer" not in active_timers
    assert "openclaw-external-push-worker.timer" in retired
    assert "openclaw-external-push-worker.service" in retired


def test_production_deploy_installs_external_effect_queue_worker_timer_without_manual_execute():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stop_runtime_units_index = workflow.index(_runtime_units_phase("stop-for-migration"))
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify"))

    assert stop_runtime_units_index < alembic_upgrade_index
    assert health_index < install_index < verify_index
    assert "sudo systemctl start openclaw-external-effect-worker.service" not in workflow


def test_production_deploy_installs_and_runs_broadcast_queue_worker_timer():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify"))
    assert health_index < install_index < verify_index


def test_production_deploy_installs_and_runs_internal_event_worker_timer():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify"))
    reconciliation_index = workflow.index("python scripts/ops/reconcile_internal_event_outbox.py")

    assert health_index < install_index < verify_index < reconciliation_index
    assert "python scripts/ops/reconcile_internal_event_outbox.py --repair" not in workflow


def test_production_deploy_runs_commerce_fulfillment_reconciliation_count_only():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    verify_index = workflow.index(_runtime_units_phase("verify"))
    internal_event_index = workflow.index("python scripts/ops/reconcile_internal_event_outbox.py")
    commerce_index = workflow.index("python scripts/ops/reconcile_commerce_fulfillment.py")

    assert verify_index < internal_event_index < commerce_index
    assert "python scripts/ops/reconcile_commerce_fulfillment.py --repair" not in workflow


def test_production_deploy_runs_r09_and_r10_reconciliation_count_only():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    verify_index = workflow.index(_runtime_units_phase("verify"))
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
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stop_runtime_units_index = workflow.index(_runtime_units_phase("stop-for-migration"))
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify"))

    assert stop_runtime_units_index < alembic_upgrade_index < install_index < verify_index


def test_payment_reconciliation_and_identity_worker_units_are_deployable():
    payment_service = (ROOT / "deploy" / "openclaw-wechat-pay-order-reconciliation-worker.service").read_text(
        encoding="utf-8"
    )
    payment_timer = (ROOT / "deploy" / "openclaw-wechat-pay-order-reconciliation-worker.timer").read_text(
        encoding="utf-8"
    )
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

    assert "python scripts/run_identity_resolution_backfill_worker.py --execute" in identity_service
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
    assert "Environment=AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_AUTO_EXECUTE=1" in service
    assert "Environment=AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE=50" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_WORKER_BATCH_SIZE=50" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE=50" in service
    assert "payment.succeeded:service_period_entitlement_consumer" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_internal_event_worker.py --execute --limit ${AICRM_INTERNAL_EVENTS_WORKER_BATCH_SIZE:-50}" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:*:40" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-internal-event-worker.service" in timer


def test_production_deploy_installs_callback_ingress_and_worker_isolated_runtime():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stop_runtime_units_index = workflow.index(_runtime_units_phase("stop-for-migration"))
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    smoke_index = workflow.index("python scripts/ops/check_wecom_callback_deploy_smoke.py")
    smoke_evidence_index = workflow.index("tee /tmp/wecom-callback-deploy-smoke.json")
    verify_index = workflow.index(_runtime_units_phase("verify"))

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
    web = (ROOT / "deploy" / "aicrm-web.service").read_text(encoding="utf-8")
    ingress = (ROOT / "deploy" / "aicrm-wecom-ingress.service").read_text(encoding="utf-8")
    callback_worker = (ROOT / "deploy" / "aicrm-wecom-callback-worker.service").read_text(encoding="utf-8")
    internal_worker = (ROOT / "deploy" / "aicrm-internal-event-worker.service").read_text(encoding="utf-8")
    external_worker = (ROOT / "deploy" / "aicrm-external-effect-worker.service").read_text(encoding="utf-8")

    for service in (web, ingress, callback_worker, internal_worker, external_worker):
        assert "After=network.target openclaw-wecom-postgres.service" in service
        assert "Requires=openclaw-wecom-postgres.service" in service
        assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
        assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
        assert "wecom_ability_service" not in service
        assert "legacy_flask_app" not in service
        assert "run-legacy" not in service

    assert "Environment=APP_PORT=5001" in web
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
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "aicrm-wechat-shop-order-sync.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "aicrm-wechat-shop-order-sync.timer").read_text(encoding="utf-8")

    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify"))

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
    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(
        encoding="utf-8"
    )

    assert "def read_int_env" in runtime
    assert 'read_int_env("BROADCAST_QUEUE_BATCH_SIZE", 50)' in broadcast_worker
    assert "int(os.environ.get" not in broadcast_worker


def test_due_runner_scripts_share_int_env_reader():
    external_push_worker = (ROOT / "scripts" / "run_external_push_worker.py").read_text(encoding="utf-8")
    internal_event_worker = (ROOT / "scripts" / "run_internal_event_worker.py").read_text(encoding="utf-8")
    ai_audience_scheduler = (ROOT / "scripts" / "run_ai_audience_scheduler.py").read_text(encoding="utf-8")

    assert not (ROOT / "scripts" / "run_automation_sop.py").exists()
    assert 'read_int_env("EXTERNAL_PUSH_WORKER_BATCH_SIZE", DEFAULT_BATCH_SIZE)' in external_push_worker
    assert "CommerceFulfillmentReconciliationService().diagnose()" in external_push_worker
    assert "run_due_external_push_events" not in external_push_worker
    assert "run_due_external_push_retries" not in external_push_worker
    assert 'read_int_env("AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE", DEFAULT_WORKER_BATCH_SIZE)' in internal_event_worker
    assert "register_payment_succeeded_consumers()" in internal_event_worker
    assert "register_shadow_event_consumers()" in internal_event_worker
    assert "register_ai_audience_event_consumers()" in internal_event_worker
    assert 'read_int_env("AICRM_AI_AUDIENCE_SCHEDULER_BATCH_SIZE", 20)' in ai_audience_scheduler
    assert "--execute" in internal_event_worker
    assert "InternalEventWorker().run_due" in internal_event_worker
    assert "int(os.environ.get" not in external_push_worker
    assert "int(os.environ.get" not in internal_event_worker
    assert "int(os.environ.get" not in ai_audience_scheduler


def test_ai_audience_scheduler_runs_through_internal_event_queue_only():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    scheduler = (ROOT / "scripts" / "run_ai_audience_scheduler.py").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.timer").read_text(encoding="utf-8")
    stop_runtime_units_index = workflow.index(_runtime_units_phase("stop-for-migration"))
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    install_index = workflow.index(_runtime_units_phase("install-enable-after-web-health"))
    verify_index = workflow.index(_runtime_units_phase("verify"))

    assert stop_runtime_units_index < alembic_upgrade_index < install_index < verify_index
    assert "register_ai_audience_event_consumers()" in scheduler
    assert 'read_int_env("AICRM_AI_AUDIENCE_SCHEDULER_BATCH_SIZE", 20)' in scheduler
    assert "run_due_ai_audience_consumers" in scheduler
    assert "--run-consumers --execute" in service
    assert "ExecStart=/bin/bash -c" in service
    assert "AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=" in service
    assert "ai_audience.refresh.incremental_tick,ai_audience.refresh.daily_tick" in service
    assert "AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=" in service
    assert "ai_audience.refresh.incremental_tick:ai_audience_incremental_refresh_consumer" in service
    assert "ai_audience.refresh.daily_tick:ai_audience_daily_refresh_consumer" in service
    assert "ai_audience.run.refreshed:ai_audience_outbound_effect_planner" in service
    assert "ai_audience.member.updated:ai_audience_outbound_effect_planner" not in service
    assert "ai_audience.member.exited:ai_audience_outbound_effect_planner" not in service
    assert "ExternalEffectWorker" not in service
    assert "run_external_effect_queue_worker.py" not in service
    assert "OnCalendar=*-*-* *:0/3:00" in timer


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
    offenders = sorted(
        path.relative_to(ROOT).as_posix()
        for path in RUNTIME_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and _calls_utcnow(path)
    )

    assert not offenders, (
        "Runtime code must use explicit timezone-aware UTC helpers instead of datetime.utcnow(). "
        f"Offenders: {offenders}"
    )


def test_alembic_0002_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0002_perf_indexes_and_trace.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "TIMESTAMPTZ" in migration


def test_alembic_0003_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0003_member_segment_columns.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "information_schema.columns" in migration
    assert "DROP COLUMN IF EXISTS" in migration


def test_alembic_0004_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0004_cloud_orchestrator.py"
    ).read_text(encoding="utf-8")

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
    migration = (
        ROOT / "migrations" / "versions" / "0005_segments_and_campaigns.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "sql_dialect TEXT NOT NULL DEFAULT 'postgres'" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "ADD COLUMN IF NOT EXISTS segment_id BIGINT" in migration


def test_alembic_0006_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0006_miniprogram_library.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration


def test_alembic_0007_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0007_image_library.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "thumb_image_id BIGINT" in migration
    assert "TIMESTAMPTZ" in migration


def test_alembic_0008_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0008_broadcast_jobs.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "BOOLEAN NOT NULL DEFAULT FALSE" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "WHERE source_id <> ''" in migration


def test_alembic_0009_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0009_image_library_semantic.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "TEXT NOT NULL DEFAULT '[]'" not in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "USING GIN (tags)" in migration
