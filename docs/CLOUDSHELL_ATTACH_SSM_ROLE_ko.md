# CloudShell에서 EC2 SSM Role 붙이기

Session Manager가 계속 오프라인이면 AWS CloudShell에서 EC2용 IAM Role을 만들고 인스턴스에 붙일 수 있습니다.

현재 대상:

```text
Region: ap-southeast-2
Instance ID: i-08bdbe63b2db7880f
```

이 문서의 명령은 AWS CloudShell에서 실행합니다. EC2 안에서 실행하는 명령이 아닙니다.

## 1. CloudShell 열기

AWS 콘솔 오른쪽 위의 CloudShell 아이콘을 누릅니다.

CloudShell이 열리면 아래 명령을 그대로 붙여넣습니다.

## 2. IAM Role 만들고 EC2에 붙이기

```bash
REGION="ap-southeast-2"
INSTANCE_ID="i-08bdbe63b2db7880f"
ROLE_NAME="agents-invest-ec2-runtime-role"
PROFILE_NAME="agents-invest-ec2-instance-profile"

cat > /tmp/agents-invest-ec2-trust.json <<'EOF'
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

aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1 || \
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document file:///tmp/agents-invest-ec2-trust.json

aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1 || \
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME"

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

aws ec2 describe-instances \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].IamInstanceProfile' \
  --output table
```

마지막에 표가 나오고 `Arn` 또는 `Id`가 보이면 IAM instance profile이 붙은 것입니다.

## 3. EC2 재부팅

Role을 붙인 뒤에도 바로 Online이 안 될 수 있습니다. CloudShell에서 아래 명령으로 재부팅합니다.

```bash
aws ec2 reboot-instances \
  --region ap-southeast-2 \
  --instance-ids i-08bdbe63b2db7880f
```

2-5분 기다린 뒤 AWS 콘솔에서 다시 확인합니다.

```text
EC2 > Instances > i-08bdbe63b2db7880f > Connect > Session Manager
```

정상 상태:

```text
Ping status: Online
Session Manager connection status: Connected
```

## 4. 그래도 Offline이면

IAM Role 문제는 해결됐을 가능성이 높고, 다음은 네트워크 문제일 수 있습니다.

확인할 것:

- EC2에 Public IPv4가 있는지
- Subnet route table에 Internet Gateway 경로가 있는지
- Security Group outbound가 전체 허용인지
- Network ACL이 outbound/inbound를 막고 있지 않은지

private subnet이면 아래 VPC Endpoint가 필요합니다.

```text
ssm
ssmmessages
ec2messages
```

처음 운영에서는 public subnet + outbound 허용 구성이 가장 쉽습니다.

## 5. Session Manager가 Online 된 뒤

EC2에 접속해서 아래를 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y git

git clone https://github.com/kdk212/agents_invest.git
cd agents_invest

AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2

sudo REPO_URL=https://github.com/kdk212/agents_invest.git \
  AWS_REGION=ap-southeast-2 \
  RUNTIME_MODE=paper \
  bash deploy/aws/bootstrap_ec2_ubuntu.sh

cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

대시보드 주소:

```text
http://13.55.135.136/
```
