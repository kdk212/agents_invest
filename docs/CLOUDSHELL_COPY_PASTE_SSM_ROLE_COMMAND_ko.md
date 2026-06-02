# CloudShell 복붙용 SSM Role 연결 명령

이 문서는 저장소가 private이라 `curl raw.githubusercontent.com` 다운로드가 실패할 때 사용합니다.

AWS CloudShell에 아래 전체 블록을 그대로 붙여넣으면 됩니다.

```bash
set -euo pipefail

REGION="ap-southeast-2"
INSTANCE_ID="i-08bdbe63b2db7880f"
ROLE_NAME="agents-invest-ec2-runtime-role"
PROFILE_NAME="agents-invest-ec2-instance-profile"
POLICY_NAME="agents-invest-runtime-inline-policy"
PARAMETER_PREFIX="/agents-invest"

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

echo "Rebooting instance..."
aws ec2 reboot-instances --region "$REGION" --instance-ids "$INSTANCE_ID"

echo "Done. Wait 2-5 minutes, then check EC2 > Connect > Session Manager."
```

정상 목표:

```text
Ping status: Online
```

만약 이 명령도 실패하면 CloudShell 출력의 마지막 오류 20-40줄만 전달하면 됩니다.
