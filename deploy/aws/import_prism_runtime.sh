#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agents_invest}"
APP_USER="${APP_USER:-ssm-user}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/dragon1086/prism-insight.git}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
PREFIX="${PREFIX:-prism-insight}"

step() {
  printf '\n==> %s\n' "$1"
}

pip_install_optional() {
  local package="$1"
  if sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/python -m pip install '$package'"; then
    return 0
  fi
  echo "optional package install skipped: $package"
  return 0
}

require_python_310_plus() {
  local python_bin="$APP_DIR/.venv/bin/python"
  if sudo -u "$APP_USER" "$python_bin" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
  then
    sudo -u "$APP_USER" "$python_bin" --version
    return 0
  fi

  echo "Python 3.10+ is required by the upstream PRISM runtime." >&2
  echo "Current virtualenv is too old: $python_bin" >&2
  echo "Run: sudo bash deploy/aws/repair_and_verify_ec2.sh" >&2
  exit 2
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/aws/import_prism_runtime.sh" >&2
  exit 2
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  APP_USER="ssm-user"
fi

if [ ! -d "$APP_DIR" ]; then
  echo "Application directory not found: $APP_DIR" >&2
  exit 2
fi

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  echo "Virtualenv python not found: $APP_DIR/.venv/bin/python" >&2
  echo "Run bootstrap first: sudo bash deploy/aws/bootstrap_ec2_amazon_linux.sh" >&2
  exit 2
fi

require_python_310_plus

if ! command -v git >/dev/null 2>&1; then
  echo "git is required. Run the Amazon Linux bootstrap first." >&2
  exit 2
fi

step "Prepare PRISM runtime import directory"
cd "$APP_DIR"
if [ -d "$PREFIX/.git" ]; then
  sudo -u "$APP_USER" git -C "$PREFIX" fetch origin "$UPSTREAM_BRANCH"
  sudo -u "$APP_USER" git -C "$PREFIX" checkout "$UPSTREAM_BRANCH"
  sudo -u "$APP_USER" git -C "$PREFIX" pull --ff-only origin "$UPSTREAM_BRANCH"
elif [ -d "$PREFIX" ]; then
  echo "$PREFIX exists but is not a git checkout. Moving it aside."
  mv "$PREFIX" "$PREFIX.backup.$(date +%Y%m%d%H%M%S)"
  sudo -u "$APP_USER" git clone --branch "$UPSTREAM_BRANCH" "$UPSTREAM_URL" "$PREFIX"
else
  sudo -u "$APP_USER" git clone --branch "$UPSTREAM_BRANCH" "$UPSTREAM_URL" "$PREFIX"
fi

step "Install core PRISM runtime dependencies"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/python -m pip install -e '$APP_DIR[test,aws]'"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/python -m pip install \
  python-dotenv \
  pykrx==1.0.48 \
  requests \
  PyYAML \
  tabulate \
  holidays \
  ujson \
  json-repair \
  tenacity \
  scipy"

step "Install optional PRISM extras when compatible"
pip_install_optional kospi_kosdaq_stock_server

step "Install KRX compatibility shim"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/install_prism_krx_compat.py --prism-dir '$APP_DIR/$PREFIX'"

step "Apply agents_invest adapter patches"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/patch_prism_adapters.py"

step "Verify PRISM runtime wiring"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/check_integration.py"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/patch_prism_adapters.py --check"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/install_prism_krx_compat.py --prism-dir '$APP_DIR/$PREFIX' --check"

step "Smoke-check PRISM trigger imports"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR:$APP_DIR/$PREFIX' .venv/bin/python scripts/check_prism_runtime_imports.py --prism-dir '$APP_DIR/$PREFIX' --json"

step "Refresh dashboard status"
mkdir -p "$APP_DIR/dashboard"
touch "$APP_DIR/dashboard/status.json"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/dashboard"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && PYTHONPATH='$APP_DIR' .venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json"

cat <<EOF

PRISM runtime import complete on EC2.

Current checks:
  cd $APP_DIR
  .venv/bin/python scripts/check_integration.py
  .venv/bin/python scripts/check_prism_runtime_imports.py --json
  bash scripts/diagnose_ec2_runtime.sh

Note: this imports PRISM on the EC2 runtime even if GitHub Actions manual dispatch is unavailable.
A GitHub PR can still be created later when Actions or local Git push is available.
EOF