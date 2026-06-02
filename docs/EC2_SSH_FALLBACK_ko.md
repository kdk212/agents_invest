# EC2 SSH 대체 접속 가이드

Session Manager가 `오프라인`이거나 `연결 비활성화` 상태일 때, EC2 생성 시 사용한 SSH key pair가 있으면 SSH로 먼저 접속해서 설치를 이어갈 수 있습니다.

현재 인스턴스 기준:

```text
Instance ID: i-08bdbe63b2db7880f
Public IPv4: 13.55.135.136
Region: ap-southeast-2
```

## 1. 먼저 Session Manager 권한은 계속 고칩니다

아래 오류가 보이면 EC2에 IAM 역할이 없거나, SSM 권한이 없는 상태입니다.

```text
DHMC is not enabled and IAM instance profile is not attached
SSM Agent unable to acquire credentials
Ping status: Offline
```

가장 빠른 해결:

```text
IAM > Roles > Create role > AWS service > EC2
```

역할에 이 managed policy를 붙입니다.

```text
AmazonSSMManagedInstanceCore
```

그 다음 기존 EC2에 연결합니다.

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Actions > Security > Modify IAM role
```

저장 후 2-5분 기다리고 `Connect > Session Manager`를 새로고침합니다.

## 2. SSH key pair가 있으면 바로 접속할 수 있습니다

EC2를 만들 때 선택한 `.pem` 파일이 PC에 있으면 Windows PowerShell에서 아래처럼 접속합니다.

```powershell
ssh -i "C:\path\to\your-key.pem" ubuntu@13.55.135.136
```

Ubuntu AMI의 기본 사용자명은 보통 `ubuntu`입니다. 만약 Amazon Linux를 사용했다면 사용자명은 보통 `ec2-user`입니다.

```powershell
ssh -i "C:\path\to\your-key.pem" ec2-user@13.55.135.136
```

## 3. SSH가 안 되면 확인할 것

EC2 보안 그룹에서 SSH 22번 포트가 본인 IP에서 허용되어 있어야 합니다.

위치:

```text
EC2 > Instances > 인스턴스 선택 > Security > Security groups > Inbound rules
```

권장 설정:

```text
Type: SSH
Port: 22
Source: 본인IP/32
```

`.pem` 파일을 잃어버렸다면 기존 인스턴스에 SSH로 들어가기 어렵습니다. 이 경우 Session Manager IAM Role을 고치거나, CloudFormation 템플릿으로 새 EC2를 만드는 편이 안전합니다.

## 4. EC2에 접속한 뒤 확인

진짜 EC2 안에 들어왔는지 먼저 확인합니다.

```bash
ps -p 1 -o comm=
```

정상적인 Ubuntu EC2라면 보통 다음이 나옵니다.

```text
systemd
```

CloudShell에서 실행하면 `/opt/agents_invest`가 없고 `systemctl`도 동작하지 않을 수 있습니다. CloudShell은 EC2가 아니라 AWS 콘솔용 별도 터미널입니다.

## 5. EC2 안에서 설치 이어가기

저장소가 아직 없다면:

```bash
sudo apt-get update
sudo apt-get install -y git

git clone https://github.com/kdk212/agents_invest.git
cd agents_invest
```

저장소가 private이면 일반 clone이 실패할 수 있습니다. 그 경우 GitHub token을 사용하거나, 저장소를 임시로 public으로 전환한 뒤 clone합니다.

기본값과 비밀값 입력:

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
```

OpenAI/KIS/Telegram 원문 값은 채팅이나 GitHub에 붙여넣지 말고 AWS SecureString에만 저장합니다.

서버 설치:

```bash
sudo REPO_URL=https://github.com/kdk212/agents_invest.git \
  AWS_REGION=ap-southeast-2 \
  RUNTIME_MODE=paper \
  bash deploy/aws/bootstrap_ec2_ubuntu.sh
```

대시보드 설치:

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

내부 확인:

```bash
curl -I http://127.0.0.1/
sudo systemctl status nginx --no-pager
```

브라우저 주소:

```text
http://13.55.135.136/
```

EC2 내부에서는 열리는데 브라우저에서 안 열리면 보통 보안 그룹의 HTTP 80번 inbound가 막힌 상태입니다.
