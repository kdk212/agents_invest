#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
DASHBOARD_PORT="${DASHBOARD_PORT:-80}"

section() {
  printf '\n== %s ==\n' "$1"
}

run_check() {
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

section "EC2 identity"
public_ip="$(metadata_value public-ipv4)"
instance_id="$(metadata_value instance-id)"
region="$(metadata_value placement/region)"
echo "instance_id=${instance_id:-unknown}"
echo "public_ip=${public_ip:-unknown}"
echo "region=${region:-unknown}"
if [ -n "$public_ip" ]; then
  if [ "$DASHBOARD_PORT" = "80" ]; then
    echo "dashboard_url=http://$public_ip/"
  else
    echo "dashboard_url=http://$public_ip:$DASHBOARD_PORT/"
  fi
fi

section "Application directory"
if [ -d "$APP_DIR" ]; then
  echo "found: $APP_DIR"
  run_check "git branch" git -C "$APP_DIR" rev-parse --abbrev-ref HEAD
  run_check "git commit" git -C "$APP_DIR" rev-parse --short HEAD
  if [ -d "$APP_DIR/prism-insight" ]; then
    echo "prism_integration=present"
  else
    echo "prism_integration=missing"
  fi
else
  echo "missing: $APP_DIR"
  echo "cloud-init log may explain clone/bootstrap failure: sudo tail -200 /var/log/cloud-init-output.log"
fi

section "Python and preflight"
if [ -x "$APP_DIR/.venv/bin/python" ]; then
  run_check "python version" "$APP_DIR/.venv/bin/python" --version
  run_check "runtime preflight" "$APP_DIR/.venv/bin/python" -m runtime.preflight --json
  run_check "dashboard status export" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/export_dashboard_status.py" --output "$APP_DIR/dashboard/status.json"
else
  echo "missing virtualenv python: $APP_DIR/.venv/bin/python"
fi

section "Services"
run_check "agents-invest service" systemctl status agents-invest --no-pager
run_check "nginx service" systemctl status nginx --no-pager

section "HTTP checks"
run_check "local dashboard http" curl -I --connect-timeout 5 "http://127.0.0.1:$DASHBOARD_PORT/"
if [ -n "$public_ip" ]; then
  run_check "public dashboard http from instance" curl -I --connect-timeout 5 "http://$public_ip:$DASHBOARD_PORT/"
fi

section "Ports"
if command -v ss >/dev/null 2>&1; then
  run_check "listening ports" ss -ltnp
else
  run_check "listening ports" netstat -ltnp
fi

section "Recent logs"
run_check "agents-invest recent logs" journalctl -u agents-invest -n 40 --no-pager
run_check "nginx recent logs" journalctl -u nginx -n 40 --no-pager
if [ -f /var/log/cloud-init-output.log ]; then
  run_check "cloud-init tail" tail -80 /var/log/cloud-init-output.log
fi

section "Next hint"
echo "If local dashboard works but browser cannot open it, check EC2 Security Group inbound HTTP $DASHBOARD_PORT from your current IP."
echo "If $APP_DIR is missing, private repo clone likely failed. Recreate stack with GitHubToken or clone manually on EC2."
