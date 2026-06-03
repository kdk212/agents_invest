#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
PYTHON="$APP_DIR/.venv/bin/python"

cat >/etc/systemd/system/agents-invest-daily-ai-win.service <<SERVICE
[Unit]
Description=agents_invest daily AI WIN optimization, rebuild, and Telegram summary
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/config/runtime.env
ExecStart=$PYTHON $APP_DIR/scripts/optimize_ai_win_count_and_portfolio.py --portfolio-start 2026-06-01 --universe-size 180 --min-top-n 1 --max-top-n 8 --period-months 24,18,12,6,3
ExecStart=$PYTHON $APP_DIR/scripts/rebuild_daily_ai_win_dashboard.py --portfolio-start 2026-06-01 --universe-size 180
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
