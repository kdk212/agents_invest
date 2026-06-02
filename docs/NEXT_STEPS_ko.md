# 현재 다음 단계

이 문서는 `agents_invest`를 실제 24시간 paper 운영까지 가져가기 위한 현재 진행 순서입니다.

현재 알려진 EC2:

```text
Instance ID: i-08bdbe63b2db7880f
Public IPv4: 13.55.135.136
Region: ap-southeast-2
```

## 현재 상태

이제 Session Manager는 Online 상태이고, 작업은 EC2 안의 `/opt/agents_invest`에서 진행합니다.

원본 `dragon1086/prism-insight`는 직접 수정하지 않습니다. EC2 안에 복사본을 만들고, 그 복사본에만 `agents_invest` 보완 패치를 적용합니다.

## 1. EC2에서 한 번에 복구/검증

EC2 Session Manager 터미널에서 아래를 그대로 실행합니다.

```bash
cd /opt/agents_invest
git pull
sudo RUN_PRISM_ONCE=true bash deploy/aws/repair_and_verify_ec2.sh
```

이 명령은 다음을 한 번에 처리합니다.

- 최신 `agents_invest` 코드 받기
- Python 3.9 가상환경이면 Python 3.11 가상환경으로 교체
- 원본 PRISM 복사/갱신
- PRISM 에이전트 보완 패치 적용
- 필요한 패키지 설치
- 대시보드 상태 갱신
- 서비스 재시작
- 가능하면 PRISM 후보 선정 1회 실행

## 2. 정상 확인 문구

아래가 보이면 가장 중요한 PRISM 연결은 통과한 것입니다.

```text
==> Smoke-check PRISM trigger imports
"ready": true
```

대시보드는 아래 주소입니다.

```text
http://13.55.135.136/
```

`HTTP/1.1 200 OK`가 보이면 EC2 내부 웹서버도 정상에 가깝습니다.

## 3. 괜찮은 경고

Amazon Linux Python 환경에서 아래가 나와도 괜찮습니다. 이 패키지는 선택 설치로 처리합니다.

```text
optional package install skipped: kospi_kosdaq_stock_server
```

## 4. 실패했을 때 보내줄 부분

아래 중 하나가 보이면 그 줄과 주변 20줄만 보내주세요.

```text
missing python module: 패키지이름
```

```text
trigger_batch import failed: 에러내용
```

```text
Python 3.10+ is required
```

## 5. OpenAI/KIS/Telegram 비밀값 입력

비밀값은 채팅창이나 GitHub에 붙여넣지 않습니다. EC2 터미널에서 직접 입력합니다.

```bash
cd /opt/agents_invest
.venv/bin/python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
.venv/bin/python scripts/test_telegram_alert.py --json
```

Telegram 테스트에서 아래가 나오면 아직 토큰 또는 chat id가 저장되지 않은 것입니다.

```text
telegram_secret_missing
```

## 6. 절대 바로 live로 전환하지 않기

처음은 반드시 `paper` 모드입니다.

live 전환 전 필수 확인:

- PRISM 후보 선정이 1회 이상 정상 실행
- 대시보드에 최근 후보/상태가 표시
- Telegram 알림 수신 확인
- paper 모드에서 충분한 거래 수 확보
- `PaperTradingValidator` 통과
- strict runtime preflight 통과
- Kill Switch 동작 확인
- RiskGovernor 차단 동작 확인
- KIS API 연결 확인

수익은 보장할 수 없습니다. 목표는 원본 PRISM 에이전트를 유지하면서, 수익 기대값 점수화와 위험 차단, 성과 피드백으로 무리한 매매를 줄이고 검증 가능한 자동화로 만드는 것입니다.
