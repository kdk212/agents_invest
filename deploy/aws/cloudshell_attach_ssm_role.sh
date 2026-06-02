#!/usr/bin/env bash
set -euo pipefail

REGION="${REGION:-ap-southeast-2}"
INSTANCE_ID="${INSTANCE_ID:-i-08bdbe63b2db7880f}"
ROLE_NAME="${ROLE_NAME:-agents-invest-ec2-runtime-role}"
PROFILE_NAME="${PROFILE_NAME:-agents-invest-ec2-instance-profile}"
POLICY_NAME="${POLICY_NAME:-agents-invest-runtime-inline-policy}"
PARAMETER_PREFIX="${PARAMETER_PREFIX:-/agents-invest}"

TRUST_FILE="/tmp/agents-invest-ec2-trust.json"
POLICY_FILE="/tmp/agents-invest-runtime-policy.json"

cat > "$TRUST_FILE" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
PARAMETER_RESOURCE="arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter${PARAMETER_PREFIX}/*"
LOG_RESOURCE="arn:aws:logs:${REGION}:${ACCOUNT_ID}:*"
KMS_VIA_SERVICE="ssm.${REGION}.amazonaws.com"

cat > "$POLICY_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadAgentsInvestParameters",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": "${PARAMETER_RESOURCE}"
    },
    {
      "Sid": "DecryptSecureParameters",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "${KMS_VIA_SERVICE}"
        }
      }
    },
    {
      "Sid": "WriteCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:DescribeLogStreams",
        "logs:PutLogEvents"
      ],
      "Resource": "${LOG_RESOURCE}"
    }
  ]
}
EOF

echo "Using region: $REGION"
echo "Target instance: $INSTANCE_ID"
echo "Runtime role: $ROLE_NAME"

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "Role already exists: $ROLE_NAME"
else
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$TRUST_FILE"
fi

aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "file://$POLICY_FILE"

if aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
  echo "Instance profile already exists: $PROFILE_NAME"
else
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME"
fi

aws iam add-role-to-instance-profile \
  --instance-profile-name "$PROFILE_NAME" \
  --role-name "$ROLE_NAME" 2>/dev/null || true

sleep 10

CURRENT_ASSOCIATION_ID="$(aws ec2 describe-iam-instance-profile-associations \
  --region "$REGION" \
  --filters "Name=instance-id,Values=$INSTANCE_ID" "Name=state,Values=associating,associated" \
  --query 'IamInstanceProfileAssociations[0].AssociationId' \
  --output text)"

if [ "$CURRENT_ASSOCIATION_ID" = "None" ] || [ -z "$CURRENT_ASSOCIATION_ID" ]; then
  aws ec2 associate-iam-instance-profile \
    --region "$REGION" \
    --instance-id "$INSTANCE_ID" \
    --iam-instance-profile Name="$PROFILE_NAME"
else
  aws ec2 replace-iam-instance-profile-association \
    --region "$REGION" \
    --association-id "$CURRENT_ASSOCIATION_ID" \
    --iam-instance-profile Name="$PROFILE_NAME"
fi

echo "Attached instance profile:"
aws ec2 describe-instances \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].IamInstanceProfile' \
  --output table

echo
echo "Next, reboot the instance and wait 2-5 minutes:"
echo "aws ec2 reboot-instances --region $REGION --instance-ids $INSTANCE_ID"
