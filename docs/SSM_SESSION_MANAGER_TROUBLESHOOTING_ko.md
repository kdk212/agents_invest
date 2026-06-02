# SSM Session Manager 문제 해결

이 문서는 EC2 `Connect > Session Manager`가 비활성화되거나 `Ping status: Offline`으로 보일 때 확인할 항목을 순서대로 정리합니다.

현재 자주 보이는 오류:

```text
DHMC is not enabled and IAM instance profile is not attached
SSM Agent unable to acquire credentials
AccessDeniedException: Systems Manager's instance management role is not configured for account
Ping status: Offline
Session Manager connection status: Not connected
```

이 오류는 보통 코드 문제가 아니라 EC2 접속 권한 문제입니다.

## 1. EC2에 IAM Role이 실제로 붙었는지 확인

위치:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Details > IAM role
```

`IAM role`이 비어 있으면 Session Manager는 연결되지 않습니다.

붙이는 위치:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Actions > Security > Modify IAM role
```

`AmazonSSMManagedInstanceCore` 권한이 들어간 EC2용 Role을 선택하고 저장합니다.

저장 후 2-5분 기다리고 `Connect > Session Manager`를 새로고침합니다.

## 2. Role에 SSM 정책이 붙었는지 확인

위치:

```text
IAM > Roles > EC2에 붙인 Role 선택 > Permissions
```

아래 AWS managed policy가 있어야 합니다.

```text
AmazonSSMManagedInstanceCore
```

없으면 `Add permissions`로 추가합니다.

## 3. Role의 신뢰 관계가 EC2용인지 확인

위치:

```text
IAM > Roles > EC2에 붙인 Role 선택 > Trust relationships
```

신뢰 정책에 `ec2.amazonaws.com`이 있어야 합니다.

정상 예:

```json
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
```

만약 Lambda, ECS 등 다른 서비스용 Role이면 EC2가 사용할 수 없습니다. 이 경우 새 Role을 만드는 편이 빠릅니다.

## 4. EC2를 재부팅

Role과 정책이 맞는데도 계속 Offline이면 재부팅합니다.

위치:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Instance state > Reboot instance
```

재부팅 후 2-5분 기다리고 Session Manager 화면을 다시 봅니다.

## 5. EC2가 인터넷 또는 SSM 엔드포인트에 접근 가능한지 확인

SSM Agent는 AWS Systems Manager 서비스와 통신해야 합니다.

일반 public EC2라면 보통 아래가 필요합니다.

- EC2에 Public IPv4가 있음
- Subnet route table에 `0.0.0.0/0 -> Internet Gateway` 경로가 있음
- Security Group outbound가 막혀 있지 않음
- Network ACL outbound/inbound가 과하게 막혀 있지 않음

인터넷 없는 private subnet이라면 VPC Endpoint가 필요합니다.

필요한 endpoint 예:

```text
ssm
ssmmessages
ec2messages
```

처음 설정에서는 public subnet + outbound 허용 구성이 가장 쉽습니다.

## 6. SSH 키가 있으면 우회 접속

`.pem` 키가 있으면 Session Manager를 고치기 전에도 SSH로 접속할 수 있습니다.

Windows PowerShell 예:

```powershell
ssh -i "C:\path\to\your-key.pem" ubuntu@13.55.135.136
```

Ubuntu가 아니라 Amazon Linux면 사용자명이 보통 `ec2-user`입니다.

```powershell
ssh -i "C:\path\to\your-key.pem" ec2-user@13.55.135.136
```

자세한 SSH 절차는 `docs/EC2_SSH_FALLBACK_ko.md`를 봅니다.

## 7. 가장 빠른 대안: 새 EC2를 CloudFormation으로 만들기

기존 EC2의 IAM Role, subnet, route table을 계속 추적하기 어렵다면 새 EC2를 만드는 편이 더 빠를 수 있습니다.

저장소의 CloudFormation 템플릿은 아래를 한 번에 준비합니다.

- EC2
- EC2용 IAM Role
- `AmazonSSMManagedInstanceCore`
- Parameter Store 기본값
- nginx 대시보드
- 24시간 paper 실행 서비스

문서:

```text
docs/AWS_CLOUDFORMATION_QUICKSTART_ko.md
```

템플릿:

```text
deploy/aws/cloudformation_agents_invest_ec2.yml
```

## 8. 정상으로 바뀐 뒤 실행할 명령

Session Manager가 Online이 되면 EC2 안에서 실행합니다.

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

대시보드:

```text
http://13.55.135.136/
```

대시보드가 외부에서 안 열리면 EC2 내부에서 먼저 확인합니다.

```bash
curl -I http://127.0.0.1/
sudo systemctl status nginx --no-pager
```

내부에서는 열리는데 외부에서만 안 열리면 Security Group inbound HTTP 80번 문제일 가능성이 큽니다.
