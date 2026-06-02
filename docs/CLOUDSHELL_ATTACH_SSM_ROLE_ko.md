# CloudShell에서 EC2 SSM Role 붙이기

Session Manager가 계속 오프라인이면 AWS CloudShell에서 EC2용 IAM Role을 만들고 인스턴스에 붙일 수 있습니다.

현재 대상:

```text
Region: ap-southeast-2
Instance ID: i-08bdbe63b2db7880f
```

이 문서의 명령은 AWS CloudShell에서 실행합니다. EC2 안에서 실행하는 명령이 아닙니다.

## 1. 가장 쉬운 방법: 복붙용 명령 전체 실행

저장소가 private이거나 GitHub token이 번거로우면 아래 문서의 긴 명령 블록을 CloudShell에 그대로 붙여넣습니다.

```text
docs/CLOUDSHELL_COPY_PASTE_SSM_ROLE_COMMAND_ko.md
```

이 방식은 raw 다운로드가 필요 없습니다.

## 2. CloudShell 열기

AWS 콘솔 오른쪽 위의 CloudShell 아이콘을 누릅니다.

## 3. 저장소가 public이면 바로 실행

저장소가 public이면 아래 두 줄로 실행할 수 있습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/kdk212/agents_invest/main/deploy/aws/cloudshell_attach_ssm_role.sh -o /tmp/cloudshell_attach_ssm_role.sh
bash /tmp/cloudshell_attach_ssm_role.sh
```

## 4. 저장소가 private이면

`kdk212/agents_invest`가 private이면 위 `curl`이 실패할 수 있습니다. 이 경우 아래 문서의 복붙용 명령을 사용하는 것이 가장 쉽습니다.

```text
docs/CLOUDSHELL_COPY_PASTE_SSM_ROLE_COMMAND_ko.md
```

또는 GitHub token으로 다운로드할 수 있습니다.

```bash
export GITHUB_TOKEN="여기에_clone_가능한_GitHub_token"
curl -fsSL \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/kdk212/agents_invest/main/deploy/aws/cloudshell_attach_ssm_role.sh \
  -o /tmp/cloudshell_attach_ssm_role.sh
bash /tmp/cloudshell_attach_ssm_role.sh
unset GITHUB_TOKEN
```

토큰은 채팅이나 GitHub 파일에 붙여넣지 않습니다. CloudShell에만 입력하고 실행 후 `unset GITHUB_TOKEN`으로 지웁니다.

## 5. 스크립트가 하는 일

- EC2용 IAM Role 생성
- `AmazonSSMManagedInstanceCore` 연결
- `/agents-invest/*` Parameter Store 읽기 권한 추가
- SecureString 복호화를 위한 KMS 권한 추가
- CloudWatch Logs 쓰기 권한 추가
- Instance Profile 생성
- EC2 `i-08bdbe63b2db7880f`에 Instance Profile 연결 또는 교체

마지막에 표가 나오고 `Arn` 또는 `Id`가 보이면 IAM instance profile이 붙은 것입니다.

## 6. EC2 재부팅

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

## 7. 다른 인스턴스에 쓸 때

기본값은 현재 인스턴스에 맞춰져 있습니다.

```text
REGION=ap-southeast-2
INSTANCE_ID=i-08bdbe63b2db7880f
ROLE_NAME=agents-invest-ec2-runtime-role
PROFILE_NAME=agents-invest-ec2-instance-profile
```

다른 인스턴스에 쓰려면 실행 전에 값을 바꿉니다.

```bash
REGION="ap-southeast-2" \
INSTANCE_ID="i-xxxxxxxxxxxxxxxxx" \
ROLE_NAME="agents-invest-ec2-runtime-role" \
PROFILE_NAME="agents-invest-ec2-instance-profile" \
bash /tmp/cloudshell_attach_ssm_role.sh
```

## 8. 그래도 Offline이면

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

## 9. Session Manager가 Online 된 뒤

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
