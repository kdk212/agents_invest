# EC2 한 방 복구/점검 명령

EC2 Session Manager 터미널에서 아래만 실행하면 최신 코드 반영, PRISM 원본 복사/패치, 서비스 복구, 테스트, 진단까지 한 번에 진행합니다.

```bash
cd /opt/agents_invest
git pull
sudo RUN_PRISM_ONCE=true bash deploy/aws/repair_and_verify_ec2.sh
```

`kospi_kosdaq_stock_server`에서 아래처럼 나와도 괜찮습니다. 현재 Amazon Linux Python 3.9 환경에서는 선택 패키지로 처리합니다.

```text
optional package install skipped: kospi_kosdaq_stock_server
```

## 실행 후 봐야 할 핵심 표시

성공에 가까운 상태라면 출력 중간이나 마지막에 아래 표시가 보입니다.

```text
==> Smoke-check PRISM trigger imports
"ready": true

== HTTP checks ==
HTTP/1.1 200 OK
```

아래도 보이면 더 좋습니다.

```text
PRISM runtime import complete on EC2
agents-invest.service
prism_batch_cycle_complete
```

홈페이지:

```text
http://13.55.135.136/
```

## 만약 PRISM 점검이 실패하면

아래 둘 중 하나가 가장 중요합니다. 이 부분만 복사해서 붙여주면 다음 보완 패키지를 바로 추가할 수 있습니다.

```text
missing python module: 패키지이름
```

또는

```text
trigger_batch import failed: 에러내용
```

## Telegram이 실패하면

아래가 보이면 Telegram 토큰 또는 chat id가 아직 저장되지 않은 상태입니다.

```text
telegram_secret_missing
```

이 경우 채팅창에 토큰을 붙여넣지 말고 EC2 터미널에서 직접 입력합니다.

```bash
cd /opt/agents_invest
.venv/bin/python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
.venv/bin/python scripts/test_telegram_alert.py --json
```

OpenAI 키, KIS 값, Telegram 토큰/chat id는 이 입력 도구에 넣으면 AWS SSM SecureString으로 저장됩니다. 화면 출력이나 GitHub에는 비밀값이 남지 않게 설계했습니다.

## 주의

- 이 명령은 EC2 안에서 실행해야 합니다. AWS CloudShell이 아닙니다.
- 원본 `dragon1086/prism-insight`는 수정하지 않고, EC2의 `/opt/agents_invest/prism-insight` 복사본만 갱신합니다.
- 처음 운영은 `paper` 모드입니다. live 전환은 paper 검증과 안전장치 확인 후에만 검토합니다.
- 수익은 보장되지 않습니다. 이 시스템은 후보 선정, 리스크 관리, 반복 실행, 알림, 대시보드 확인을 자동화하는 도구입니다.
