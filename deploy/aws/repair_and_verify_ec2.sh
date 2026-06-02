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

run_as_app_user() {
  if [ "$(id -u)" -eq 0 ]; then
    sudo -u "$APP_USER" "$@"
  else
    "$@"
  fi
}

run_app_python() {
  if [ "$(id -u)" -eq 0 ]; then
    sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' '$APP_DIR/.venv/bin/python' $*"
  else
    bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' '$APP_DIR/.venv/bin/python' $*"
  fi
}

if [ ! -d "$APP_DIR" ]; then
  echo "Application directory not found: $APP_DIR" >&2
  echo "Run bootstrap first, or check that you are inside the EC2 instance rather than CloudShell." >&2
  exit 2
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  APP_USER="ssm-user"
fi

cd "$APP_DIR"

step "Fix application ownership before update"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR" || true

step "Pull latest agents_invest"
run_as_app_user git -C "$APP_DIR" pull --ff-only

step "Import or refresh PRISM runtime"
sudo APP_DIR="$APP_DIR" APP_USER="$APP_USER" bash deploy/aws/import_prism_runtime.sh

step "Install or repair agents-invest service"
sudo APP_DIR="$APP_DIR" APP_USER="$APP_USER" AWS_REGION="$AWS_REGION" bash deploy/aws/install_agents_service_amazon_linux.sh

step "Run local tests"
run_optional "pytest" run_app_python -m pytest -q tests

step "Run startup preflight"
run_optional "install preflight" run_app_python -m runtime.preflight --json --allow-missing-secrets
run_optional "strict runtime preflight" run_app_python -m runtime.preflight --json

step "Check Telegram alert"
run_optional "telegram smoke test" run_app_python scripts/test_telegram_alert.py --json

if [ "$RUN_PRISM_ONCE" = "true" ]; then
  step "Run one PRISM batch cycle"
  run_optional "one PRISM batch cycle" run_app_python -m agents_invest_runner --run-batch-once
fi

step "Restart service"
run_optional "restart agents-invest" sudo systemctl restart agents-invest
run_optional "agents-invest status" sudo systemctl status agents-invest --no-pager

step "Run EC2 diagnosis"
run_optional "diagnose EC2 runtime" bash scripts/diagnose_ec2_runtime.sh

cat <<EOF

Repair and verification complete.

Dashboard:
  http://13.55.135.136/

If Telegram test failed with telegram_secret_missing, run:
  cd $APP_DIR
  .venv/bin/python scripts/configure_runtime_secrets.py --target ssm --region $AWS_REGION

If strict runtime preflight failed only because secrets are missing, enter the secrets above and run this repair command again.
EOF