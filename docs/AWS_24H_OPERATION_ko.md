# AWS 24시간 운영 초안

## 목적

PRISM-INSIGHT 기반 투자 자동화 프로그램을 AWS에서 24시간 안정적으로 실행하기 위한 운영 설계 초안입니다.

리전은 사용자가 지정한 `ap-southeast-2`를 기준으로 합니다.

## 기본 원칙

1. 실계좌 자동매매는 페이퍼트레이딩 검증 통과 후에만 켭니다.
2. API 키와 토큰은 코드나 GitHub에 저장하지 않습니다.
3. 모든 주문 실행 전 RiskGovernor를 통과해야 합니다.
4. 비상정지 스위치를 반드시 둡니다.
5. 로그와 알림이 없으면 실계좌 자동매매를 켜지 않습니다.

## 1단계 권장 구조: EC2

초기에는 EC2가 가장 단순합니다.

구성:

- Region: `ap-southeast-2`
- Instance: `t3.small` 또는 `t3.medium`
- OS: Ubuntu LTS
- Storage: 20GB 이상
- Process manager: `systemd`
- Logs: systemd journal, 이후 CloudWatch Logs
- Secrets: AWS Systems Manager Parameter Store 또는 Secrets Manager
- Alerts: Telegram + CloudWatch Alarm

저장소에는 EC2용 실행 파일과 가이드가 포함되어 있습니다.

- `deploy/aws/bootstrap_ec2_ubuntu.sh`: EC2 서버 준비 및 systemd 서비스 등록
- `deploy/aws/put_default_parameters.sh`: SSM Parameter Store 기본값 생성
- `deploy/aws/iam_policy_agents_invest_runtime.json`: EC2 런타임 IAM 정책 예시
- `deploy/aws/iam_policy_agents_invest_setup.json`: 초기 SSM 값 생성용 IAM 정책 예시
- [AWS EC2 24시간 실행 가이드](AWS_EC2_SETUP_ko.md)

## 2단계 권장 구조: ECS/Fargate

운영이 안정화되면 컨테이너로 이동합니다.

구성:

- ECS Cluster
- Fargate Service
- ECR 이미지 저장소
- CloudWatch Logs
- EventBridge Scheduler
- Secrets Manager

장점:

- 서버 관리 부담이 줄어듭니다.
- 배포와 롤백이 쉬워집니다.
- 장애 복구가 깔끔합니다.

단점:

- 초기 설정이 EC2보다 복잡합니다.

## 필수 환경 변수

예시:

```text
APP_ENV=paper
AWS_REGION=ap-southeast-2
TRADING_MODE=paper
KILL_SWITCH=false
MAX_DAILY_LOSS_PCT=3.0
MAX_POSITIONS=10
MAX_SECTOR_WEIGHT_PCT=30.0
TELEGRAM_ENABLED=true
```

실계좌 전환 시:

```text
APP_ENV=production
TRADING_MODE=live
PAPER_VALIDATION_APPROVED=true
KILL_SWITCH=false
```

단, `PaperTradingValidator` 기준 통과 전에는 live로 변경하지 않습니다.

## 비밀값 저장

다음 값은 GitHub에 커밋하지 않습니다.

- OpenAI API Key
- KIS App Key
- KIS App Secret
- KIS Account Number
- Telegram Bot Token
- Telegram Chat ID

권장 저장 위치:

- AWS Secrets Manager
- 또는 SSM Parameter Store SecureString

기본 Parameter Store 경로는 다음과 같습니다.

```text
/agents-invest/openai/api-key
/agents-invest/kis/app-key
/agents-invest/kis/app-secret
/agents-invest/kis/account-no
/agents-invest/telegram/bot-token
/agents-invest/telegram/chat-id
```

## 비상정지 Kill Switch

Parameter Store에 다음 값을 둡니다.

```text
/agents-invest/kill-switch = false
```

프로그램은 주문 전 이 값을 확인하도록 확장해야 합니다. `true`이면 신규 매수를 막고 알림을 보냅니다.

로컬 `.env` 기준으로는 다음 값과 대응됩니다.

```text
KILL_SWITCH=true
```

## 운영 프로세스

### 장 시작 전

1. 시장 상태 확인
2. 전일 후보 후행 성과 업데이트
3. 트리거별 성과 요약 갱신
4. 당일 리스크 한도 초기화
5. 텔레그램 상태 알림

### 장중

1. 후보 종목 탐지
2. ProfitScoringEngine 점수화
3. 에이전트 분석
4. Buy Specialist 판단
5. RiskGovernor 최종 검증
6. 페이퍼 주문 또는 실주문
7. 로그 저장 및 알림

### 장 마감 후

1. 체결/미체결 정리
2. 매매 일지 기록
3. 후보 성과 추적 테이블 업데이트
4. PaperTradingValidator 검증
5. 다음 거래일 리스크 설정 조정

## CloudWatch 알림 조건

필수 알림:

- 프로세스 종료
- 주문 API 오류
- 일일 손실 한도 도달
- Kill Switch 활성화
- 텔레그램 알림 실패
- 데이터 수집 실패
- 예상보다 많은 주문 시도

## 배포 전 체크리스트

- [ ] GitHub 저장소 최신 상태 확인
- [ ] 테스트 통과
- [ ] API 키가 GitHub에 없는지 확인
- [ ] 페이퍼트레이딩 최소 30건 이상
- [ ] PaperTradingValidator 승인
- [ ] RiskGovernor 주문 전 연결 확인
- [ ] CloudWatch 또는 journal 로그 확인
- [ ] 텔레그램 알림 확인
- [ ] Kill Switch 동작 확인
- [ ] 수동 종료/재시작 절차 확인

## 권장 진행 순서

1. 로컬 또는 GitHub Actions에서 PRISM-INSIGHT 원본과 optimization 모듈 병합
2. 페이퍼트레이딩 모드 실행
3. AWS EC2에 동일 환경 구성
4. systemd로 paper 모드 24시간 실행
5. 로그/알림/비상정지 검증
6. 최소 성과 기준 통과 후 실계좌 live 검토
