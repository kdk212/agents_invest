# AWS EC2 24시간 실행 가이드

이 문서는 `kdk212/agents_invest`를 AWS `ap-southeast-2` 리전의 EC2에서 24시간 실행하기 위한 최소 절차입니다.

콘솔에서 어떤 값을 선택해야 하는지만 빠르게 확인하려면 [AWS 콘솔 설정 체크리스트](AWS_CONSOLE_CHECKLIST_ko.md)를 먼저 봅니다.

## 0. 중요한 운영 원칙

처음에는 반드시 `paper` 모드로만 실행합니다. 실계좌 `live` 모드는 페이퍼트레이딩 성과 검증, 알림, 로그, 비상정지 확인이 끝난 뒤에만 전환합니다.

수익은 보장할 수 없습니다. 이 구조의 목적은 무리한 매매를 줄이고, 검증된 후보만 통과시키며, 중단 가능한 자동화로 운영 리스크를 낮추는 것입니다.

## 1. EC2 만들기

AWS 콘솔에서 다음 기준으로 EC2를 생성합니다.

- Region: `ap-southeast-2`
- AMI: Ubuntu LTS
- Instance type: `t3.small` 이상
- Storage: 20GB 이상
- Security group: SSH는 본인 IP만 허용, 대시보드 확인용 HTTP 80 허용
- IAM role: 런타임 정책과 `AmazonSSMManagedInstanceCore`가 연결된 EC2 Role

IAM 정책 예시:

- `deploy/aws/iam_policy_agents_invest_runtime.json`: EC2가 실행 중 사용할 권한입니다. Parameter Store 읽기와 CloudWatch Logs 쓰기를 허용합니다.
- `deploy/aws/iam_policy_agents_invest_setup.json`: 초기 설정자가 SSM 기본값과 SecureString을 만들 때 사용할 권한입니다. 계속 붙여둘 필요는 없습니다.

## 2. Session Manager 접속 준비

Session Manager를 쓰려면 EC2에 IAM Role이 연결되어 있어야 합니다.

필수 AWS managed policy:

```text
AmazonSSMManagedInstanceCore
```

이미 만든 인스턴스에 붙이는 위치:

```text
EC2 > Instances > i-08bdbe63b2db7880f 선택 > Actions > Security > Modify IAM role
```

Role을 붙인 뒤 2-5분 기다리고 `Connect > Session Manager` 화면을 새로고침합니다.

다음 에러가 보이면 Role이 없거나 DHMC가 설정되지 않은 상태입니다.

```text
DHMC is not enabled and IAM instance profile is not attached
SSM Agent unable to acquire credentials
```

가장 빠른 해결은 `AmazonSSMManagedInstanceCore`가 포함된 EC2용 IAM Role을 인스턴스에 연결하는 것입니다.

CloudShell과 EC2는 다릅니다. CloudShell에서는 `/opt/agents_invest`가 없고 `systemctl`이 동작하지 않을 수 있습니다. EC2에 접속했는지 확인하려면 다음을 실행합니다.

```bash
ps -p 1 -o comm=
```

정상 EC2 Ubuntu면 보통 다음이 나옵니다.

```text
systemd
```

## 3. EC2 접속 후 저장소 받기

처음 접속한 홈 디렉터리에서 스크립트 실행용 저장소를 받습니다.

```bash
sudo apt-get update
sudo apt-get install -y git

git clone https://github.com/kdk212/agents_invest.git
cd agents_invest
```

부트스트랩 스크립트는 실제 실행 위치를 `/opt/agents_invest`로 준비합니다. 홈 디렉터리의 clone은 설치 스크립트를 실행하기 위한 작업용입니다.

## 4. SSM 기본값과 비밀값 만들기

SSM 값을 만들 권한이 있는 사용자 또는 임시 setup role로 기본 운영값을 생성합니다.

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
```

이 스크립트는 `/agents-invest/*` 경로에 기본 설정과 보안값 자리표시자를 만듭니다.

그 다음 OpenAI/KIS/Telegram 값을 SecureString으로 저장합니다. 입력값은 화면에 다시 출력되지 않습니다.

```bash
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
```

저장되는 SecureString:

```text
/agents-invest/openai/api-key
/agents-invest/kis/app-key
/agents-invest/kis/app-secret
/agents-invest/kis/account-no
/agents-invest/telegram/bot-token
/agents-invest/telegram/chat-id
```

Telegram만 별도로 수정할 때는 다음 명령을 사용할 수 있습니다.

```bash
python scripts/configure_telegram.py --target ssm --region ap-southeast-2
```

키, 토큰, 계좌번호 원문은 절대 GitHub에 커밋하지 않습니다.

## 5. EC2 부트스트랩

EC2에서 다음 명령으로 서버를 준비합니다.

```bash
sudo REPO_URL=https://github.com/kdk212/agents_invest.git \
  AWS_REGION=ap-southeast-2 \
  RUNTIME_MODE=paper \
  bash deploy/aws/bootstrap_ec2_ubuntu.sh
```

스크립트가 하는 일:

- 필요한 OS 패키지 설치
- AWS CLI 설치
- `/opt/agents_invest`에 저장소 준비
- Python 가상환경 생성 및 AWS용 `boto3` 설치
- `config/runtime.env` 생성
- `ENABLE_SSM_SETTINGS=true` 설정
- 테스트와 설치용 안전 점검 실행
- `systemd` 서비스 등록

## 6. 대시보드 설치

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

설치 후 대시보드 주소:

```text
http://13.55.135.136/
```

브라우저에서 안 열리면 EC2 안에서 먼저 확인합니다.

```bash
curl -I http://127.0.0.1/
sudo systemctl status nginx --no-pager
```

EC2 내부에서는 열리는데 브라우저에서 안 열리면 Security Group inbound HTTP 80 문제입니다.

## 7. 서비스 시작과 로그 확인

```bash
sudo systemctl start agents-invest
sudo systemctl status agents-invest --no-pager
sudo journalctl -u agents-invest -f
```

상태가 불안정하거나 주문/알림 연결이 완전히 검증되지 않았으면 서비스를 멈춥니다.

```bash
sudo systemctl stop agents-invest
```

## 8. SSM 기반 비상정지

EC2 부트스트랩 기본값은 `ENABLE_SSM_SETTINGS=true`입니다. 이 경우 런타임은 반복 실행 중에도 SSM 설정을 다시 읽고, 다음 값이 `true`이면 신규 실행을 차단합니다.

```text
/agents-invest/kill-switch = true
```

콘솔에서 바꾸는 위치:

```text
Systems Manager > Parameter Store > /agents-invest/kill-switch
```

로컬 설정 파일만 쓰는 경우에는 `config/runtime.env`에서 다음처럼 바꿉니다.

```text
KILL_SWITCH=true
```

SSM 로딩이 실패하면 `paper` 모드에서는 경고로 남고, `live` 모드에서는 시작이 차단됩니다.

## 9. 실계좌 전환 조건

아래 조건을 모두 만족하기 전에는 `live`로 전환하지 않습니다.

- GitHub Actions `integrate-prism-insight` 성공
- `python scripts/check_integration.py` 성공
- `python scripts/patch_prism_adapters.py --check` 성공
- 페이퍼트레이딩 최소 거래 수 충족
- `PaperTradingValidator` 통과
- 일일 손실 한도 동작 확인
- RiskGovernor가 실제 주문 직전에 연결된 상태
- Telegram 알림 확인
- CloudWatch 또는 journal 로그 확인
- Kill Switch 동작 확인
- 수동 종료/재시작 절차 확인

전환 시 환경값은 다음 조합이어야 합니다.

```text
APP_ENV=production
TRADING_MODE=live
PAPER_VALIDATION_APPROVED=true
KILL_SWITCH=false
ENABLE_SSM_SETTINGS=true
```
