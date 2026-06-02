# AWS 콘솔 설정 체크리스트

이 체크리스트는 `agents_invest`를 AWS `ap-southeast-2`에서 24시간 paper 모드로 실행하기 위해 콘솔에서 확인하거나 설정해야 하는 항목입니다.

## 1. EC2

콘솔 위치:

```text
EC2 > Instances > Launch instance
```

권장값:

- Region: `ap-southeast-2`
- AMI: Ubuntu LTS
- Instance type: `t3.small` 이상
- Storage: 20GB 이상
- Auto-assign public IP: SSH 접속이 필요하면 활성화
- Security Group: SSH 22번은 본인 IP만 허용
- Dashboard Security Group: HTTP 80번은 대시보드 확인용으로 허용

권장 태그:

```text
Name=agents-invest-paper
Project=agents-invest
Mode=paper
```

## 2. IAM Role

콘솔 위치:

```text
IAM > Roles > Create role > AWS service > EC2
```

역할 이름 예시:

```text
agents-invest-ec2-runtime-role
```

연결할 권한:

- `AmazonSSMManagedInstanceCore`
- `deploy/aws/iam_policy_agents_invest_runtime.json` 내용을 사용자 지정 정책으로 생성 후 연결

이 Role은 EC2가 실행 중 다음을 할 수 있게 합니다.

- Session Manager 접속
- `/agents-invest/*` SSM Parameter 읽기
- SecureString 복호화
- CloudWatch Logs 쓰기

이미 EC2를 만든 뒤 Role을 붙이는 위치:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Actions > Security > Modify IAM role
```

`agents-invest-ec2-runtime-role` 또는 `AmazonSSMManagedInstanceCore`가 붙은 EC2용 Role을 선택하고 저장합니다. 저장 후 2-5분 기다린 뒤 Session Manager 화면을 새로고침합니다.

다음 에러가 보이면 EC2 IAM Role 또는 계정 DHMC 설정 문제입니다.

```text
DHMC is not enabled and IAM instance profile is not attached
SSM Agent unable to acquire credentials
```

이 경우 가장 빠른 해결은 EC2에 `AmazonSSMManagedInstanceCore`가 포함된 IAM Role을 연결하는 것입니다.

초기 SSM 값을 만드는 사용자나 임시 Role에는 다음 정책을 사용합니다.

```text
deploy/aws/iam_policy_agents_invest_setup.json
```

setup 권한은 계속 붙여둘 필요가 없습니다.

## 3. Systems Manager Parameter Store

콘솔 위치:

```text
Systems Manager > Parameter Store
```

기본값 생성:

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
```

필수 운영값:

```text
/agents-invest/kill-switch=false
/agents-invest/trading-mode=paper
/agents-invest/paper-validation-approved=false
/agents-invest/max-daily-loss-pct=3.0
/agents-invest/max-positions=10
/agents-invest/max-same-sector=3
/agents-invest/max-sector-weight-pct=30.0
/agents-invest/min-buy-score=7.0
/agents-invest/min-profit-score=60.0
/agents-invest/min-risk-reward=1.2
/agents-invest/max-expected-loss-pct=7.0
```

필수 보안값은 `SecureString`으로 저장합니다.

```text
/agents-invest/openai/api-key
/agents-invest/kis/app-key
/agents-invest/kis/app-secret
/agents-invest/kis/account-no
/agents-invest/telegram/bot-token
/agents-invest/telegram/chat-id
```

OpenAI/KIS/Telegram 값은 채팅이나 GitHub에 붙여넣지 말고 AWS 콘솔의 Parameter Store 또는 전용 입력 도구로만 저장합니다.

## 4. Session Manager 접속

콘솔 위치:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Connect > Session Manager > Connect
```

CloudShell이 아니라 EC2 인스턴스 상세 화면의 `Connect` 버튼을 사용합니다.

접속 후 EC2인지 확인:

```bash
ps -p 1 -o comm=
```

정상 EC2 Ubuntu면 보통 다음이 나옵니다.

```text
systemd
```

## 5. 비상정지

신규 실행을 막고 싶으면 콘솔에서 다음 값을 바꿉니다.

```text
/agents-invest/kill-switch=true
```

서비스는 반복 실행 중에도 SSM 값을 다시 읽고, kill switch가 `true`이면 신규 실행을 차단합니다.

## 6. EC2에서 실행할 명령

EC2 접속 후:

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
```

서비스 시작:

```bash
sudo systemctl start agents-invest
sudo systemctl status agents-invest --no-pager
sudo journalctl -u agents-invest -f
```

대시보드 설치:

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

## 7. 실계좌 전환 전 확인

아래가 모두 끝나기 전에는 live로 바꾸지 않습니다.

- GitHub Actions `integrate-prism-insight` 성공
- `python scripts/check_integration.py` 성공
- `python scripts/patch_prism_adapters.py --check` 성공
- 페이퍼트레이딩 최소 거래 수 충족
- `PaperTradingValidator` 통과
- Telegram 알림 확인
- journal 또는 CloudWatch 로그 확인
- Kill Switch 동작 확인
- RiskGovernor가 주문 직전에 차단 가능한 상태 확인

전환 시 필요한 값:

```text
/agents-invest/trading-mode=live
/agents-invest/paper-validation-approved=true
/agents-invest/kill-switch=false
```

EC2 `config/runtime.env` 기준:

```text
APP_ENV=production
TRADING_MODE=live
PAPER_VALIDATION_APPROVED=true
KILL_SWITCH=false
ENABLE_SSM_SETTINGS=true
```

## 8. 내가 확인해야 할 정보

작업을 이어가기 위해 사용자가 알려주면 좋은 정보입니다. 비밀값 원문은 알려주지 않아도 됩니다.

- EC2를 만들었는지 여부
- EC2 OS가 Ubuntu인지 여부
- EC2에 연결한 IAM Role 이름
- Session Manager Ping status가 Online인지 여부
- Parameter Store에 `/agents-invest/*` 값이 생성됐는지 여부
- KIS 실계좌 API를 쓸지, 모의투자 API를 먼저 쓸지
- Telegram 알림을 받을 chat id가 준비됐는지 여부

계좌번호, API secret, 토큰 원문은 채팅에 붙이지 말고 AWS SecureString에만 저장합니다.
