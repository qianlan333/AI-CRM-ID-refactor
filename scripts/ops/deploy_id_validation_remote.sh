#!/usr/bin/env bash
set -e
set -o pipefail
runtime_mutation_started=0
runtime_committed=0
release_control_dir=""
release_control_manager=""
release_control_manifest=""
release_provenance_tmp=""
release_provenance_directory="/home/ubuntu/.aicrm-releases"
release_provenance_prepared="/home/ubuntu/.aicrm-releases/id-validation.prepared.json"
release_provenance_prepared_owned=0
release_provenance_pending="/home/ubuntu/.aicrm-releases/id-validation.pending.json"
release_provenance_pending_owned=0
cd '/home/ubuntu/极简 crm'
readonly deploy_target="${DEPLOY_TARGET}"
readonly runtime_target_environment="${RUNTIME_TARGET_ENVIRONMENT}"
readonly public_base_url="${PUBLIC_BASE_URL}"
readonly public_health_url="${PUBLIC_HEALTH_URL}"
readonly allow_missing_wechat_shop_callback_token="${ALLOW_MISSING_WECHAT_SHOP_CALLBACK_TOKEN}"
readonly expected_repository="${EXPECTED_REPOSITORY}"
readonly release_repository="${RELEASE_REPOSITORY}"
readonly release_run_id="${RELEASE_RUN_ID}"
readonly release_run_attempt="${RELEASE_RUN_ATTEMPT}"
readonly source_ci_run_id="${SOURCE_CI_RUN_ID}"
readonly bundle_sha256="${BUNDLE_SHA256}"
if [ "$release_repository" != "$expected_repository" ]; then
  echo "release repository does not match the immutable ID validation repository"
  exit 1
fi
if [ "$deploy_target" != "id-validation" ]; then
  echo "deployment target does not match the immutable ID validation environment"
  exit 1
fi
if [ "$runtime_target_environment" != "production" ]; then
  echo "runtime target does not match the production data environment"
  exit 1
fi
if [ "$public_health_url" != "https://id-dev.youcangogogo.com/health" ]; then
  echo "public health URL does not match the immutable ID validation target"
  exit 1
fi
if [ "$public_base_url" != "https://id-dev.youcangogogo.com" ]; then
  echo "public base URL does not match the immutable ID validation target"
  exit 1
fi
if [ "$allow_missing_wechat_shop_callback_token" != "0" ]; then
  echo "missing WeChat Shop callback token must remain fail-closed"
  exit 1
fi
remote_origin_url="$(git remote get-url origin)"
case "$remote_origin_url" in
  "https://github.com/${expected_repository}"|\
  "https://github.com/${expected_repository}.git"|\
  "git@github.com:${expected_repository}"|\
  "git@github.com:${expected_repository}.git")
    ;;
  *)
    echo "target checkout origin is not the ID validation repository"
    exit 1
    ;;
esac
deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"
exec 9>"$deploy_lock_file"
if ! flock -n 9; then
  echo "another $deploy_target deployment holds $deploy_lock_file"
  exit 1
fi
cd '/home/ubuntu/极简 crm'
before_sha="$(git rev-parse HEAD)"
readonly verified_sha="${VERIFIED_SHA}"
readonly base_sha="${BASE_SHA}"
readonly base_source="${BASE_SOURCE}"
if ! printf '%s' "$verified_sha" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "invalid verified workflow sha"
  exit 1
fi
if ! printf '%s' "$bundle_sha256" | grep -Eq '^[0-9a-f]{64}$'; then
  echo "invalid release bundle provenance checksum"
  exit 1
fi
case "$base_source" in
  public_health|guarded_server_checkout)
    ;;
  *)
    echo "invalid release base source"
    exit 1
    ;;
esac
if [ "$before_sha" != "$base_sha" ]; then
  echo "target checkout moved after the incremental release bundle was built"
  exit 1
fi
if [ "$base_source" = "guarded_server_checkout" ]; then
  # The first attestation lock is released while the runner builds and copies
  # the bundle. Re-establish its non-HEAD invariants under the final deployment
  # lock before any bundle, checkout, or runtime mutation.
  remote_origin_url="$(git remote get-url origin)"
  case "$remote_origin_url" in
    "https://github.com/${expected_repository}"|\
    "https://github.com/${expected_repository}.git"|\
    "git@github.com:${expected_repository}"|\
    "git@github.com:${expected_repository}.git")
      ;;
    *)
      echo "guarded release base origin changed after attestation"
      exit 1
      ;;
  esac
  if [ -L .release-sha ] || [ ! -f .release-sha ]; then
    echo "guarded release marker is missing or is a symlink"
    exit 1
  fi
  release_marker_sha="$(python3 - <<'PY'
import re
from pathlib import Path

raw = Path(".release-sha").read_bytes()
if raw.endswith(b"\r\n"):
    raw = raw[:-2]
elif raw.endswith(b"\n"):
    raw = raw[:-1]
if re.fullmatch(rb"[0-9a-f]{40}", raw) is None:
    raise SystemExit("guarded release marker is not exactly one SHA")
print(raw.decode("ascii"))
PY
)"
  if [ "$release_marker_sha" != "$base_sha" ]; then
    echo "guarded release marker changed after attestation"
    exit 1
  fi
  if [ -n "$(git status --porcelain=v1 --untracked-files=all)" ]; then
    echo "guarded release checkout became dirty after attestation"
    git status --short --untracked-files=all
    exit 1
  fi
fi
release_bundle_dir="/tmp/aicrm-release-$verified_sha"
release_bundle="/tmp/aicrm-release-$verified_sha/aicrm-release.bundle"
release_bundle_checksum="/tmp/aicrm-release-$verified_sha/aicrm-release.bundle.sha256"
deploy_smoke_session_file=""
runtime_units_stopped=0
runtime_transaction_partial=0
release_switched=0
release_committed=0
previous_expected_migration_heads_json=""
schema_recovery_target="unknown"
schema_aligned_to_verified_release=0
verified_release_web_smoke_passed=0
restore_runtime_allowed=1
restore_expected_sha="$before_sha"
revoke_deploy_smoke_session() {
  local cookie_file="$1"
  local report_file
  if ! report_file="$(mktemp /tmp/aicrm-deploy-smoke-session-revoke.XXXXXX)"; then
    return 1
  fi
  if ! python3 scripts/ops/create_deploy_smoke_session.py revoke \
    --cookie-file "$cookie_file" \
    > "$report_file"; then
    cat "$report_file" || true
    rm -f -- "$report_file"
    return 1
  fi
  cat "$report_file"
  rm -f -- "$report_file"
}
verify_system_health_for_runtime_release() {
  local expected_sha="$1"
  local report_file="$2"
  local headers_file="${report_file%.json}.headers"
  for _ in $(seq 1 10); do
    if curl -sSf -D "$headers_file" \
      http://127.0.0.1:5001/api/system/health \
      -o "$report_file" \
      && EXPECTED_RELEASE_SHA="$expected_sha" REPORT_FILE="$report_file" \
        python3 -c 'import json, os, sys; payload=json.load(open(os.environ["REPORT_FILE"], encoding="utf-8")); release=payload.get("components", {}).get("release", {}); migration=payload.get("components", {}).get("migration", {}); migration_ready=bool(migration.get("matches_head") or migration.get("forward_compatible")); ready=payload.get("ok") is True and int(payload.get("http_status") or 0) == 200 and release.get("release_sha") == os.environ["EXPECTED_RELEASE_SHA"] and release.get("exact_sha") is True and migration_ready; sys.exit(0 if ready else "runtime system health is not release-safe")'; then
      cat "$report_file"
      return 0
    fi
    sleep 1
  done
  cat "$report_file" 2>/dev/null || true
  return 1
}
print_runtime_release_diagnostics() {
  for marker in \
    /home/ubuntu/.aicrm-production-deploy-in-progress \
    /run/aicrm-production-web-start-authorized \
    /run/aicrm-production-runtime-start-authorized; do
    if sudo test -e "$marker"; then
      echo "runtime_marker=$marker state=present"
    else
      echo "runtime_marker=$marker state=absent"
    fi
  done
  sudo systemctl is-active \
    openclaw-wecom-postgres.service \
    aicrm-internal-queue-runtime.service \
    aicrm-inbox-queue-runtime.service \
    aicrm-external-queue-runtime.service || true
  sudo systemctl is-active \
    openclaw-internal-event-worker.timer \
    openclaw-external-effect-worker.timer \
    openclaw-broadcast-queue-worker.timer \
    openclaw-ai-audience-scheduler.timer \
    openclaw-identity-resolution-worker.timer \
    openclaw-customer-read-model-refresh.timer \
    openclaw-automation-ops-scheduler.timer || true
  curl -sS http://127.0.0.1:5001/api/system/health || true
}
restore_runtime_from_guard() {
  local authorize_phase="$1"
  python3 "$release_control_manager" \
    --manifest "$release_control_manifest" \
    --phase "$authorize_phase" --execute \
    && python3 "$release_control_manager" \
      --manifest "$release_control_manifest" \
      --phase install-enable-after-web-health --execute \
    && python3 "$release_control_manager" \
      --manifest "$release_control_manifest" \
      --phase verify-staged-runtime --execute \
    && python3 "$release_control_manager" \
      --manifest "$release_control_manifest" \
      --phase release-runtime-guard --execute
}
resecure_runtime_guard() {
  python3 "$release_control_manager" \
    --manifest "$release_control_manifest" \
    --phase begin-transaction --execute \
    && python3 "$release_control_manager" \
      --manifest "$release_control_manifest" \
      --phase ensure-stopped-for-rollback --execute
}
fsync_provenance_file() {
  PROVENANCE_FILE="$1" /home/ubuntu/venvs/openclaw/bin/python -c 'import os, stat; path=os.environ["PROVENANCE_FILE"]; flags=os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0); descriptor=os.open(path, flags); info=os.fstat(descriptor); assert stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not (stat.S_IMODE(info.st_mode) & 0o022), "unsafe provenance file"; os.fsync(descriptor); os.close(descriptor)'
}
fsync_provenance_directory() {
  PROVENANCE_DIRECTORY="$release_provenance_directory" /home/ubuntu/venvs/openclaw/bin/python -c 'import os; path=os.environ["PROVENANCE_DIRECTORY"]; flags=os.O_RDONLY | getattr(os, "O_DIRECTORY", 0); descriptor=os.open(path, flags); os.fsync(descriptor); os.close(descriptor)'
}
expected_migration_heads_for_tree() {
  MIGRATION_TREE_ROOT="$1" /home/ubuntu/venvs/openclaw/bin/python -c 'import json, os; from pathlib import Path; from alembic.config import Config; from alembic.script import ScriptDirectory; root=Path(os.environ["MIGRATION_TREE_ROOT"]); config=Config(str(root / "alembic.ini")); config.set_main_option("script_location", str(root / "migrations")); heads=sorted(ScriptDirectory.from_config(config).get_heads()); assert heads, "migration tree has no heads"; print(json.dumps(heads))'
}
classify_schema_recovery_target() {
  EXPECTED_PREVIOUS_HEADS_JSON="$previous_expected_migration_heads_json" /home/ubuntu/venvs/openclaw/bin/python -c 'import json, os; from aicrm_next.platform_foundation.readiness import _expected_migration_heads; from aicrm_next.platform_foundation.repository import RuntimeReadinessRepository; from aicrm_next.shared.runtime import raw_database_url; previous=tuple(sorted(json.loads(os.environ["EXPECTED_PREVIOUS_HEADS_JSON"]))); verified=tuple(sorted(_expected_migration_heads())); context=RuntimeReadinessRepository(raw_database_url()); context.__enter__(); current=context.migration_revisions(); context.__exit__(None, None, None); matches_previous=current == previous; matches_verified=current == verified; target="previous" if matches_previous else ("verified" if matches_verified else "unknown"); print(f"{target}:{1 if matches_verified else 0}")'
}
refresh_schema_recovery_target() {
  local classification
  if ! classification="$(classify_schema_recovery_target)"; then
    classification="unknown:0"
  fi
  case "$classification" in
    previous:0)
      schema_recovery_target="previous"
      schema_aligned_to_verified_release=0
      ;;
    previous:1)
      schema_recovery_target="previous"
      schema_aligned_to_verified_release=1
      ;;
    verified:1)
      schema_recovery_target="verified"
      schema_aligned_to_verified_release=1
      ;;
    *)
      schema_recovery_target="unknown"
      schema_aligned_to_verified_release=0
      ;;
  esac
  echo "schema_recovery_target=$schema_recovery_target verified_match=$schema_aligned_to_verified_release"
  return 0
}
cleanup_deploy() {
  exit_status=$?
  trap - EXIT
  set +e
  cleanup_failed=0
  if [ -n "${deploy_smoke_session_file:-}" ] && [ -e "$deploy_smoke_session_file" ]; then
    if ! revoke_deploy_smoke_session "$deploy_smoke_session_file"; then
      echo "failed to revoke temporary deploy smoke session"
      cleanup_failed=1
    fi
    rm -f -- "$deploy_smoke_session_file"
  fi
  if [ "$exit_status" -ne 0 ] \
    && [ "${release_switched:-0}" = "1" ] \
    && [ "${runtime_committed:-0}" != "1" ]; then
    refresh_schema_recovery_target
    if [ "${schema_recovery_target:-unknown}" = "unknown" ]; then
      echo "database schema matches neither the previous nor verified release; keeping runtime guarded"
      restore_runtime_allowed=0
      cleanup_failed=1
    fi
  fi
  if [ "$exit_status" -ne 0 ] \
    && [ "${runtime_mutation_started:-0}" = "1" ] \
    && [ "${runtime_committed:-0}" != "1" ]; then
    if [ "${runtime_units_stopped:-0}" = "1" ]; then
      if ! python3 "$release_control_manager" \
        --manifest "$release_control_manifest" \
        --phase begin-transaction --execute; then
        cleanup_failed=1
      fi
      if ! python3 "$release_control_manager" \
        --manifest "$release_control_manifest" \
        --phase ensure-stopped-for-rollback --execute; then
        cleanup_failed=1
      fi
    else
      echo "runtime stop did not complete; preserving active one-shot workers during rollback"
      runtime_transaction_partial=1
    fi
  fi
  if [ "$exit_status" -ne 0 ] \
    && [ "${release_switched:-0}" = "1" ] \
    && [ "${runtime_committed:-0}" != "1" ] \
    && [ "${schema_recovery_target:-unknown}" != "previous" ] \
    && [ "${verified_release_web_smoke_passed:-0}" != "1" ] \
    && [ "${runtime_units_stopped:-0}" != "1" ]; then
    echo "schema is not rollback-compatible with the previous release and Web smoke is absent; stopping runtime fail-closed"
    if python3 "$release_control_manager" \
      --manifest "$release_control_manifest" \
      --phase begin-transaction --execute \
      && python3 "$release_control_manager" \
        --manifest "$release_control_manifest" \
        --phase ensure-stopped-for-rollback --execute; then
      runtime_units_stopped=1
      runtime_transaction_partial=0
    else
      restore_runtime_allowed=0
      cleanup_failed=1
    fi
  fi
  if [ "$exit_status" -ne 0 ] \
    && [ "${release_switched:-0}" = "1" ] \
    && [ "${release_committed:-0}" != "1" ] \
    && [ "${runtime_committed:-0}" != "1" ]; then
    if [ "${runtime_units_stopped:-0}" = "1" ]; then
      sudo systemctl stop aicrm-web.service || true
      sudo systemctl stop openclaw-wecom-postgres.service || true
    else
      echo "primary Web remains active while the partial runtime transaction is rolled back"
    fi
    if [ "${schema_recovery_target:-unknown}" = "unknown" ]; then
      echo "database schema is in an unknown intermediate state; preserving verified checkout and deploy guard"
      restore_expected_sha="$verified_sha"
      restore_runtime_allowed=0
      cleanup_failed=1
    elif [ "${schema_recovery_target:-unknown}" = "verified" ]; then
      if [ "${verified_release_web_smoke_passed:-0}" = "1" ]; then
        echo "schema already matches verified release; preserving smoke-verified checkout $verified_sha"
        restore_expected_sha="$verified_sha"
      else
        echo "schema already matches verified release but Web smoke did not pass; keeping runtime guarded"
        restore_expected_sha="$verified_sha"
        restore_runtime_allowed=0
        cleanup_failed=1
      fi
    else
      echo "deployment failed before schema alignment; rolling back to $before_sha"
      if git reset --hard "$before_sha"; then
        printf '%s\n' "$before_sha" > .release-sha
        if ! git diff --quiet "$before_sha" "$verified_sha" -- requirements.lock; then
          if ! /home/ubuntu/venvs/openclaw/bin/python -m pip install \
            --require-hashes -r requirements.lock; then
            echo "failed to restore dependencies for $before_sha"
            restore_runtime_allowed=0
            cleanup_failed=1
            if [ "${runtime_units_stopped:-0}" != "1" ]; then
              echo "dependency rollback failed while runtime was only partially stopped; securing deploy guard"
              if resecure_runtime_guard; then
                runtime_units_stopped=1
                runtime_transaction_partial=0
              else
                echo "failed to secure deploy guard after dependency rollback failure"
                print_runtime_release_diagnostics
              fi
            fi
          fi
        fi
      else
        echo "failed to restore checkout to $before_sha"
        restore_runtime_allowed=0
        cleanup_failed=1
      fi
    fi
  fi
  if [ "${runtime_units_stopped:-0}" = "1" ] \
    && [ "${restore_runtime_allowed:-1}" = "1" ]; then
    echo "restoring runtime units for $restore_expected_sha"
    if ! python3 "$release_control_manager" \
      --manifest "$release_control_manifest" \
      --phase authorize-web-start --execute; then
      cleanup_failed=1
    fi
    sudo systemctl reset-failed \
      openclaw-wecom-postgres.service || true
    sudo systemctl start openclaw-wecom-postgres.service
    restored_web_ready=0
    for _ in $(seq 1 30); do
      if curl -sSf -D /tmp/aicrm_cleanup_health_headers.txt \
        http://127.0.0.1:5001/health \
        -o /tmp/aicrm_cleanup_health.json \
        && grep -i "x-aicrm-release-sha: $restore_expected_sha" \
          /tmp/aicrm_cleanup_health_headers.txt; then
        restored_web_ready=1
        break
      fi
      sleep 1
    done
    if [ "$restored_web_ready" = "1" ]; then
      if verify_system_health_for_runtime_release \
        "$restore_expected_sha" \
        /tmp/aicrm-cleanup-system-health.json; then
        if ! restore_runtime_from_guard authorize-runtime-start; then
          echo "runtime restore failed; re-securing deploy guard"
          resecure_runtime_guard || true
          print_runtime_release_diagnostics
          cleanup_failed=1
        fi
      else
        echo "restored Web failed release-safe system health; runtime remains guarded"
        print_runtime_release_diagnostics
        cleanup_failed=1
      fi
    else
      echo "web health unavailable; runtime units could not be safely restored"
      cleanup_failed=1
    fi
  fi
  if [ "${runtime_transaction_partial:-0}" = "1" ] \
    && [ "${runtime_units_stopped:-0}" != "1" ] \
    && [ "${runtime_committed:-0}" != "1" ] \
    && [ "${restore_runtime_allowed:-1}" = "1" ] \
    && [ "${schema_recovery_target:-unknown}" = "previous" ]; then
    echo "restoring timers after a partial runtime stop for $restore_expected_sha"
    partial_web_ready=0
    for _ in $(seq 1 10); do
      if curl -sSf -D /tmp/aicrm_cleanup_partial_health_headers.txt \
        http://127.0.0.1:5001/health \
        -o /tmp/aicrm_cleanup_partial_health.json \
        && grep -i "x-aicrm-release-sha: $restore_expected_sha" \
          /tmp/aicrm_cleanup_partial_health_headers.txt; then
        partial_web_ready=1
        break
      fi
      sleep 1
    done
    if [ "$partial_web_ready" = "1" ]; then
      if verify_system_health_for_runtime_release \
        "$restore_expected_sha" \
        /tmp/aicrm-cleanup-partial-system-health.json; then
        if ! restore_runtime_from_guard authorize-runtime-restore; then
          echo "partial runtime restore failed; re-securing deploy guard"
          resecure_runtime_guard || true
          print_runtime_release_diagnostics
          cleanup_failed=1
        else
          runtime_transaction_partial=0
        fi
      else
        echo "partially stopped runtime failed release-safe system health; runtime remains guarded"
        print_runtime_release_diagnostics
        cleanup_failed=1
      fi
    else
      echo "existing Web health unavailable; partially stopped timers could not be restored"
      cleanup_failed=1
    fi
  fi
  rm -rf -- "$release_control_dir"
  rm -rf -- "$release_bundle_dir"
  if [ -n "${release_provenance_tmp:-}" ]; then
    rm -f -- "$release_provenance_tmp"
  fi
  if [ "${release_provenance_prepared_owned:-0}" = "1" ]; then
    if [ "${runtime_committed:-0}" = "1" ] \
      && [ "${release_committed:-0}" != "1" ]; then
      echo "preserving validated prepared provenance for full-readiness recovery"
    else
      rm -f -- "$release_provenance_prepared"
    fi
  fi
  if [ "${release_provenance_pending_owned:-0}" = "1" ]; then
    if [ "${runtime_committed:-0}" = "1" ] \
      && [ "${release_committed:-0}" != "1" ]; then
      echo "preserving validated pending provenance for same-SHA no-op recovery"
    else
      rm -f -- "$release_provenance_pending"
    fi
  fi
  if [ "$exit_status" -eq 0 ] && [ "$cleanup_failed" -ne 0 ]; then
    exit_status=1
  fi
  exit "$exit_status"
}
trap cleanup_deploy EXIT
if [ ! -r "$release_bundle" ] || [ ! -r "$release_bundle_checksum" ]; then
  echo "verified release bundle or checksum is missing"
  exit 1
fi
(
  cd "$release_bundle_dir"
  sha256sum -c aicrm-release.bundle.sha256
)
actual_bundle_sha256="$(awk '{print $1}' "$release_bundle_checksum")"
if [ "$actual_bundle_sha256" != "$bundle_sha256" ]; then
  echo "release bundle checksum does not match workflow provenance"
  exit 1
fi
git bundle verify "$release_bundle"
if ! git bundle list-heads "$release_bundle" \
  | grep -Fx "$verified_sha refs/deploy/release" >/dev/null; then
  echo "release bundle does not advertise the verified workflow sha"
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git stash push --include-untracked -m "deploy-backup-$(date -u +%Y%m%dT%H%M%SZ)"
fi
git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/deploy/main"
release_head_sha="$(git rev-parse refs/remotes/deploy/main)"
if [ "$release_head_sha" != "$verified_sha" ]; then
  echo "verified workflow sha is no longer the repository main head"
  exit 1
fi
release_control_dir="$(mktemp -d /tmp/aicrm-release-control.XXXXXX)"
git archive "$verified_sha" \
  app.py \
  scripts \
  deploy \
  | tar -x -C "$release_control_dir"
release_control_manager="$release_control_dir/scripts/ops/manage_production_runtime_units.py"
release_control_manifest="$release_control_dir/deploy/production_runtime_units.json"
bash "$release_control_dir/scripts/ops/normalize_queue_runtime_generation_marker.sh"
set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
test -n "${DATABASE_URL:-}"
source /home/ubuntu/venvs/openclaw/bin/activate
if [ -e "$release_provenance_pending" ] \
  || [ -e "$release_provenance_prepared" ]; then
  echo "recovering provenance for active base release $before_sha before deploying $verified_sha"
  test "$(tr -d '\r\n' < .release-sha)" = "$before_sha"
  python3 scripts/ops/manage_production_runtime_units.py --phase verify --execute
  python3 scripts/ops/check_id_validation_release_readiness.py \
    --public-health-url "$public_health_url" \
    --expected-sha "$before_sha" \
    > /tmp/aicrm-active-release-readiness.json
  cat /tmp/aicrm-active-release-readiness.json
  /home/ubuntu/venvs/openclaw/bin/python \
    "$release_control_dir/scripts/ops/recover_id_validation_provenance.py" \
    --canonical "$release_provenance_directory/id-validation.json" \
    --pending "$release_provenance_pending" \
    --prepared "$release_provenance_prepared" \
    --expected-repository "$expected_repository" \
    --expected-release-sha "$before_sha" \
    --expected-public-health-url "$public_health_url" \
    --repository-path '/home/ubuntu/极简 crm' \
    --promote-pending \
    --allow-prepared-recovery \
    --require-canonical-base-chain \
    > /tmp/aicrm-active-provenance-recovery.json
  cat /tmp/aicrm-active-provenance-recovery.json
  test ! -e "$release_provenance_pending"
  test ! -e "$release_provenance_prepared"
fi
previous_migration_tree="$release_control_dir/previous-migration-tree"
mkdir -p "$previous_migration_tree"
git archive "$before_sha" alembic.ini migrations \
  | tar -x -C "$previous_migration_tree"
previous_expected_migration_heads_json="$(
  expected_migration_heads_for_tree "$previous_migration_tree"
)"
git reset --hard "$verified_sha"
release_switched=1
after_sha="$(git rev-parse HEAD)"
if [ "$after_sha" != "$verified_sha" ]; then
  echo "deployed checkout does not match verified workflow sha"
  exit 1
fi
printf '%s\n' "$after_sha" > .release-sha
python3 scripts/ops/manage_production_runtime_units.py --phase retire-legacy-overlays --execute
set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
test -n "${DATABASE_URL:-}"
source /home/ubuntu/venvs/openclaw/bin/activate
if [ "$before_sha" = "$after_sha" ] || git diff --quiet "$before_sha" "$after_sha" -- requirements.lock; then
  echo "requirements.lock unchanged; skipping pip install"
else
  python -m pip install --require-hashes -r requirements.lock
fi
python3 scripts/ops/ensure_ai_audience_external_api_env.py /home/ubuntu/.openclaw-wecom-pg.env
auth_issuer="${public_base_url}"
if ! printf '%s' "$auth_issuer" | grep -Eq '^https://[^/]+$'; then
  echo "PUBLIC_BASE_URL must be an https origin"
  exit 1
fi
runtime_environment_args=()
if [ "${allow_missing_wechat_shop_callback_token}" = "1" ]; then
  runtime_environment_args+=(--allow-missing-wechat-shop-callback-token)
fi
python3 -m scripts.ops.ensure_runtime_environment \
  --environment-file /home/ubuntu/.openclaw-wecom-pg.env \
  --target-environment "$runtime_target_environment" \
  --public-base-url "$auth_issuer" \
  "${runtime_environment_args[@]}"
deprecated_runtime_env_keys="$(
  python3 - <<'PY'
from scripts.ops.ensure_runtime_environment import DEPRECATED_RUNTIME_ENV_KEYS

print("\n".join(sorted(DEPRECATED_RUNTIME_ENV_KEYS)))
PY
)"
while IFS= read -r deprecated_runtime_env_key; do
  test -n "$deprecated_runtime_env_key" || continue
  unset "$deprecated_runtime_env_key"
done <<< "$deprecated_runtime_env_keys"
set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
python3 - <<'PY'
from aicrm_next.shared.wecom_runtime import load_wecom_execution_config

config = load_wecom_execution_config()
if config.conflict:
    raise SystemExit("WeCom execution config remains conflicting after deprecated environment cleanup")
print(f"WeCom execution config coherent: mode={config.execution_mode}")
PY
refresh_schema_recovery_target
# Identity preflight must fail before any runtime unit is stopped.
python3 scripts/ops/check_unionid_identity_cutover.py \
  --phase preflight \
  --register-existing-conflicts \
  --expected-release-sha "$after_sha" \
  | tee /tmp/aicrm-identity-preflight.json
runtime_mutation_started=1
runtime_transaction_partial=1
python3 "$release_control_manager" \
  --manifest "$release_control_manifest" \
  --phase begin-transaction --execute
# The previous identity worker held its claim transaction open while
# re-enqueueing the same source from another connection. Recover only
# that exact, aged self-deadlock while the deploy guard blocks restarts.
python3 scripts/ops/recover_identity_resolution_worker_deadlock.py \
  --execute \
  | tee /tmp/aicrm-identity-worker-deadlock-recovery.json
if [ "$base_source" = "guarded_server_checkout" ]; then
  echo "guarded recovery accepts enabled runtime units that are already inactive"
  python3 "$release_control_manager" \
    --manifest "$release_control_manifest" \
    --phase stop-for-migration-recovery --execute
else
  python3 "$release_control_manager" \
    --manifest "$release_control_manifest" \
    --phase stop-for-migration --execute
fi
runtime_units_stopped=1
runtime_transaction_partial=0
if sudo fuser -s 5001/tcp; then
  echo "5001 is still occupied before release mutation; terminating stale listener"
  sudo ss -ltnp 'sport = :5001' || true
  sudo fuser -k -TERM 5001/tcp || true
  sleep 2
fi
if sudo fuser -s 5001/tcp; then
  echo "5001 listener survived TERM; force killing stale listener"
  sudo ss -ltnp 'sport = :5001' || true
  sudo fuser -k -KILL 5001/tcp || true
fi
for _ in $(seq 1 10); do
  if ! sudo fuser -s 5001/tcp; then
    break
  fi
  echo "waiting for stale 5001 listener to exit"
  sleep 1
done
if sudo fuser -s 5001/tcp; then
  echo "5001 is still occupied after stale listener cleanup"
  sudo ss -ltnp 'sport = :5001' || true
  exit 1
fi
# 1) AI-CRM Next schema migrations
python3 -m alembic upgrade head
refresh_schema_recovery_target
if [ "$schema_aligned_to_verified_release" != "1" ]; then
  echo "database schema does not match the verified release after migration"
  exit 1
fi
export AICRM_SECRET_STORE_DIR="${AICRM_SECRET_STORE_DIR:-/home/ubuntu/.aicrm-secrets}"
python3 scripts/ops/migrate_app_setting_secrets.py --execute \
  --secret-store-dir "$AICRM_SECRET_STORE_DIR" \
  --environment-file /home/ubuntu/.openclaw-wecom-pg.env \
  | tee /tmp/aicrm-secret-migration.json
python3 scripts/ops/bootstrap_auth_clients.py \
  --apply \
  --issuer "$auth_issuer" \
  --secret-store-dir "$AICRM_SECRET_STORE_DIR" \
  --environment-file /home/ubuntu/.openclaw-wecom-pg.env \
  | tee /tmp/aicrm-auth-client-bootstrap.json
set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
python3 scripts/ops/check_auth_readiness.py \
  --issuer "$auth_issuer" \
  --secret-store-dir "$AICRM_SECRET_STORE_DIR" \
  --environment-file /home/ubuntu/.openclaw-wecom-pg.env \
  | tee /tmp/aicrm-auth-readiness.json
python3 scripts/ops/check_secret_reference_cutover.py \
  --secret-store-dir "$AICRM_SECRET_STORE_DIR" \
  --environment-file /home/ubuntu/.openclaw-wecom-pg.env \
  | tee /tmp/aicrm-secret-reconciliation.json
python3 scripts/ops/manage_production_runtime_units.py --phase install-primary-web --execute
python3 scripts/ops/manage_production_runtime_units.py --phase authorize-web-start --execute
sudo systemctl reset-failed openclaw-wecom-postgres.service || true
if ! sudo systemctl start openclaw-wecom-postgres.service; then
  sudo systemctl status openclaw-wecom-postgres.service --no-pager || true
  sudo journalctl -u openclaw-wecom-postgres.service -n 80 --no-pager || true
  sudo ss -ltnp 'sport = :5001' || true
  exit 1
fi
release_ready=0
for _ in $(seq 1 60); do
  if curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health -o /tmp/aicrm_health.json \
    && grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt; then
    release_ready=1
    break
  fi
  actual_release_sha="$(awk 'tolower($1) == "x-aicrm-release-sha:" {print $2}' /tmp/aicrm_health_headers.txt 2>/dev/null | tr -d '\r' | tail -n 1 || true)"
  echo "waiting for 5001 release sha: expected=$after_sha actual=${actual_release_sha:-missing}"
  sleep 1
done
if [ "$release_ready" != "1" ]; then
  sudo systemctl status openclaw-wecom-postgres.service --no-pager || true
  sudo journalctl -u openclaw-wecom-postgres.service -n 80 --no-pager || true
  exit 1
fi
cat /tmp/aicrm_health.json
python3 scripts/ops/check_unionid_identity_cutover.py \
  --phase post-deploy \
  --expected-release-sha "$after_sha" \
  | tee /tmp/aicrm-identity-reconciliation.json
runtime_secret_args=()
if [ "${allow_missing_wechat_shop_callback_token}" = "1" ]; then
  runtime_secret_args+=(--allow-missing-wechat-shop-callback-token)
fi
python scripts/ops/check_runtime_secret_readiness.py \
  --base-url http://127.0.0.1:5001 \
  --expected-sha "$after_sha" \
  --expected-callback-url "$auth_issuer/auth/wecom/callback" \
  "${runtime_secret_args[@]}" \
  | tee /tmp/aicrm-runtime-secret-readiness.json
deploy_smoke_session_file="$(mktemp /tmp/aicrm-deploy-smoke-session.XXXXXX)"
python3 scripts/ops/create_deploy_smoke_session.py issue \
  --output-file "$deploy_smoke_session_file" \
  --ttl-seconds 300 \
  | tee /tmp/aicrm-deploy-smoke-session-issue.json
admin_smoke_sidebar_args=(--include-all-sidebar)
if ! python scripts/ops/check_admin_read_pages_smoke.py \
  --base-url http://127.0.0.1:5001 \
  --require-admin-cookie \
  --admin-cookie-file "$deploy_smoke_session_file" \
  "${admin_smoke_sidebar_args[@]}" \
  | tee /tmp/aicrm-admin-read-pages-pre-runtime-smoke.json; then
  sudo systemctl status openclaw-wecom-postgres.service --no-pager || true
  sudo journalctl -u openclaw-wecom-postgres.service -n 120 --no-pager || true
  exit 1
fi
revoke_deploy_smoke_session "$deploy_smoke_session_file"
deploy_smoke_session_file=""
if ! verify_system_health_for_runtime_release \
  "$after_sha" \
  /tmp/aicrm-pre-runtime-release-system-health.json; then
  echo "new release failed system health before runtime authorization"
  print_runtime_release_diagnostics
  exit 1
fi
if ! python3 scripts/ops/manage_production_runtime_units.py --phase authorize-runtime-start --execute; then
  echo "runtime authorization failed after release-safe system health"
  print_runtime_release_diagnostics
  exit 1
fi
python3 scripts/ops/manage_production_runtime_units.py --phase install-enable-after-web-health --execute
# The candidate internal runtime is now the sole queue owner. Ask it to repair
# the local projection through the durable intent and wait for completion;
# this deploy path never rebuilds inline and never calls a provider.
python3 scripts/run_customer_read_model_refresh.py \
  --execute \
  --source-key "deploy_runtime:${release_run_id}:${release_run_attempt}" \
  --wait-seconds 180 \
  | tee /tmp/aicrm-customer-read-model-deploy-runtime.json
deploy_smoke_session_file="$(mktemp /tmp/aicrm-deploy-strict-smoke-session.XXXXXX)"
python3 scripts/ops/create_deploy_smoke_session.py issue \
  --output-file "$deploy_smoke_session_file" \
  --ttl-seconds 300 \
  | tee /tmp/aicrm-deploy-strict-smoke-session-issue.json
if ! python scripts/ops/check_admin_read_pages_smoke.py \
  --base-url http://127.0.0.1:5001 \
  --require-admin-cookie \
  --admin-cookie-file "$deploy_smoke_session_file" \
  "${admin_smoke_sidebar_args[@]}" \
  --require-all-data-health-green \
  | tee /tmp/aicrm-admin-read-pages-smoke.json; then
  sudo systemctl status openclaw-wecom-postgres.service --no-pager || true
  sudo journalctl -u openclaw-wecom-postgres.service -n 120 --no-pager || true
  exit 1
fi
verified_release_web_smoke_passed=1
revoke_deploy_smoke_session "$deploy_smoke_session_file"
deploy_smoke_session_file=""
python scripts/ops/check_wecom_callback_deploy_smoke.py | tee /tmp/wecom-callback-deploy-smoke.json
python3 scripts/ops/manage_production_runtime_units.py --phase verify-staged-runtime --execute
curl -sSf http://127.0.0.1:5001/api/system/health \
  | tee /tmp/aicrm-runtime-readiness.json
# Count-only R06 reconciliation. This command never repairs rows or executes consumers/providers.
python scripts/ops/reconcile_internal_event_outbox.py \
  | tee /tmp/aicrm-internal-event-outbox-reconciliation.json
# Count-only R08 commerce fulfillment reconciliation. Never repairs or calls providers.
python scripts/ops/reconcile_commerce_fulfillment.py \
  | tee /tmp/aicrm-commerce-fulfillment-reconciliation.json
# Count-only R09 questionnaire/radar reconciliation. Never repairs or executes consumers/providers.
python scripts/ops/reconcile_questionnaire_radar.py \
  | tee /tmp/aicrm-questionnaire-radar-reconciliation.json
# Count-only R10 Group Ops/broadcast reconciliation. Never repairs, resends, or calls providers.
python scripts/ops/reconcile_group_ops_broadcast.py \
  | tee /tmp/aicrm-group-ops-broadcast-reconciliation.json
public_release_ready=0
for _ in $(seq 1 30); do
  if curl -sSf -D /tmp/aicrm_id_validation_public_health_headers.txt \
    "${public_health_url}" \
    -o /tmp/aicrm_id_validation_public_health.json \
    && grep -i "x-aicrm-release-sha: $after_sha" \
      /tmp/aicrm_id_validation_public_health_headers.txt; then
    public_release_ready=1
    break
  fi
  actual_public_release_sha="$(awk 'tolower($1) == "x-aicrm-release-sha:" {print $2}' \
    /tmp/aicrm_id_validation_public_health_headers.txt 2>/dev/null | tr -d '\r' | tail -n 1 || true)"
  echo "waiting for public ID validation release sha: expected=$after_sha actual=${actual_public_release_sha:-missing}"
  sleep 2
done
if [ "$public_release_ready" != "1" ]; then
  echo "public ID validation health does not expose the deployed release sha"
  exit 1
fi
cat /tmp/aicrm_id_validation_public_health.json
python3 scripts/ops/check_id_validation_release_readiness.py \
  --public-health-url "$public_health_url" \
  --expected-sha "$after_sha" \
  > /tmp/aicrm-id-validation-final-readiness.json
cat /tmp/aicrm-id-validation-final-readiness.json
install -d -m 0750 /home/ubuntu/.aicrm-releases
release_provenance_tmp="$(mktemp /home/ubuntu/.aicrm-releases/id-validation.XXXXXX)"
RELEASE_REPOSITORY="$release_repository" \
RELEASE_RUN_ID="$release_run_id" \
RELEASE_RUN_ATTEMPT="$release_run_attempt" \
SOURCE_CI_RUN_ID="$source_ci_run_id" \
RELEASE_SHA="$after_sha" \
BASE_SHA="$before_sha" \
BUNDLE_SHA256="$bundle_sha256" \
DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  python3 -c 'import json, os, sys; json.dump({"repository": os.environ["RELEASE_REPOSITORY"], "deploy_run_id": os.environ["RELEASE_RUN_ID"], "deploy_run_attempt": os.environ["RELEASE_RUN_ATTEMPT"], "source_ci_run_id": os.environ["SOURCE_CI_RUN_ID"], "release_sha": os.environ["RELEASE_SHA"], "base_sha": os.environ["BASE_SHA"], "bundle_sha256": os.environ["BUNDLE_SHA256"], "environment": "id-validation", "public_health_url": "https://id-dev.youcangogogo.com/health", "deployed_at": os.environ["DEPLOYED_AT"]}, sys.stdout, sort_keys=True); sys.stdout.write("\n")' \
  > "$release_provenance_tmp"
python3 -m json.tool "$release_provenance_tmp" >/dev/null
chmod 0640 "$release_provenance_tmp"
fsync_provenance_file "$release_provenance_tmp"
release_provenance_prepared_owned=1
mv -f "$release_provenance_tmp" "$release_provenance_prepared"
release_provenance_tmp=""
fsync_provenance_directory
python3 scripts/ops/manage_production_runtime_units.py --phase release-runtime-guard --execute
runtime_units_stopped=0
runtime_committed=1
release_provenance_pending_owned=1
mv -f "$release_provenance_prepared" "$release_provenance_pending"
release_provenance_prepared_owned=0
fsync_provenance_directory
mv -f "$release_provenance_pending" /home/ubuntu/.aicrm-releases/id-validation.json
release_provenance_pending_owned=0
fsync_provenance_directory
release_committed=1
