#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"

if [ -x "$APP_DIR/scripts/operator_status.sh" ] || [ -f "$APP_DIR/scripts/operator_status.sh" ]; then
  bash "$APP_DIR/scripts/operator_status.sh"
else
  echo "WARN operator_status.sh missing: $APP_DIR/scripts/operator_status.sh"
fi

if [ -x "$APP_DIR/scripts/operator_ai_win_status.sh" ] || [ -f "$APP_DIR/scripts/operator_ai_win_status.sh" ]; then
  bash "$APP_DIR/scripts/operator_ai_win_status.sh"
else
  echo "WARN operator_ai_win_status.sh missing: $APP_DIR/scripts/operator_ai_win_status.sh"
fi
