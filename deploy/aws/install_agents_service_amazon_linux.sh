#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
APP_USER="${APP_USER:-ec2-user}"
AWS_REGION="${AWS_REGION:-ap-southeast-2}"
RUNTIME_MODE="${RUNTIME_MODE:-paper}"
ENABLE_SSM_SETTINGS="${ENABLE_SSM_SETTINGS:-true}"
SSM_PARAMETER_PREFIX="${SSM_PARAMETER_PREFIX:-/agents-invest}"
DASHBOARD_PUBLIC_URL="${DASHBOARD_PUBLIC_URL:-}"

step() {
  printf '\n==> %s\n' "$1"
}

metadata_value() {
  local path="$1"
  local token=""
  token="$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)"
  if [ -n "$token" ]; then
    curl -fsS -H "X-aws-ec2-metadata-token: $token" "http://169.254.169.254/latest/meta-data/$path" 2>/dev/null || true
  else
    curl -fsS "http://169.254.169.254/latest/meta-data/$path" 2>/dev/null || true
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"
  if grep -q "^$key=" "$file"; then
    sed -i "s#^$key=.*#$key=$value#" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/aws/install_agents_service_amazon_linux.sh" >&2
  exit 2
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  APP_USER="ssm-user"
fi

if [ ! -d "$APP_DIR" ]; then
  echo "Application directory not found: $APP_DIR" >&2
  exit 2
fi

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  echo "Virtualenv python not found: $APP_DIR/.venv/bin/python" >&2
  echo "Run bootstrap first: sudo bash deploy/aws/bootstrap_ec2_amazon_linux.sh" >&2
  exit 2
fi

step "Fix application ownership"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
mkdir -p "$APP_DIR/dashboard"
touch "$APP_DIR/dashboard/status.json"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/dashboard"

step "Ensure runtime env"
mkdir -p "$APP_DIR/config"
if [ ! -f "$APP_DIR/config/runtime.env" ]; then
  cp "$APP_DIR/config/runtime.example.env" "$APP_DIR/config/runtime.env"
fi
if [ -z "$DASHBOARD_PUBLIC_URL" ]; then
  public_ip="$(metadata_value public-ipv4)"
  if [ -n "$public_ip" ]; then
    DASHBOARD_PUBLIC_URL="http://$public_ip/"
  fi
fi
set_env_value AWS_REGION "$AWS_REGION" "$APP_DIR/config/runtime.env"
set_env_value APP_ENV "$RUNTIME_MODE" "$APP_DIR/config/runtime.env"
set_env_value TRADING_MODE "$RUNTIME_MODE" "$APP_DIR/config/runtime.env"
set_env_value ENABLE_SSM_SETTINGS "$ENABLE_SSM_SETTINGS" "$APP_DIR/config/runtime.env"
set_env_value SSM_PARAMETER_PREFIX "$SSM_PARAMETER_PREFIX" "$APP_DIR/config/runtime.env"
if [ -n "$DASHBOARD_PUBLIC_URL" ]; then
  set_env_value DASHBOARD_PUBLIC_URL "$DASHBOARD_PUBLIC_URL" "$APP_DIR/config/runtime.env"
fi
chown "$APP_USER:$APP_USER" "$APP_DIR/config/runtime.env"
chmod 600 "$APP_DIR/config/runtime.env"

step "Install agents-invest systemd service"
cp "$APP_DIR/deploy/systemd/agents-invest.service.example" /etc/systemd/system/agents-invest.service
sed -i "s#^User=.*#User=$APP_USER#" /etc/systemd/system/agents-invest.service
sed -i "s#^WorkingDirectory=.*#WorkingDirectory=$APP_DIR#" /etc/systemd/system/agents-invest.service
sed -i "s#^EnvironmentFile=.*#EnvironmentFile=$APP_DIR/config/runtime.env#" /etc/systemd/system/agents-invest.service
sed -i "s#^ExecStart=.*#ExecStart=$APP_DIR/.venv/bin/python -m agents_invest_runner#" /etc/systemd/system/agents-invest.service

systemctl daemon-reload
systemctl enable agents-invest.service

step "Refresh dashboard status"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json"

step "Start service"
systemctl restart agents-invest.service
systemctl status agents-invest.service --no-pager || true

cat <<EOF

agents-invest service installed for Amazon Linux.

Dashboard URL:
  ${DASHBOARD_PUBLIC_URL:-not detected}

Next checks:
  systemctl status agents-invest --no-pager
  bash $APP_DIR/scripts/diagnose_ec2_runtime.sh
EOF