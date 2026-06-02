# AWS EC2 24시간 실행 가이드

이 문서는 `kdk212/agents_invest`를 AWS `ap-southeast-2` 리전의 EC2에서 24시간 실행하기 위한 최소 절차입니다.

## 0. 중요한 운영 원칙

처음에는 반드시 `paper` 모드로만 실행합니다. 실계좌 `live` 모드는 페이퍼트레이딩 성과 검증, 알림, 로그, 비상정지 확인이 끝난 뒤에만 전환합니다.

## 1. EC2 만들기

AWS 콘솔에서 다음 기준으로 EC2를 생성합니다.

- Region: `ap-southeast-2`
- AMI: Ubuntu LTS
- Instance type: `t3.small` 이상
- Storage: 20GB 이상
- Security group: SSH는 본인 IP만 허용
- IAM role: 런타임 정책을 연결한 EC2 Role

IAM 정책 예시:

- `deploy/aws/iam_policy_agents_invest_runtime.json`: EC2가 실행 중 사용할 권한입니다. Parameter Store 읽기와 CloudWatch Logs 쓰기를 허용합니다.
- `deploy/aws/iam_policy_agents_invest_setup.json`: 초기 설정자가 SSM 기본값을 만들 때 사용할 권한입니다. 계속 붙여둘 필요는 없습니다.

## 2. EC2 접속 후 저장소 받기

처음 접속한 홈 디렉터리에서 스크립트 실행용 저장소를 받습니다.

```bash
sudo apt-get update
sudo apt-get install -y git

git clone https://github.com/kdk212/agents_invest.git
cd agents_invest
```

부트스트랩 스크립트는 실제 실행 위치를 `/opt/agents_invest`로 준비합니다. 홈 디렉터리의 clone은 설치 스크립트를 실행하기 위한 작업용입니다.

## 3. 기본 비밀값 만들기

SSM 값을 만들 권한이 있는 사용자 또는 임시 setup role로 다음을 실행합니다.

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
```

이 스크립트는 `/agents-invest/*` 경로에 기본 설정과 보안값 자리표시자를 만듭니다.

생성 후 AWS 콘솔의 Systems Manager > Parameter Store에서 `CHANGE_ME` 값을 실제 값으로 바꿉니다.

- `/agents-invest/openai/api-key`
- `/agents-invest/kis/app-key`
- `/agents-invest/kis/app-secret`
- `/agents-invest/kis/account-no`
- `/agents-invest/telegram/bot-token`
- `/agents-invest/telegram/chat-id`

키는 절대 GitHub에 커밋하지 않습니다.

## 4. EC2 부트스트랩

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
- Python 가상환경 생성
- 테스트와 시작 전 안전 점검 실행
- `systemd` 서비스 등록

## 5. 서비스 시작과 로그 확인

```bash
sudo systemctl start agents-invest
sudo systemctl status agents-invest --no-pager
sudo journalctl -u agents-invest -f
```

상태가 불안정하거나 주문/알림 연결이 완전히 검증되지 않았으면 서비스를 멈춥니다.

```bash
sudo systemctl stop agents-invest
```

## 6. 비상정지

신규 실행을 막고 싶으면 Parameter Store에서 다음 값을 `true`로 바꿉니다.

```text
/agents-invest/kill-switch = true
```

로컬 설정 파일을 쓰는 경우에는 `config/runtime.env`에서 다음처럼 바꿉니다.

```text
KILL_SWITCH=true
```

## 7. 실계좌 전환 조건

아래 조건을 모두 만족하기 전에는 `live`로 전환하지 않습니다.

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
```

수익은 보장할 수 없습니다. 이 구조의 목적은 무리한 매매를 줄이고, 검증된 후보만 통과시키며, 중단 가능한 자동화로 운영 리스크를 낮추는 것입니다.
