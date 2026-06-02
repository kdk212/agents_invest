#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
DASHBOARD_PORT="${DASHBOARD_PORT:-80}"

ok() { printf 'OK   %s\n' "$1"; }
warn() { printf 'WARN %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; }

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

json_field() {
  local file="$1"
  local field="$2"
  if command -v jq >/dev/null 2>&1 && [ -f "$file" ]; then
    jq -r "$field // empty" "$file" 2>/dev/null || true
  fi
}

python_json_field() {
  local command_text="$1"
  local field="$2"
  cd "$APP_DIR"
  OP_STATUS_CMD="$command_text" OP_STATUS_FIELD="$field" \
    PYTHONPATH="$APP_DIR:$APP_DIR/prism-insight" "$APP_DIR/.venv/bin/python" - <<'PY' 2>/dev/null || true
import json
import os
import subprocess

cmd = os.environ.get("OP_STATUS_CMD", "")
field = os.environ.get("OP_STATUS_FIELD", "")
try:
    out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=45)
    data = json.loads(out)
    value = data
    for part in field.split("."):
        if not part:
            continue
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break
    if isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False))
    elif value is not None:
        print(value)
except Exception:
    pass
PY
}

show_runtime_failure_details() {
  local file="$1"
  if [ ! -f "$file" ] || [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    return 0
  fi
  "$APP_DIR/.venv/bin/python" - "$file" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

status = data.get("status") or ""
last_result = data.get("last_result") if isinstance(data.get("last_result"), dict) else {}
results = last_result.get("results") if isinstance(last_result.get("results"), list) else []

if status and "failed" in status:
    print(f"WARN runtime failure detail: status={status}")

for item in results:
    if not isinstance(item, dict):
        continue
    try:
        returncode = int(item.get("returncode", 1))
    except Exception:
        returncode = 1
    if returncode == 0:
        continue
    mode = item.get("mode") or "unknown"
    print(f"WARN PRISM batch failed: mode={mode}, exit={returncode}")
    stderr = str(item.get("stderr_tail") or "").strip()
    stdout = str(item.get("stdout_tail") or "").strip()
    if stderr:
        print("---- PRISM stderr tail ----")
        print("\n".join(stderr.splitlines()[-20:]))
    if stdout:
        print("---- PRISM stdout tail ----")
        print("\n".join(stdout.splitlines()[-20:]))
PY
}

printf '\n== agents_invest short status ==\n'

public_ip="$(metadata_value public-ipv4)"
if [ -z "$public_ip" ]; then
  public_ip="13.55.135.136"
fi
printf 'dashboard_url=http://%s/\n' "$public_ip"

if [ -d "$APP_DIR" ]; then
  ok "app directory: $APP_DIR"
else
  fail "app directory missing: $APP_DIR"
  exit 0
fi

if git -C "$APP_DIR" rev-parse --short HEAD >/tmp/agents_invest_git_sha.$$ 2>/dev/null; then
  branch="$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  sha="$(cat /tmp/agents_invest_git_sha.$$)"
  rm -f /tmp/agents_invest_git_sha.$$
  ok "git: $branch@$sha"
else
  warn "git state unavailable"
fi

if [ -x "$APP_DIR/.venv/bin/python" ]; then
  version="$($APP_DIR/.venv/bin/python --version 2>&1)"
  if "$APP_DIR/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
  then
    ok "python: $version"
  else
    fail "python too old for PRISM: $version"
  fi
else
  fail "virtualenv missing: $APP_DIR/.venv/bin/python"
fi

if [ -d "$APP_DIR/prism-insight" ]; then
  ok "PRISM copy present"
else
  fail "PRISM copy missing"
fi

if [ -x "$APP_DIR/.venv/bin/python" ]; then
  prism_ready="$(python_json_field "PYTHONPATH='$APP_DIR:$APP_DIR/prism-insight' '$APP_DIR/.venv/bin/python' '$APP_DIR/scripts/check_prism_runtime_imports.py' --json" "ready")"
  if [ "$prism_ready" = "True" ] || [ "$prism_ready" = "true" ]; then
    ok "PRISM import smoke check: ready=true"
  else
    fail "PRISM import smoke check is not ready"
    cd "$APP_DIR"
    PYTHONPATH="$APP_DIR:$APP_DIR/prism-insight" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/check_prism_runtime_imports.py" --json 2>/dev/null || true
  fi
fi

if systemctl is-active --quiet agents-invest 2>/dev/null; then
  ok "agents-invest service active"
else
  warn "agents-invest service not active"
fi

if systemctl is-active --quiet nginx 2>/dev/null; then
  ok "nginx active"
else
  warn "nginx not active"
fi

if curl -fsSI --connect-timeout 5 "http://127.0.0.1:$DASHBOARD_PORT/" >/dev/null 2>&1; then
  ok "local dashboard HTTP works"
else
  fail "local dashboard HTTP not reachable"
fi

status_file="$APP_DIR/dashboard/status.json"
if [ -f "$status_file" ]; then
  updated="$(json_field "$status_file" '.updated_at')"
  overall="$(json_field "$status_file" '.overall')"
  mode="$(json_field "$status_file" '.trading_mode')"
  ok "dashboard status.json present: overall=${overall:-unknown}, mode=${mode:-unknown}, updated=${updated:-unknown}"
else
  warn "dashboard/status.json missing"
fi

runtime_file="$APP_DIR/dashboard/runtime_status.json"
if [ -f "$runtime_file" ]; then
  runtime_status="$(json_field "$runtime_file" '.status')"
  runtime_updated="$(json_field "$runtime_file" '.updated_at')"
  runtime_ready="$(json_field "$runtime_file" '.runtime_ready')"
  missing_count="$(json_field "$runtime_file" '.missing_secret_names | length')"
  if [ "$runtime_ready" = "true" ]; then
    ok "runtime heartbeat: ${runtime_status:-unknown}, updated=${runtime_updated:-unknown}"
  else
    warn "runtime heartbeat: ${runtime_status:-unknown}, missing_secrets=${missing_count:-unknown}, updated=${runtime_updated:-unknown}"
  fi
  show_runtime_failure_details "$runtime_file"
else
  warn "dashboard/runtime_status.json missing"
fi

latest_count=0
for file in "$APP_DIR"/dashboard/prism_latest_*.json; do
  if [ -f "$file" ]; then
    latest_count=$((latest_count + 1))
    mtime="$(date -r "$file" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
    ok "PRISM result file: $(basename "$file") updated=$mtime"
  fi
done
if [ "$latest_count" -eq 0 ]; then
  warn "no PRISM result file yet"
fi

if [ -x "$APP_DIR/.venv/bin/python" ]; then
  preflight_ok="$(python_json_field "PYTHONPATH='$APP_DIR' '$APP_DIR/.venv/bin/python' -m runtime.preflight --json --allow-missing-secrets" "install_ready")"
  if [ "$preflight_ok" = "True" ] || [ "$preflight_ok" = "true" ]; then
    ok "install preflight ready"
  else
    warn "install preflight not ready"
  fi
fi

printf '\nNext if something is FAIL: paste this short status output plus the FAIL line above.\n'
printf 'Dashboard: http://%s/\n' "$public_ip"
