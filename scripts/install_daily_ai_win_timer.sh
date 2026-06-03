#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
PYTHON="$APP_DIR/.venv/bin/python"

cat >/etc/systemd/system/agents-invest-daily-ai-win.service <<SERVICE
[Unit]
Description=agents_invest daily AI WIN optimization, validation, and Telegram summary
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/config/runtime.env
Environment=PYTHON_BIN=$PYTHON
Environment=PORTFOLIO_START=2026-06-01
Environment=UNIVERSE_SIZE=180
Environment=MIN_TOP_N=1
Environment=MAX_TOP_N=8
Environment=PERIOD_MONTHS=24,18,12,6,3
Environment=EXPLAIN_QUERY=001820
ExecStart=/bin/bash $APP_DIR/scripts/run_ai_win_rebuild_and_validate.sh
ExecStart=$PYTHON $APP_DIR/scripts/send_dashboard_telegram.py
SERVICE

cat >/etc/systemd/system/agents-invest-daily-ai-win.timer <<'TIMER'
[Unit]
Description=Run agents_invest daily AI WIN workflow

[Timer]
OnCalendar=Mon..Fri *-*-* 08:45:00
OnCalendar=Mon..Fri *-*-* 15:35:00
Persistent=true
Unit=agents-invest-daily-ai-win.service

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now agents-invest-daily-ai-win.timer
systemctl list-timers agents-invest-daily-ai-win.timer --no-pager
