#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
PORTFOLIO_START="${PORTFOLIO_START:-2026-06-01}"
UNIVERSE_SIZE="${UNIVERSE_SIZE:-180}"
MIN_TOP_N="${MIN_TOP_N:-1}"
MAX_TOP_N="${MAX_TOP_N:-8}"
PERIOD_MONTHS="${PERIOD_MONTHS:-24,18,12,6,3}"
EXPLAIN_QUERY="${EXPLAIN_QUERY:-001820}"
STATUS_FILE="dashboard/ai_win_rebuild_status.json"
VALIDATION_FILE="dashboard/ai_win_validation_latest.json"

mkdir -p dashboard

write_status() {
  local status="$1"
  local step="$2"
  local detail="${3:-}"
  "$PYTHON_BIN" - "$status" "$step" "$detail" <<'PY' || true
import json
import sys
from datetime import datetime
from pathlib import Path
status, step, detail = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {
    "status": status,
    "step": step,
    "detail": detail,
    "updated_at": datetime.now().isoformat(timespec="seconds"),
}
Path("dashboard/ai_win_rebuild_status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

run_step() {
  local step="$1"
  shift
  write_status "running" "$step"
  echo "== $step =="
  "$@"
  echo
}

if [ ! -x "$PYTHON_BIN" ]; then
  echo "python_not_found: $PYTHON_BIN" >&2
  exit 2
fi

trap 'write_status "failed" "${CURRENT_STEP:-unknown}" "line=$LINENO"' ERR

CURRENT_STEP="Optimize AI WIN strategy"
run_step "$CURRENT_STEP" "$PYTHON_BIN" scripts/optimize_ai_win_count_and_portfolio.py \
  --portfolio-start "$PORTFOLIO_START" \
  --universe-size "$UNIVERSE_SIZE" \
  --min-top-n "$MIN_TOP_N" \
  --max-top-n "$MAX_TOP_N" \
  --period-months "$PERIOD_MONTHS"

CURRENT_STEP="Rebuild dashboard outputs"
run_step "$CURRENT_STEP" "$PYTHON_BIN" scripts/rebuild_daily_ai_win_dashboard.py \
  --portfolio-start "$PORTFOLIO_START" \
  --universe-size "$UNIVERSE_SIZE"

CURRENT_STEP="Validate dashboard outputs"
write_status "running" "$CURRENT_STEP"
echo "== $CURRENT_STEP =="
"$PYTHON_BIN" scripts/validate_ai_win_outputs.py --portfolio-start "$PORTFOLIO_START" | tee "$VALIDATION_FILE"
echo

CURRENT_STEP="Explain recommendation: $EXPLAIN_QUERY"
echo "== $CURRENT_STEP =="
"$PYTHON_BIN" scripts/explain_recommendation.py "$EXPLAIN_QUERY" || true
echo

CURRENT_STEP="Key files"
echo "== $CURRENT_STEP =="
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
for path in ["dashboard/adaptive_strategy.json", "dashboard/portfolio_status.json", "dashboard/recommendation_history.json", "dashboard/ai_win_validation_latest.json"]:
    p = Path(path)
    print(f"{path}: exists={p.exists()} size={p.stat().st_size if p.exists() else 0}")

strategy = json.loads(Path("dashboard/adaptive_strategy.json").read_text(encoding="utf-8"))
portfolio = json.loads(Path("dashboard/portfolio_status.json").read_text(encoding="utf-8"))
print("selected_top_n:", strategy.get("selected_top_n"))
print("best_summary:", strategy.get("best_summary"))
print("portfolio_summary:", portfolio.get("summary"))
print("equity_curve_window:", portfolio.get("equity_curve_window"))
PY

write_status "complete" "done" "validation=$VALIDATION_FILE"
