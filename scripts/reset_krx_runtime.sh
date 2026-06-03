#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"

printf '== reset KRX/runtime session ==\n'

sudo systemctl stop agents-invest 2>/dev/null || true
sudo systemctl stop agents-invest-adaptive-strategy.service 2>/dev/null || true

sudo pkill -f 'trigger_batch.py' 2>/dev/null || true
sudo pkill -f 'agents_invest_runner' 2>/dev/null || true
sudo pkill -f 'optimize_adaptive_strategy.py' 2>/dev/null || true
sudo pkill -f 'chrome-headless-shell' 2>/dev/null || true
sudo pkill -f 'playwright' 2>/dev/null || true

rm -f /tmp/agents_invest_krx.lock 2>/dev/null || true
rm -rf /tmp/playwright_chromiumdev_profile-* 2>/dev/null || true
rm -rf /tmp/.org.chromium.Chromium.* 2>/dev/null || true

sleep 15

cd "$APP_DIR"
if [ -x "$APP_DIR/.venv/bin/python" ]; then
  "$APP_DIR/.venv/bin/python" scripts/update_portfolio_status.py --start-date "${PORTFOLIO_START_DATE:-2026-06-01}" >/dev/null 2>&1 || true
fi

sudo systemctl restart agents-invest
sleep 20
bash scripts/operator_status.sh
