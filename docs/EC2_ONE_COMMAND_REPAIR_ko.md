# EC2 한 방 복구/점검 명령

EC2 Session Manager 터미널에서 아래만 실행하면 최신 코드 반영, PRISM 원본 복사/패치, 서비스 복구, 테스트, 진단까지 한 번에 진행합니다.

```bash
cd /opt/agents_invest
sudo bash deploy/aws/repair_and_verify_ec2.sh
```

PRISM 후보 선정을 즉시 한 번 실행해서 홈페이지와 Telegram까지 확인하려면 다음처럼 실행합니다.

```bash
cd /opt/agents_invest
sudo RUN_PRISM_ONCE=true bash deploy/aws/repair_and_verify_ec2.sh
```

## 실행 후 봐야 할 것

성공에 가까운 상태라면 출력에 아래 항목들이 보입니다.

```text
PRISM runtime import complete on EC2
fully_wired: True
Telegram test alert sent successfully
agents-invest.service
HTTP/1.1 200 OK
```

홈페이지:

```text
http://13.55.135.136/
```

## Telegram이 실패하면

아래가 보이면 Telegram 토큰 또는 chat id가 아직 저장되지 않은 상태입니다.

```text
telegram_secret_missing
```

이 경우 먼저 입력합니다.

```bash
cd /opt/agents_invest
.venv/bin/python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
.venv/bin/python scripts/test_telegram_alert.py --json
```

## 주의

- 이 명령은 EC2 안에서 실행해야 합니다. AWS CloudShell이 아닙니다.
- 원본 `dragon1086/prism-insight`는 수정하지 않고, EC2의 `/opt/agents_invest/prism-insight` 복사본만 갱신합니다.
- 처음 운영은 `paper` 모드입니다. live 전환은 paper 검증과 안전장치 확인 후에만 검토합니다.
- 수익은 보장되지 않습니다. 이 시스템은 후보 선정과 리스크 관리를 자동화하는 도구입니다.