#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"
PORTFOLIO_START="${PORTFOLIO_START:-2026-06-01}"
EXPLAIN_QUERY="${EXPLAIN_QUERY:-001820}"

ok() { printf 'OK   %s\n' "$1"; }
warn() { printf 'WARN %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; }

printf '\n== AI WIN short status ==\n'

if [ -d "$APP_DIR" ]; then
  ok "app directory: $APP_DIR"
else
  fail "app directory missing: $APP_DIR"
  exit 0
fi

if [ -x "$PYTHON" ]; then
  ok "python present: $PYTHON"
else
  fail "python missing: $PYTHON"
fi

if systemctl list-unit-files agents-invest-daily-ai-win.timer >/dev/null 2>&1; then
  if systemctl is-enabled --quiet agents-invest-daily-ai-win.timer 2>/dev/null; then
    ok "daily AI WIN timer enabled"
  else
    warn "daily AI WIN timer installed but not enabled"
  fi
  if systemctl is-active --quiet agents-invest-daily-ai-win.timer 2>/dev/null; then
    ok "daily AI WIN timer active"
  else
    warn "daily AI WIN timer not active"
  fi
  next_run="$(systemctl list-timers agents-invest-daily-ai-win.timer --no-pager --no-legend 2>/dev/null | awk '{print $1" "$2" "$3" "$4}' || true)"
  if [ -n "$next_run" ]; then
    ok "daily AI WIN next run: $next_run"
  fi
else
  warn "daily AI WIN timer not installed"
fi

if [ -f "$APP_DIR/dashboard/ai_win_rebuild_status.json" ]; then
  APP_DIR="$APP_DIR" "$PYTHON" - <<'PY' 2>/dev/null || true
import json
import os
from pathlib import Path
p = Path(os.environ['APP_DIR']) / 'dashboard' / 'ai_win_rebuild_status.json'
data = json.loads(p.read_text(encoding='utf-8'))
status = data.get('status')
line = f"AI WIN last rebuild: status={status}, step={data.get('step')}, updated={data.get('updated_at')}"
if status == 'complete':
    print(f"OK   {line}")
elif status == 'failed':
    print(f"FAIL {line}, detail={data.get('detail')}")
else:
    print(f"WARN {line}")
PY
else
  warn "AI WIN rebuild status file missing"
fi

if [ -f "$APP_DIR/dashboard/adaptive_strategy.json" ]; then
  APP_DIR="$APP_DIR" "$PYTHON" - <<'PY' 2>/dev/null || true
import json
import os
from pathlib import Path
p = Path(os.environ['APP_DIR']) / 'dashboard' / 'adaptive_strategy.json'
data = json.loads(p.read_text(encoding='utf-8'))
print(f"OK   strategy source: {data.get('source')}")
print(f"OK   selected top_n: {data.get('selected_top_n')}, period_months: {data.get('selected_period_months')}")
print(f"OK   best summary: {data.get('best_summary')}")
PY
else
  warn "adaptive_strategy.json missing"
fi

if [ -f "$APP_DIR/dashboard/portfolio_status.json" ]; then
  APP_DIR="$APP_DIR" "$PYTHON" - <<'PY' 2>/dev/null || true
import json
import os
from pathlib import Path
p = Path(os.environ['APP_DIR']) / 'dashboard' / 'portfolio_status.json'
data = json.loads(p.read_text(encoding='utf-8'))
summary = data.get('summary', {})
print(f"OK   portfolio: {data.get('start_date')} ~ {data.get('end_date')}, source={data.get('price_source')}")
print(f"OK   portfolio summary: return={summary.get('total_return_pct')}, annualized={summary.get('annualized_return_pct')}, holdings={summary.get('open_positions')}, sells={summary.get('sell_signal_count')}")
curve = data.get('equity_curve') or []
if curve:
    print(f"OK   equity curve: rows={len(curve)}, first={curve[0].get('date')}, last={curve[-1].get('date')}, window={data.get('equity_curve_window')}")
PY
else
  warn "portfolio_status.json missing"
fi

if [ -f "$APP_DIR/dashboard/ai_win_validation_latest.json" ]; then
  APP_DIR="$APP_DIR" "$PYTHON" - <<'PY' 2>/dev/null || true
import json
import os
from pathlib import Path
p = Path(os.environ['APP_DIR']) / 'dashboard' / 'ai_win_validation_latest.json'
data = json.loads(p.read_text(encoding='utf-8'))
if data.get('ok'):
    print("OK   saved AI WIN validation: ok=true")
else:
    print(f"FAIL saved AI WIN validation: issues={data.get('issues')}")
PY
else
  warn "saved AI WIN validation file missing"
fi

if [ -x "$PYTHON" ] && [ -f "$APP_DIR/scripts/validate_ai_win_outputs.py" ]; then
  if "$PYTHON" "$APP_DIR/scripts/validate_ai_win_outputs.py" --portfolio-start "$PORTFOLIO_START" >/tmp/agents_invest_ai_win_validate.$$ 2>&1; then
    ok "AI WIN output validation passed"
  else
    fail "AI WIN output validation failed"
    cat /tmp/agents_invest_ai_win_validate.$$
  fi
  rm -f /tmp/agents_invest_ai_win_validate.$$
fi

if [ -x "$PYTHON" ] && [ -f "$APP_DIR/scripts/explain_recommendation.py" ]; then
  if "$PYTHON" "$APP_DIR/scripts/explain_recommendation.py" "$EXPLAIN_QUERY" >/tmp/agents_invest_ai_win_explain.$$ 2>&1; then
    ok "recommendation explanation available for $EXPLAIN_QUERY"
    cat /tmp/agents_invest_ai_win_explain.$$
  else
    warn "recommendation explanation not found for $EXPLAIN_QUERY"
    cat /tmp/agents_invest_ai_win_explain.$$ || true
  fi
  rm -f /tmp/agents_invest_ai_win_explain.$$
fi
