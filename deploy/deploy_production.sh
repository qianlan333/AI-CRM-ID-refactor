#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/极简 crm}"
VENV_DIR="${VENV_DIR:-/home/ubuntu/venvs/openclaw}"
SERVICE_NAME="${SERVICE_NAME:-openclaw-wecom-postgres.service}"
ENV_FILE="${ENV_FILE:-/home/ubuntu/.openclaw-wecom-pg.env}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:5001/health}"
HEALTHCHECK_TIMEOUT="${HEALTHCHECK_TIMEOUT:-30}"
DEPLOY_SHA="${DEPLOY_SHA:-}"

if [ ! -d "$APP_DIR" ]; then
  echo "APP_DIR does not exist: $APP_DIR" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "VENV_DIR does not exist: $VENV_DIR" >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ENV_FILE does not exist: $ENV_FILE" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required on the production server" >&2
  exit 1
fi

systemctl_bin="$(command -v systemctl || true)"
if [ -z "$systemctl_bin" ]; then
  echo "systemctl is required on the production server" >&2
  exit 1
fi

cd "$APP_DIR"

if [ -n "$DEPLOY_SHA" ]; then
  printf '%s\n' "$DEPLOY_SHA" > .release-sha
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python3 -m pip install --disable-pip-version-check -r requirements.txt
python app.py init-db

sudo -n "$systemctl_bin" restart "$SERVICE_NAME"
sudo -n "$systemctl_bin" is-active --quiet "$SERVICE_NAME"

for _ in $(seq 1 "$HEALTHCHECK_TIMEOUT"); do
  if health_payload="$(curl -fsS "$HEALTHCHECK_URL")"; then
    printf '%s\n' "$health_payload"
    exit 0
  fi
  sleep 1
done

sudo -n "$systemctl_bin" status "$SERVICE_NAME" --no-pager || true
echo "Health check failed: $HEALTHCHECK_URL" >&2
exit 1
