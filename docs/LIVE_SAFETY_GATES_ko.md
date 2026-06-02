# live 전환 안전 조건

`agents_invest`는 처음부터 실계좌 자동매매로 가지 않습니다. PRISM 원본 에이전트를 복사해 보완하더라도, 아래 조건이 통과되기 전에는 `TRADING_MODE=live`가 차단됩니다.

## 코드상 필수 조건

live 모드는 `runtime/safety.py`에서 다음 조건을 모두 요구합니다.

```text
APP_ENV=production
TRADING_MODE=live
PAPER_VALIDATION_APPROVED=true
KILL_SWITCH=false
MAX_DAILY_LOSS_PCT > 0
MAX_POSITIONS > 0
MAX_SECTOR_WEIGHT_PCT > 0
```

하나라도 빠지면 시작 안전검사에서 차단됩니다.

## paper 검증 기준

`optimization/paper_validator.py` 기준입니다.

```text
최소 거래 수: 30
최소 승률: 45.0%
최소 기대값: 0.5%
최대 MDD: 15.0%
최소 손익비 계수: 1.2
단일 트리거 의존도: 55% 이하
단일 섹터 의존도: 55% 이하
```

## EC2에서 확인

```bash
cd /opt/agents_invest
.venv/bin/python -m runtime.preflight --json
```

확인할 값:

```text
startup_safety.allowed
startup_safety.reasons
ready
```

## live 전환 전 수동 확인

- Telegram 후보 알림이 정상 수신된다.
- 홈페이지에 최근 PRISM 후보가 표시된다.
- Kill Switch를 `true`로 바꾸면 신규 실행이 차단된다.
- paper 결과가 최소 거래 수와 성과 기준을 만족한다.
- KIS 계좌 정보가 paper/live 구분에 맞게 입력되어 있다.
- 하루 최대 손실, 최대 보유 종목 수, 섹터 집중 제한이 본인 리스크 허용범위 안에 있다.

## 주의

수익은 보장되지 않습니다. live 전환은 자동 후보 선정과 리스크 제한이 정상 작동함을 충분히 확인한 뒤에만 검토합니다.