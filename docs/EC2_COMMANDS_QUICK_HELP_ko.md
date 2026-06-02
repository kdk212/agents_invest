# EC2 명령 실행 빠른 도움말

이 문서는 AWS EC2에서 `agents_invest` 대시보드와 24시간 실행 상태를 확인할 때 자주 쓰는 명령을 어디서 실행해야 하는지 정리합니다.

## 먼저 확인: CloudShell이 아닙니다

`cd /opt/agents_invest` 같은 명령은 AWS CloudShell에서 실행하면 안 됩니다. CloudShell은 EC2 서버가 아니라 AWS 콘솔용 별도 터미널입니다.

진짜 EC2에 접속했는지 먼저 확인합니다.

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

## 어디서 실행하나

아래 같은 명령은 내 PC PowerShell이나 AWS CloudShell이 아니라 EC2 서버 안에서 실행합니다.

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

AWS 콘솔 경로:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Connect > Session Manager > Connect
```

중요: AWS 콘솔 오른쪽 위의 `CloudShell` 버튼이 아니라, EC2 인스턴스 상세 화면의 `Connect` 버튼을 사용합니다.

검은 터미널 화면이 열리면 먼저 다음을 확인합니다.

```bash
ps -p 1 -o comm=
```

`systemd`가 나오면 그 안에서 명령을 입력합니다.

Session Manager가 안 보이면 다음 중 하나가 필요합니다.

- EC2에 `AmazonSSMManagedInstanceCore` 권한이 연결되어 있어야 합니다.
- EC2가 인터넷 또는 SSM 엔드포인트에 접근 가능해야 합니다.
- 인스턴스가 완전히 켜진 뒤 몇 분 기다려야 합니다.
- 또는 SSH key pair로 `SSH client` 접속을 사용합니다.

## 빠른 진단

EC2 안에서 아래 명령을 실행하면 서버, 대시보드, nginx, 서비스, 최근 로그를 한 번에 확인합니다.

```bash
cd /opt/agents_invest
bash scripts/diagnose_ec2_runtime.sh
```

`/opt/agents_invest`가 없으면 저장소 clone 또는 CloudFormation bootstrap이 실패했을 가능성이 큽니다. 이때는 EC2 안에서 다음 로그를 확인합니다.

```bash
sudo tail -200 /var/log/cloud-init-output.log
```

## 대시보드 설치

EC2 안에서 실행합니다.

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

설치 후 EC2의 `Public IPv4 address`로 접속합니다.

```text
http://PUBLIC_IPV4_ADDRESS/
```

현재 알려진 인스턴스 IP 기준 예:

```text
http://13.55.135.136/
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

EC2 안에서 로컬 접속이 되는지 확인합니다.

```bash
curl -I http://127.0.0.1/
```

브라우저에서만 안 열리면 보통 Security Group 문제입니다.

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

이미 EC2가 만들어졌는데 `/opt/agents_invest`가 없다면, User data 실행 중 repo clone에서 실패했을 가능성이 큽니다. 이때는 EC2 로그에서 확인합니다.

```bash
sudo tail -200 /var/log/cloud-init-output.log
```

## 비밀값 입력 위치

OpenAI, KIS, Telegram 원문 값은 GitHub에 넣지 않습니다. AWS 콘솔에서 SecureString으로 넣습니다.

```text
Systems Manager > Parameter Store
```

필요 이름:

```text
/agents-invest/openai/api-key
/agents-invest/kis/app-key
/agents-invest/kis/app-secret
/agents-invest/kis/account-no
/agents-invest/telegram/bot-token
/agents-invest/telegram/chat-id
```

## 즉시 멈추기

AWS 콘솔에서 다음 값을 `true`로 바꾸면 신규 실행이 막힙니다.

```text
Systems Manager > Parameter Store > /agents-invest/kill-switch = true
```
