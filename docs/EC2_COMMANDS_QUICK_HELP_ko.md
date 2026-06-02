# EC2 명령 실행 빠른 도움말

이 문서는 AWS EC2에서 `agents_invest` 대시보드와 24시간 실행 상태를 확인할 때 자주 쓰는 명령을 어디서 실행해야 하는지 정리합니다.

## 먼저 확인: CloudShell이 아닙니다

`cd /opt/agents_invest` 같은 명령은 AWS CloudShell에서 실행하면 안 됩니다. CloudShell은 EC2 서버가 아니라 AWS 콘솔용 별도 터미널입니다.

AWS 콘솔 오른쪽 위의 CloudShell 버튼이 아니라, EC2 인스턴스 상세 화면의 `Connect` 버튼을 사용합니다.

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Connect > Session Manager > Connect
```

검은 터미널 화면이 열리면 먼저 다음을 확인합니다.

```bash
ps -p 1 -o comm=
```

정상적인 EC2 Ubuntu 서버라면 보통 다음처럼 나옵니다.

```text
systemd
```

아래처럼 나오거나 `systemctl`이 동작하지 않으면 EC2가 아니라 CloudShell 또는 다른 제한된 터미널일 가능성이 큽니다.

```text
System has not been booted with systemd as init system
```

## Session Manager가 오프라인일 때

아래 오류가 보이면 EC2에 SSM 접속 권한이 아직 제대로 붙지 않은 상태입니다.

```text
DHMC is not enabled and IAM instance profile is not attached
SSM Agent unable to acquire credentials
Ping status: Offline
```

먼저 이 문서를 따라 확인합니다.

```text
docs/SSM_SESSION_MANAGER_TROUBLESHOOTING_ko.md
```

핵심은 EC2에 `AmazonSSMManagedInstanceCore` 권한이 있는 EC2용 IAM Role을 붙이는 것입니다.

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Actions > Security > Modify IAM role
```

붙인 뒤 2-5분 기다리고 `Connect > Session Manager`를 새로고침합니다.

`.pem` SSH 키가 있으면 Session Manager 대신 SSH로도 접속할 수 있습니다.

```powershell
ssh -i "C:\path\to\your-key.pem" ubuntu@13.55.135.136
```

SSH 절차는 아래 문서를 봅니다.

```text
docs/EC2_SSH_FALLBACK_ko.md
```

## 처음 설치할 때

EC2 안에 접속한 뒤 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y git

git clone https://github.com/kdk212/agents_invest.git
cd agents_invest
```

저장소가 private이면 일반 clone이 실패할 수 있습니다. 그 경우 GitHub token을 사용하거나 CloudFormation의 `GitHubToken` 입력값을 사용합니다.

기본 운영값 생성:

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
```

OpenAI/KIS/Telegram 비밀값 입력:

```bash
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
```

Telegram만 따로 수정할 때:

```bash
python scripts/configure_telegram.py --target ssm --region ap-southeast-2
```

OpenAI, KIS, Telegram 원문 값은 GitHub나 채팅에 붙여넣지 말고 AWS SecureString에만 저장합니다.

## 서버 설치

EC2 안에서 실행합니다.

```bash
sudo REPO_URL=https://github.com/kdk212/agents_invest.git \
  AWS_REGION=ap-southeast-2 \
  RUNTIME_MODE=paper \
  bash deploy/aws/bootstrap_ec2_ubuntu.sh
```

이 스크립트는 `/opt/agents_invest`에 실행 환경을 만들고, paper 모드 systemd 서비스를 등록합니다.

## 대시보드 설치

EC2 안에서 실행합니다.

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

현재 알려진 인스턴스 IP 기준 대시보드 주소:

```text
http://13.55.135.136/
```

## 빠른 진단

EC2 안에서 아래 명령을 실행하면 서버, 대시보드, nginx, 서비스, 최근 로그를 한 번에 확인합니다.

```bash
cd /opt/agents_invest
bash scripts/diagnose_ec2_runtime.sh
```

`/opt/agents_invest`가 없으면 저장소 clone 또는 bootstrap이 실패했을 가능성이 큽니다. 이때는 EC2 안에서 다음 로그를 확인합니다.

```bash
sudo tail -200 /var/log/cloud-init-output.log
```

## 서비스 상태 확인

```bash
sudo systemctl status agents-invest --no-pager
```

실시간 로그:

```bash
sudo journalctl -u agents-invest -f
```

서비스 시작:

```bash
sudo systemctl start agents-invest
```

서비스 중지:

```bash
sudo systemctl stop agents-invest
```

서비스 재시작:

```bash
sudo systemctl restart agents-invest
```

## 대시보드가 안 열릴 때

먼저 EC2 안에서 nginx 상태를 봅니다.

```bash
sudo systemctl status nginx --no-pager
```

EC2 내부에서 로컬 접속이 되는지 확인합니다.

```bash
curl -I http://127.0.0.1/
```

EC2 내부에서는 열리는데 브라우저에서만 안 열리면 보통 Security Group 문제입니다.

확인 위치:

```text
EC2 > Instances > 인스턴스 선택 > Security tab > Security groups > Inbound rules
```

80 포트가 본인 IP에서 허용되어 있어야 합니다.

```text
Type: HTTP
Port: 80
Source: 본인IP/32
```

## GitHub 저장소가 private일 때

CloudFormation으로 EC2를 만들 때 `GitHubToken`에 clone 권한이 있는 토큰을 넣어야 `/opt/agents_invest`가 만들어집니다.

이미 EC2가 만들어졌는데 `/opt/agents_invest`가 없다면 User data 실행 중 repo clone에서 실패했을 가능성이 큽니다.

```bash
sudo tail -200 /var/log/cloud-init-output.log
```

## 즉시 멈추기

AWS 콘솔에서 다음 값을 `true`로 바꾸면 신규 실행이 막힙니다.

```text
Systems Manager > Parameter Store > /agents-invest/kill-switch = true
```
