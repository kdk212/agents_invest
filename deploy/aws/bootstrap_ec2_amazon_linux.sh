#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kdk212/agents_invest.git}"
PUBLIC_REPO_URL="${PUBLIC_REPO_URL:-https://github.com/kdk212/agents_invest.git}"
APP_DIR="${APP_DIR:-/opt/agents_invest}"
APP_BRANCH="${APP_BRANCH:-main}"
APP_USER="${APP_USER:-ec2-user}"
AWS_REGION="${AWS_REGION:-ap-southeast-2}"
RUNTIME_MODE="${RUNTIME_MODE:-paper}"
ENABLE_SSM_SETTINGS="${ENABLE_SSM_SETTINGS:-true}"
SSM_PARAMETER_PREFIX="${SSM_PARAMETER_PREFIX:-/agents-invest}"
DNF_EXTRA_ARGS="${DNF_EXTRA_ARGS:---allowerasing}"

step() {
  printf '\n==> %s\n' "$1"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/aws/bootstrap_ec2_amazon_linux.sh" >&2
  exit 2
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  APP_USER="ssm-user"
fi

PKG="dnf"
PKG_INSTALL_ARGS=(-y)
if command -v dnf >/dev/null 2>&1; then
  if [ -n "$DNF_EXTRA_ARGS" ]; then
    # shellcheck disable=SC2206
    PKG_INSTALL_ARGS+=($DNF_EXTRA_ARGS)
  fi
elif command -v yum >/dev/null 2>&1; then
  PKG="yum"
else
  echo "Neither dnf nor yum was found." >&2
  exit 2
fi

pkg_install() {
  "$PKG" install "${PKG_INSTALL_ARGS[@]}" "$@"
}

step "Install OS packages"
pkg_install \
  ca-certificates \
  curl \
  git \
  jq \
  python3 \
  python3-pip \
  unzip

step "Install python venv support if available"
pkg_install python3-virtualenv || true

step "Install AWS CLI v2 if missing"
if ! command -v aws >/dev/null 2>&1; then
  tmpdir="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$tmpdir/awscliv2.zip"
  unzip -q "$tmpdir/awscliv2.zip" -d "$tmpdir"
  "$tmpdir/aws/install"
  rm -rf "$tmpdir"
fi

step "Prepare application directory"
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git clone --branch "$APP_BRANCH" "$REPO_URL" "$APP_DIR"
else
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin "$APP_BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout "$APP_BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only origin "$APP_BRANCH"
fi

sudo -u "$APP_USER" git -C "$APP_DIR" remote set-url origin "$PUBLIC_REPO_URL"

step "Create Python virtual environment"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m pip install -e "$APP_DIR[test,aws]"

step "Create runtime env if missing"
mkdir -p "$APP_DIR/config"
if [ ! -f "$APP_DIR/config/runtime.env" ]; then
  cp "$APP_DIR/config/runtime.example.env" "$APP_DIR/config/runtime.env"
  sed -i "s/^AWS_REGION=.*/AWS_REGION=$AWS_REGION/" "$APP_DIR/config/runtime.env"
  sed -i "s/^APP_ENV=.*/APP_ENV=$RUNTIME_MODE/" "$APP_DIR/config/runtime.env"
  sed -i "s/^TRADING_MODE=.*/TRADING_MODE=$RUNTIME_MODE/" "$APP_DIR/config/runtime.env"
  sed -i "s/^ENABLE_SSM_SETTINGS=.*/ENABLE_SSM_SETTINGS=$ENABLE_SSM_SETTINGS/" "$APP_DIR/config/runtime.env"
  sed -i "s#^SSM_PARAMETER_PREFIX=.*#SSM_PARAMETER_PREFIX=$SSM_PARAMETER_PREFIX#" "$APP_DIR/config/runtime.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/config/runtime.env"
  chmod 600 "$APP_DIR/config/runtime.env"
fi

step "Install systemd service"
cp "$APP_DIR/deploy/systemd/agents-invest.service.example" /etc/systemd/system/agents-invest.service
systemctl daemon-reload
systemctl enable agents-invest.service

step "Run install checks"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m pytest -q "$APP_DIR/tests"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m runtime.preflight --json --allow-missing-secrets
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m agents_invest_runner --once --allow-missing-secrets

cat <<EOF

Bootstrap complete for Amazon Linux.

Next commands:
  sudo systemctl start agents-invest
  sudo systemctl status agents-invest --no-pager
  sudo journalctl -u agents-invest -f

The install check can pass before OpenAI/KIS/Telegram secrets are entered.
The runtime service remains conservative: it will block trading work until
startup safety and secret loading are healthy.
EOF
