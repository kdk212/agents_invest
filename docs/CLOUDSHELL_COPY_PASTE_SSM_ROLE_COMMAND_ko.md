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

실행 후 CloudShell에서 바로 확인하려면 아래 문서를 사용합니다.

```text
docs/CLOUDSHELL_VERIFY_SSM_READY_ko.md
```

## 실패했을 때 오류 의미

CloudShell 출력의 마지막 오류 20-40줄만 전달하면 됩니다. 자주 나오는 오류는 아래처럼 해석합니다.

```text
AccessDenied / UnauthorizedOperation
```

현재 AWS 사용자에게 IAM Role 생성, 정책 연결, EC2 instance profile 연결 권한이 부족한 상태입니다. 관리자 권한 사용자로 실행하거나, IAM/EC2 권한이 있는 사용자로 실행해야 합니다.

```text
InvalidInstanceID.NotFound
```

인스턴스 ID나 Region이 맞지 않습니다. 현재 문서는 `ap-southeast-2`와 `i-08bdbe63b2db7880f` 기준입니다.

```text
NoSuchEntity
```

Role 또는 Instance Profile이 아직 생성되기 전 조회됐거나 이름이 다릅니다. 전체 블록을 처음부터 다시 실행하면 대부분 해결됩니다.

```text
LimitExceeded
```

IAM Role 또는 Instance Profile 한도에 걸렸을 수 있습니다. 기존 불필요한 IAM Role/Profile을 정리하거나 새 이름으로 실행합니다.

```text
EntityAlreadyExists
```

이미 같은 이름의 Role 또는 Instance Profile이 있습니다. 이 문서의 명령은 대부분 기존 리소스를 재사용하지만, 중간에 멈췄다면 전체 블록을 다시 실행합니다.

```text
Cannot exceed quota for PoliciesPerRole
```

Role에 너무 많은 정책이 붙어 있습니다. `agents-invest-ec2-runtime-role`에 불필요한 정책이 많이 붙어 있는지 확인합니다.

```text
An error occurred (Throttling)
```

AWS API 호출이 잠시 제한된 상태입니다. 1-2분 뒤 전체 블록을 다시 실행합니다.

```text
Done. Wait 2-5 minutes...
```

명령은 성공한 상태입니다. 2-5분 기다린 뒤 EC2 `Connect > Session Manager`를 새로고침합니다. 그래도 Offline이면 EC2 네트워크, route table, outbound, VPC endpoint 문제일 가능성이 큽니다.
