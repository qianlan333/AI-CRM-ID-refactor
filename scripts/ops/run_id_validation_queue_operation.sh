#!/usr/bin/env bash
set -e
set -o pipefail
umask 077

readonly repository_path='/home/ubuntu/极简 crm'
readonly expected_repository="${EXPECTED_REPOSITORY:-}"
readonly deploy_target="${DEPLOY_TARGET:-}"
readonly public_base_url="${PUBLIC_BASE_URL:-}"
readonly public_health_url="${PUBLIC_HEALTH_URL:-}"
readonly expected_release_sha="${EXPECTED_RELEASE_SHA:-}"
readonly queue_operation="${QUEUE_OPERATION:-}"
readonly queue_expected_generation="${QUEUE_EXPECTED_GENERATION:-0}"
readonly queue_generation="${QUEUE_GENERATION:-0}"
readonly queue_policy_version="${QUEUE_POLICY_VERSION:-}"
readonly operator_actor="${OPERATOR_ACTOR:-}"
readonly operation_run_id="${OPERATION_RUN_ID:-}"
readonly operation_run_attempt="${OPERATION_RUN_ATTEMPT:-}"
queue_target_policy_version="${QUEUE_TARGET_POLICY_VERSION:-}"
queue_run_id="${QUEUE_RUN_ID:-}"
readonly queue_execution_id="${QUEUE_EXECUTION_ID:-}"
readonly queue_job_id="${QUEUE_JOB_ID:-0}"
readonly queue_expected_version="${QUEUE_EXPECTED_VERSION:-0}"
readonly queue_evidence_type="${QUEUE_EVIDENCE_TYPE:-}"

fail() {
  echo "$1" >&2
  exit 1
}

if [ "$expected_repository" != "qianlan333/AI-CRM-ID-refactor" ]; then
  fail "queue operation refuses an unexpected repository"
fi
if [ "$deploy_target" != "id-validation" ]; then
  fail "queue operation refuses an unexpected deploy target"
fi
if [ "$public_base_url" != "https://id-dev.youcangogogo.com" ] || \
   [ "$public_health_url" != "https://id-dev.youcangogogo.com/health" ]; then
  fail "queue operation refuses an unexpected public target"
fi
if ! printf '%s' "$expected_release_sha" | grep -Eq '^[0-9a-f]{40}$'; then
  fail "expected release must be one full SHA"
fi
if ! printf '%s' "$queue_expected_generation" | grep -Eq '^[0-9]+$' || \
   ! printf '%s' "$queue_generation" | grep -Eq '^[1-9][0-9]*$'; then
  fail "queue generation inputs are invalid"
fi
if ! printf '%s' "$queue_policy_version" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'; then
  fail "queue policy version is invalid"
fi
if [ -n "$queue_target_policy_version" ] && \
   ! printf '%s' "$queue_target_policy_version" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'; then
  fail "queue target policy version is invalid"
fi
if ! printf '%s' "$operator_actor" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$' || \
   ! printf '%s' "$operation_run_id" | grep -Eq '^[1-9][0-9]*$' || \
   ! printf '%s' "$operation_run_attempt" | grep -Eq '^[1-9][0-9]*$'; then
  fail "GitHub operation provenance is invalid"
fi
if ! printf '%s' "$queue_job_id" | grep -Eq '^[0-9]+$' || \
   ! printf '%s' "$queue_expected_version" | grep -Eq '^[0-9]+$'; then
  fail "queue job id or expected row version is invalid"
fi
case "$queue_operation" in
  activate_test_loopback|verify_owner_state|run_test_loopback|configure_allowlisted|\
  transition_allowlisted|run_wecom_canary|authorize_execution|attest_execution|fault_listener|\
  fault_worker|fault_database|rollback_test_loopback|soak_start|soak_status|\
  soak_complete|soak_invalidate)
    ;;
  *)
    fail "unsupported ID-validation queue operation"
    ;;
esac

if [ -z "$queue_run_id" ]; then
  queue_run_id="gh-${operation_run_id}-${operation_run_attempt}"
fi
if ! printf '%s' "$queue_run_id" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'; then
  fail "queue run id is invalid"
fi
if [ -z "$queue_target_policy_version" ]; then
  case "$queue_operation" in
    transition_allowlisted)
      queue_target_policy_version="queue-v2-allowlisted-${expected_release_sha:0:12}"
      ;;
    rollback_test_loopback)
      queue_target_policy_version="queue-v2-test-loopback-${expected_release_sha:0:8}-${operation_run_id}"
      ;;
  esac
fi

exec 9>"/tmp/aicrm-deploy-${deploy_target}.lock"
if ! flock -n 9; then
  fail "another ID-validation deploy or queue mutation holds the server lock"
fi

cd "$repository_path"
remote_origin_url="$(git remote get-url origin)"
case "$remote_origin_url" in
  "https://github.com/${expected_repository}"|\
  "https://github.com/${expected_repository}.git"|\
  "git@github.com:${expected_repository}"|\
  "git@github.com:${expected_repository}.git")
    ;;
  *)
    fail "server checkout origin is not the ID validation repository"
    ;;
esac
if [ "$(git rev-parse HEAD)" != "$expected_release_sha" ]; then
  fail "server checkout does not match the requested release"
fi
if [ ! -f .release-sha ] || [ -L .release-sha ] || \
   [ "$(tr -d '\r\n' < .release-sha)" != "$expected_release_sha" ]; then
  fail "server release marker does not match the requested release"
fi
if [ -n "$(git status --porcelain=v1 --untracked-files=all)" ]; then
  git status --short --untracked-files=all >&2
  fail "queue operation refuses a dirty server checkout"
fi
python3 - "$expected_release_sha" "$expected_repository" "$public_health_url" <<'PY'
import json
import sys
from pathlib import Path

expected_sha, expected_repository, expected_health_url = sys.argv[1:]
path = Path("/home/ubuntu/.aicrm-releases/id-validation.json")
if path.is_symlink() or not path.is_file():
    raise SystemExit("canonical ID-validation provenance is missing")
payload = json.loads(path.read_text(encoding="utf-8"))
expected = {
    "release_sha": expected_sha,
    "repository": expected_repository,
    "environment": "id-validation",
    "public_health_url": expected_health_url,
}
for key, value in expected.items():
    if payload.get(key) != value:
        raise SystemExit(f"canonical provenance {key} mismatch")
PY

rm -f /tmp/aicrm-queue-operation-health.headers
curl --retry 3 --retry-all-errors --connect-timeout 10 --max-time 30 -fsS \
  -D /tmp/aicrm-queue-operation-health.headers \
  -o /dev/null \
  "$public_health_url"
python3 - /tmp/aicrm-queue-operation-health.headers "$expected_release_sha" <<'PY'
import sys
from pathlib import Path

headers = Path(sys.argv[1]).read_text(encoding="iso-8859-1")
expected = sys.argv[2]
values = []
for line in headers.replace("\r\n", "\n").splitlines():
    name, separator, value = line.partition(":")
    if separator and name.lower() == "x-aicrm-release-sha":
        values.append(value.strip())
if values != [expected]:
    raise SystemExit("public health does not expose the exact requested release")
PY

set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
test -n "${DATABASE_URL:-}" || fail "DATABASE_URL is missing"
source /home/ubuntu/venvs/openclaw/bin/activate

readonly actor="github:${operator_actor}"
readonly reason="ID validation ${queue_operation} via GitHub Actions ${operation_run_id}/${operation_run_attempt}"
spec_file=""
cleanup() {
  if [ -n "$spec_file" ]; then
    rm -f -- "$spec_file"
  fi
  rm -f /tmp/aicrm-queue-operation-health.headers
}
trap cleanup EXIT

require_canary_spec() {
  if [ -z "${WECOM_CANARY_SPEC_B64:-}" ]; then
    fail "ID_VALIDATION_WECOM_CANARY_SPEC_B64 is not configured"
  fi
  spec_file="$(mktemp /tmp/aicrm-wecom-canary.XXXXXX.json)"
  WECOM_CANARY_SPEC_B64="$WECOM_CANARY_SPEC_B64" python3 - "$spec_file" <<'PY'
import base64
import binascii
import os
import sys
from pathlib import Path

try:
    decoded = base64.b64decode(os.environ["WECOM_CANARY_SPEC_B64"], validate=True)
except (KeyError, binascii.Error) as exc:
    raise SystemExit("canary spec secret is not strict base64") from exc
if not decoded or len(decoded) > 65536:
    raise SystemExit("canary spec secret has an invalid size")
Path(sys.argv[1]).write_bytes(decoded)
PY
  unset WECOM_CANARY_SPEC_B64
  chmod 0600 "$spec_file"
}

common_identity=(
  --expected-release-sha "$expected_release_sha"
  --generation "$queue_generation"
  --expected-policy-version "$queue_policy_version"
  --actor "$actor"
  --reason "$reason"
)

case "$queue_operation" in
  activate_test_loopback)
    AICRM_QUEUE_CUTOVER_AUTHORIZED=1 python3 scripts/ops/cutover_queue_runtime_generation.py \
      --expected-generation "$queue_expected_generation" \
      --target-generation "$queue_generation" \
      --expected-policy-version "$queue_policy_version" \
      --lane internal_general \
      --lane internal_financial \
      --lane webhook_inbox \
      --lane wecom_interactive \
      --lane wecom_bulk \
      --lane wecom_media \
      --lane outbound_webhook \
      --owner-inventory pr3 \
      --actor "$actor" \
      --reason "$reason" \
      --apply \
      --confirmation "ACTIVATE_QUEUE_GENERATION_${queue_generation}"
    ;;
  verify_owner_state)
    python3 scripts/ops/cutover_queue_runtime_generation.py \
      --expected-generation "$queue_expected_generation" \
      --target-generation "$queue_generation" \
      --expected-policy-version "$queue_policy_version" \
      --lane internal_general \
      --owner-inventory pr3 \
      --actor "$actor" \
      --reason "$reason" \
      --verify-owner-state
    ;;
  run_test_loopback)
    AICRM_TEST_LOOPBACK_CANARY_AUTHORIZED=1 python3 scripts/ops/run_test_loopback_canary.py \
      --base-url "$public_base_url" \
      --scenario questionnaire_submission_push_success \
      --run-id "$queue_run_id" \
      "${common_identity[@]}" \
      --apply \
      --confirmation "RUN_TEST_LOOPBACK_${queue_run_id}_${queue_generation}"
    ;;
  configure_allowlisted)
    require_canary_spec
    AICRM_WECOM_CANARY_CONFIG_AUTHORIZED=1 python3 scripts/ops/configure_wecom_canary.py \
      --mode enable \
      --spec-file "$spec_file" \
      --generation "$queue_generation" \
      --expected-policy-version "$queue_policy_version" \
      --actor "$actor" \
      --reason "$reason" \
      --apply \
      --confirmation "CONFIGURE_WECOM_CANARY_${queue_generation}_ENABLE"
    ;;
  transition_allowlisted)
    test -n "$queue_target_policy_version" || fail "target policy version is required"
    AICRM_QUEUE_SCOPE_TRANSITION_AUTHORIZED=1 python3 scripts/ops/transition_queue_runtime_scope.py \
      --generation "$queue_generation" \
      --expected-policy-version "$queue_policy_version" \
      --target-policy-version "$queue_target_policy_version" \
      --expected-scope test_loopback \
      --target-scope allowlisted \
      --actor "$actor" \
      --reason "$reason" \
      --apply \
      --confirmation "TRANSITION_QUEUE_SCOPE_${queue_generation}_TEST_LOOPBACK_TO_ALLOWLISTED"
    ;;
  run_wecom_canary)
    require_canary_spec
    AICRM_WECOM_CANARY_PLAN_AUTHORIZED=1 python3 scripts/ops/plan_wecom_canary.py \
      --spec-file "$spec_file" \
      --run-id "$queue_run_id" \
      "${common_identity[@]}" \
      --apply \
      --confirmation "PLAN_WECOM_CANARY_${queue_run_id^^}_${queue_generation}"
    ;;
  authorize_execution)
    if ! printf '%s' "$queue_execution_id" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$' || \
       ! printf '%s' "$queue_expected_version" | grep -Eq '^[1-9][0-9]*$'; then
      fail "execution id and positive expected version are required for authorization"
    fi
    authorize_job_args=()
    if [ "$queue_job_id" != "0" ]; then
      authorize_job_args=(--job-id "$queue_job_id")
    fi
    AICRM_WECOM_CANARY_AUTHORIZE_AUTHORIZED=1 python3 scripts/ops/authorize_wecom_canary_execution.py \
      --execution-id "$queue_execution_id" \
      "${authorize_job_args[@]}" \
      --expected-version "$queue_expected_version" \
      "${common_identity[@]}" \
      --apply \
      --confirmation "AUTHORIZE_WECOM_CANARY_${queue_execution_id}_${queue_expected_version}"
    ;;
  attest_execution)
    if ! printf '%s' "$queue_execution_id" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'; then
      fail "execution id is required for attestation"
    fi
    case "$queue_evidence_type" in
      test_loopback|wecom_private|wecom_group|wecom_welcome|wecom_tag|\
      wecom_profile|wecom_contact_detail|wecom_media)
        ;;
      *)
        fail "unsupported external evidence type"
        ;;
    esac
    attest_job_args=()
    if [ "$queue_job_id" != "0" ]; then
      attest_job_args=(--job-id "$queue_job_id")
    fi
    AICRM_QUEUE_EVIDENCE_ATTEST_AUTHORIZED=1 python3 scripts/ops/attest_queue_runtime_validation.py \
      --execution-id "$queue_execution_id" \
      "${attest_job_args[@]}" \
      --evidence-type "$queue_evidence_type" \
      "${common_identity[@]}" \
      --apply \
      --confirmation "ATTEST_QUEUE_EVIDENCE_${queue_execution_id}_${queue_generation}"
    ;;
  fault_listener|fault_worker|fault_database)
    case "$queue_operation" in
      fault_listener) fault_action="listener_reconnect" ;;
      fault_worker) fault_action="worker_restart" ;;
      fault_database) fault_action="database_reconnect" ;;
    esac
    AICRM_QUEUE_FAULT_DRILL_AUTHORIZED=1 python3 scripts/ops/run_queue_runtime_fault_drill.py \
      --action "$fault_action" \
      "${common_identity[@]}" \
      --apply \
      --confirmation "RUN_QUEUE_FAULT_${fault_action^^}_${expected_release_sha}_${queue_generation}"
    ;;
  rollback_test_loopback)
    test -n "$queue_target_policy_version" || fail "rollback target policy is required"
    AICRM_WECOM_CANARY_CONFIG_AUTHORIZED=1 python3 scripts/ops/configure_wecom_canary.py \
      --mode disable \
      --generation "$queue_generation" \
      --expected-policy-version "$queue_policy_version" \
      --actor "$actor" \
      --reason "$reason" \
      --apply \
      --confirmation "CONFIGURE_WECOM_CANARY_${queue_generation}_DISABLE"
    AICRM_QUEUE_SCOPE_TRANSITION_AUTHORIZED=1 python3 scripts/ops/transition_queue_runtime_scope.py \
      --generation "$queue_generation" \
      --expected-policy-version "$queue_policy_version" \
      --target-policy-version "$queue_target_policy_version" \
      --expected-scope allowlisted \
      --target-scope test_loopback \
      --actor "$actor" \
      --reason "$reason" \
      --apply \
      --confirmation "TRANSITION_QUEUE_SCOPE_${queue_generation}_ALLOWLISTED_TO_TEST_LOOPBACK"
    ;;
  soak_start)
    AICRM_QUEUE_SOAK_AUTHORIZED=1 python3 scripts/ops/manage_queue_runtime_soak.py \
      --action start \
      "${common_identity[@]}" \
      --confirmation "START_QUEUE_SOAK_${expected_release_sha}_${queue_generation}"
    ;;
  soak_status)
    python3 scripts/ops/manage_queue_runtime_soak.py --action status
    ;;
  soak_complete)
    AICRM_QUEUE_SOAK_AUTHORIZED=1 python3 scripts/ops/manage_queue_runtime_soak.py \
      --action complete \
      "${common_identity[@]}" \
      --confirmation "COMPLETE_QUEUE_SOAK_${expected_release_sha}_${queue_generation}"
    ;;
  soak_invalidate)
    AICRM_QUEUE_SOAK_AUTHORIZED=1 python3 scripts/ops/manage_queue_runtime_soak.py \
      --action invalidate \
      "${common_identity[@]}" \
      --confirmation "INVALIDATE_QUEUE_SOAK_${expected_release_sha}_${queue_generation}"
    ;;
esac
