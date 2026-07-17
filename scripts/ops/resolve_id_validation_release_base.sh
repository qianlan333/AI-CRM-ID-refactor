#!/usr/bin/env bash
set -e
set -o pipefail

canonical_path="${1:-/home/ubuntu/.aicrm-releases/id-validation.json}"
repository_path="${2:-/home/ubuntu/极简 crm}"
readonly expected_repository="${EXPECTED_REPOSITORY:-}"
readonly deploy_target="${DEPLOY_TARGET:-}"
readonly public_health_url="${PUBLIC_HEALTH_URL:-}"

if [ "$expected_repository" != "qianlan333/AI-CRM-ID-refactor" ]; then
  echo "canonical base resolver refuses an unexpected repository" >&2
  exit 1
fi
if [ "$deploy_target" != "id-validation" ]; then
  echo "canonical base resolver refuses an unexpected deploy target" >&2
  exit 1
fi
if [ "$public_health_url" != "https://id-dev.youcangogogo.com/health" ]; then
  echo "canonical base resolver refuses an unexpected public health URL" >&2
  exit 1
fi
if [ -L "$canonical_path" ] || [ ! -f "$canonical_path" ]; then
  echo "canonical ID validation provenance is missing or is a symlink" >&2
  exit 1
fi
if [ -L "$(dirname "$canonical_path")" ]; then
  echo "canonical provenance directory must not be a symlink" >&2
  exit 1
fi
if [ -L "$repository_path" ] || [ ! -d "$repository_path/.git" ]; then
  echo "ID validation repository checkout is missing" >&2
  exit 1
fi

deploy_lock_file="/tmp/aicrm-deploy-${deploy_target}.lock"
exec 9>"$deploy_lock_file"
if ! flock -n 9; then
  echo "another ID validation deployment holds $deploy_lock_file" >&2
  exit 1
fi

stat_mode() {
  if stat -c '%a' "$1" >/dev/null 2>&1; then
    stat -c '%a' "$1"
  else
    stat -f '%Lp' "$1"
  fi
}

stat_uid() {
  if stat -c '%u' "$1" >/dev/null 2>&1; then
    stat -c '%u' "$1"
  else
    stat -f '%u' "$1"
  fi
}

strict_sha_file() {
  python3 - "$1" <<'PY'
import re
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_bytes()
if raw.endswith(b"\r\n"):
    raw = raw[:-2]
elif raw.endswith(b"\n"):
    raw = raw[:-1]
if re.fullmatch(rb"[0-9a-f]{40}", raw) is None:
    raise SystemExit("release marker is not exactly one SHA")
print(raw.decode("ascii"))
PY
}

canonical_directory="$(dirname "$canonical_path")"
if [ "$(stat_mode "$canonical_directory")" != "750" ]; then
  echo "canonical provenance directory mode must be 0750" >&2
  exit 1
fi
if [ "$(stat_mode "$canonical_path")" != "640" ]; then
  echo "canonical provenance file mode must be 0640" >&2
  exit 1
fi
if [ "$(stat_uid "$canonical_directory")" != "$(id -u)" ] || \
   [ "$(stat_uid "$canonical_path")" != "$(id -u)" ]; then
  echo "canonical provenance must be owned by the deploy user" >&2
  exit 1
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
    echo "canonical base resolver refuses a non-ID repository checkout" >&2
    exit 1
    ;;
esac

if [ -L .release-sha ] || [ ! -f .release-sha ]; then
  echo "server release marker is missing or is a symlink" >&2
  exit 1
fi
if [ -e "$canonical_directory/id-validation.pending.json" ] || \
   [ -e "$canonical_directory/id-validation.prepared.json" ]; then
  echo "ambiguous pending or prepared provenance blocks guarded base recovery" >&2
  exit 1
fi
if [ -n "$(git status --porcelain=v1 --untracked-files=all)" ]; then
  echo "guarded base recovery refuses a dirty server checkout" >&2
  exit 1
fi

canonical_chain="$(python3 - "$canonical_path" "$expected_repository" "$public_health_url" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_repository = sys.argv[2]
expected_health_url = sys.argv[3]
payload = json.loads(path.read_text(encoding="utf-8"))

required_exact = {
    "repository": expected_repository,
    "environment": "id-validation",
    "public_health_url": expected_health_url,
}
for key, expected in required_exact.items():
    if payload.get(key) != expected:
        raise SystemExit(f"canonical provenance {key} mismatch")

release_sha = str(payload.get("release_sha") or "")
base_sha = str(payload.get("base_sha") or "")
bundle_sha256 = str(payload.get("bundle_sha256") or "")
if re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
    raise SystemExit("canonical provenance release_sha is invalid")
if re.fullmatch(r"[0-9a-f]{40}", base_sha) is None:
    raise SystemExit("canonical provenance base_sha is invalid")
if re.fullmatch(r"[0-9a-f]{64}", bundle_sha256) is None:
    raise SystemExit("canonical provenance bundle_sha256 is invalid")
for key in ("source_ci_run_id", "deploy_run_id", "deploy_run_attempt"):
    if re.fullmatch(r"[1-9][0-9]*", str(payload.get(key) or "")) is None:
        raise SystemExit(f"canonical provenance {key} is invalid")

print(release_sha, base_sha)
PY
)"
read -r release_sha canonical_base_sha unexpected_chain_field <<< "$canonical_chain"

if ! printf '%s' "$release_sha" | grep -Eq '^[0-9a-f]{40}$' || \
   ! printf '%s' "$canonical_base_sha" | grep -Eq '^[0-9a-f]{40}$' || \
   [ -n "$unexpected_chain_field" ]; then
  echo "canonical provenance did not resolve one release/base chain" >&2
  exit 1
fi
if ! git cat-file -e "$release_sha^{commit}"; then
  echo "canonical release SHA is not present in the server repository" >&2
  exit 1
fi
if ! git cat-file -e "$canonical_base_sha^{commit}"; then
  echo "canonical base SHA is not present in the server repository" >&2
  exit 1
fi
if ! git merge-base --is-ancestor "$canonical_base_sha" "$release_sha"; then
  echo "canonical base is not an ancestor of the canonical release" >&2
  exit 1
fi

current_sha="$(git rev-parse HEAD)"
release_marker_sha="$(strict_sha_file .release-sha)"
if ! printf '%s' "$current_sha" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "server checkout does not resolve to one full SHA" >&2
  exit 1
fi
if [ "$release_marker_sha" != "$current_sha" ]; then
  echo "server release marker does not match the guarded checkout" >&2
  exit 1
fi
if ! git merge-base --is-ancestor "$release_sha" "$current_sha"; then
  echo "guarded checkout is not descended from canonical provenance" >&2
  exit 1
fi

printf 'AICRM_ATTESTED_RELEASE_SHA=%s\n' "$current_sha"
