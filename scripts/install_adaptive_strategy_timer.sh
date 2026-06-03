#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
SERVICE_FILE="/etc/systemd/system/agents-invest-adaptive-strategy.service"
TIMER_FILE="/etc/systemd/system/agents-invest-adaptive-strategy.timer"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "FAIL virtualenv python missing: $PYTHON_BIN" >&2
  exit 2
fi

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=agents_invest weekly adaptive strategy optimizer
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
Environment=PYTHONPATH=$APP_DIR:$APP_DIR/prism-insight
ExecStart=$PYTHON_BIN $APP_DIR/scripts/optimize_adaptive_strategy.py --periods 24,18,12 --top-n 7 --universe-size 160
User=root
EOF

sudo tee "$TIMER_FILE" >/dev/null <<EOF
[Unit]
Description=Run agents_invest adaptive strategy optimizer weekly

[Timer]
OnCalendar=Asia/Seoul Sun 21:20:00
Persistent=true
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now agents-invest-adaptive-strategy.timer
sudo systemctl list-timers agents-invest-adaptive-strategy.timer --no-pager
