#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-southeast-2}"
PREFIX="${PREFIX:-/agents-invest}"

put_string() {
  local name="$1"
  local value="$2"
  aws ssm put-parameter \
    --region "$AWS_REGION" \
    --name "$PREFIX/$name" \
    --type String \
    --value "$value" \
    --overwrite >/dev/null
  echo "put $PREFIX/$name=$value"
}

put_secure_placeholder() {
  local name="$1"
  aws ssm put-parameter \
    --region "$AWS_REGION" \
    --name "$PREFIX/$name" \
    --type SecureString \
    --value "CHANGE_ME" \
    --overwrite >/dev/null
  echo "put secure placeholder $PREFIX/$name"
}

put_string "kill-switch" "false"
put_string "trading-mode" "paper"
put_string "paper-validation-approved" "false"
put_string "max-daily-loss-pct" "3.0"
put_string "max-positions" "10"
put_string "max-sector-weight-pct" "30.0"

put_secure_placeholder "openai/api-key"
put_secure_placeholder "kis/app-key"
put_secure_placeholder "kis/app-secret"
put_secure_placeholder "kis/account-no"
put_secure_placeholder "telegram/bot-token"
put_secure_placeholder "telegram/chat-id"

cat <<EOF

Default parameters created in $AWS_REGION.

Important:
- Replace CHANGE_ME values in AWS Systems Manager Parameter Store before running real integrations.
- Keep $PREFIX/kill-switch=true whenever you want to block new execution.
- Do not commit plaintext keys to GitHub.
EOF
