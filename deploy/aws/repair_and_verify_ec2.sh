#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
APP_USER="${APP_USER:-ssm-user}"
AWS_REGION="${AWS_REGION:-ap-southeast-2}"
RUN_PRISM_ONCE="${RUN_PRISM_ONCE:-false}"

step() {
  printf '\n==> %s\n' "$1"
}

run_optional() {
  local label="$1"
  shift
  printf '\n-- %s --\n' "$label"
  if "$@"; then
    return 0
  fi
  local code=$?
  echo "failed: $label (exit=$code)"
  return 0
}

if [ ! -d "$APP_DIR" ]; then
  echo "Application directory not found: $APP_DIR" >&2
  echo "Run bootstrap first, or check that you are inside the EC2 instance rather than CloudShell." >&2
  exit 2
fi

cd "$APP_DIR"

step "Pull latest agents_invest"
if [ "$(id -u)" -eq 0 ]; then
  git pull --ff-only
else
  sudo git pull --ff-only || git pull --ff-only
fi

step "Import or refresh PRISM runtime"
sudo APP_DIR="$APP_DIR" APP_USER="$APP_USER" bash deploy/aws/import_prism_runtime.sh

step "Install or repair agents-invest service"
sudo APP_DIR="$APP_DIR" APP_USER="$APP_USER" AWS_REGION="$AWS_REGION" bash deploy/aws/install_agents_service_amazon_linux.sh

step "Run local tests"
PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -m pytest -q tests

step "Run startup preflight"
PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -m runtime.preflight --json

step "Check Telegram alert"
run_optional "telegram smoke test" "$APP_DIR/.venv/bin/python" scripts/test_telegram_alert.py --json

if [ "$RUN_PRISM_ONCE" = "true" ]; then
  step "Run one PRISM batch cycle"
  PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -m agents_invest_runner --run-batch-once
fi

step "Restart service"
sudo systemctl restart agents-invest
sudo systemctl status agents-invest --no-pager || true

step "Run EC2 diagnosis"
bash scripts/diagnose_ec2_runtime.sh

cat <<EOF

Repair and verification complete.

Dashboard:
  http://13.55.135.136/

If Telegram test failed with telegram_secret_missing, run:
  cd $APP_DIR
  .venv/bin/python scripts/configure_runtime_secrets.py --target ssm --region $AWS_REGION
EOF