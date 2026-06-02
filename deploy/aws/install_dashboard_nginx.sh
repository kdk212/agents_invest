#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
APP_USER="${APP_USER:-ubuntu}"
DASHBOARD_PORT="${DASHBOARD_PORT:-80}"

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

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/aws/install_dashboard_nginx.sh" >&2
  exit 2
fi

if [ ! -d "$APP_DIR/dashboard" ]; then
  echo "Dashboard directory not found: $APP_DIR/dashboard" >&2
  exit 2
fi

step "Install nginx"
apt-get update
apt-get install -y nginx

step "Export initial dashboard status"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/export_dashboard_status.py" \
  --output "$APP_DIR/dashboard/status.json"

step "Install nginx site"
cat >/etc/nginx/sites-available/agents-invest-dashboard <<EOF
server {
    listen $DASHBOARD_PORT;
    server_name _;
    root $APP_DIR/dashboard;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/agents-invest-dashboard /etc/nginx/sites-enabled/agents-invest-dashboard
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

step "Install 5-minute status refresh cron"
cat >/etc/cron.d/agents-invest-dashboard <<EOF
*/5 * * * * $APP_USER cd $APP_DIR && .venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json >/tmp/agents-invest-dashboard.log 2>&1
EOF
chmod 644 /etc/cron.d/agents-invest-dashboard

public_ip="$(metadata_value public-ipv4)"
if [ -n "$public_ip" ]; then
  if [ "$DASHBOARD_PORT" = "80" ]; then
    dashboard_url="http://$public_ip/"
  else
    dashboard_url="http://$public_ip:$DASHBOARD_PORT/"
  fi
else
  dashboard_url="http://EC2_PUBLIC_IP:$DASHBOARD_PORT/"
fi

cat <<EOF

Dashboard installed.

Open this URL after allowing port $DASHBOARD_PORT from your IP in the EC2 Security Group:
  $dashboard_url

Local server check:
  curl -I http://127.0.0.1:$DASHBOARD_PORT/
EOF