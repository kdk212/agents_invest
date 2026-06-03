#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"

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

printf '\n== GitHub workflow trigger status ==\n'
if [ -x "$PYTHON" ] && [ -f "$APP_DIR/scripts/check_workflow_triggers.py" ]; then
  if "$PYTHON" "$APP_DIR/scripts/check_workflow_triggers.py" --json >/tmp/agents_invest_workflow_triggers.$$ 2>&1; then
    echo "OK   workflows are manual-only"
    cat /tmp/agents_invest_workflow_triggers.$$
  else
    echo "FAIL workflow trigger check failed"
    cat /tmp/agents_invest_workflow_triggers.$$
  fi
  rm -f /tmp/agents_invest_workflow_triggers.$$
else
  echo "WARN workflow trigger checker missing; run git pull first"
fi
