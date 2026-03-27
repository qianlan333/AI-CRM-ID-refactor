#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"
VERIFY_DIR="${VERIFY_DIR:-$SCRIPT_DIR/.verify}"
VERIFY_HOST="${VERIFY_HOST:-127.0.0.1}"
VERIFY_PORT="${VERIFY_PORT:-18081}"
VERIFY_LOG="$VERIFY_DIR/verify.log"

mkdir -p "$VERIFY_DIR"

if [ -f "${ENV_FILE:-$SCRIPT_DIR/.env}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE:-$SCRIPT_DIR/.env}"
  set +a
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$SCRIPT_DIR/install.sh"
fi

: "${CRM_MCP_URL:?CRM_MCP_URL is required}"
: "${MCP_BEARER_TOKEN:?MCP_BEARER_TOKEN is required}"

export APP_HOST="$VERIFY_HOST"
export APP_PORT="$VERIFY_PORT"
export CRM_MCP_TIMEOUT_SECONDS="${CRM_MCP_TIMEOUT_SECONDS:-10}"

"$VENV_DIR/bin/python" -c "from openclaw_crm_proxy_server import create_app; create_app(); print('import ok')"

"$VENV_DIR/bin/python" "$SCRIPT_DIR/openclaw_crm_proxy_server.py" >"$VERIFY_LOG" 2>&1 &
SERVER_PID=$!
cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl -fsS "http://$VERIFY_HOST:$VERIFY_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "http://$VERIFY_HOST:$VERIFY_PORT/health" >/dev/null

TOOLS_JSON="$(
  curl -fsS \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
    "http://$VERIFY_HOST:$VERIFY_PORT/mcp"
)"

echo "$TOOLS_JSON" | "$VENV_DIR/bin/python" -c '
import json, sys
payload = json.load(sys.stdin)
tools = [item["name"] for item in payload["result"]["tools"]]
required = {
    "resolve_customer",
    "get_customer_context",
    "update_customer_tags",
    "create_private_message_task",
    "create_group_message_task",
    "create_moment_task",
    "get_owner_recent_chat_dump",
}
missing = sorted(required - set(tools))
if missing:
    raise SystemExit("missing tools: " + ",".join(missing))
print("verify ok")
'

echo "Verify complete."
