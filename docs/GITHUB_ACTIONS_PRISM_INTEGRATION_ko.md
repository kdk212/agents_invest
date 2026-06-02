# GitHub Actions PRISM-INSIGHT 통합 실행

로컬 Windows/OneDrive/Git 인증 문제를 피하려면 GitHub Actions에서 원본 통합을 실행합니다.

## 실행 위치

```text
GitHub > kdk212/agents_invest > Actions > integrate-prism-insight > Run workflow
```

기본값 그대로 실행합니다.

```text
upstream_url=https://github.com/dragon1086/prism-insight.git
upstream_branch=main
target_branch=integrate-prism-insight
```

## 워크플로가 하는 일

1. `main`에서 `integrate-prism-insight` 브랜치를 만듭니다.
2. `dragon1086/prism-insight` 원본을 `prism-insight/` 하위 폴더로 가져옵니다.
3. `scripts/patch_prism_adapters.py`로 다음 파일을 보완합니다.

```text
prism-insight/trigger_batch.py
prism-insight/stock_tracking_agent.py
prism-insight/cores/agents/trading_agents.py
```

4. 다음 검증을 실행합니다.

```bash
python -m pytest -q
python scripts/check_integration.py
python scripts/patch_prism_adapters.py --check
python -m runtime.preflight --json --allow-missing-secrets
```

`--allow-missing-secrets`는 GitHub Actions 통합 검증용입니다. 이 단계에서는 OpenAI/KIS/Telegram 비밀값이 없어도 코드 연결 상태를 검증합니다.

운영 서버에서는 다음 strict 검사를 별도로 통과해야 합니다.

```bash
python -m runtime.preflight --json
```

5. `integrate-prism-insight` 브랜치를 푸시합니다.
6. draft PR을 자동 생성하거나 기존 PR을 업데이트합니다.
7. Actions Summary에 브랜치와 검증 결과 요약을 남깁니다.

## 성공 후 확인

Draft PR에서 다음을 확인합니다.

- 원본 라이선스 파일과 README가 `prism-insight/` 아래 유지됐는지
- `trigger_batch.py`에 `profit_score`, `expected_value` 출력이 포함됐는지
- `stock_tracking_agent.py`에서 RiskGovernor가 매수 직전에 호출되는지
- `trading_agents.py`의 Buy Specialist 프롬프트에 Profit Optimization Addendum이 들어갔는지
- 테스트, 통합 마커, 어댑터 idempotency, install-mode preflight가 통과했는지

## live 전환 금지 조건

이 PR이 성공해도 바로 `live`로 바꾸지 않습니다. 아래가 끝나야 합니다.

- paper 모드에서 충분한 거래 수 확보
- `PaperTradingValidator` 통과
- OpenAI/KIS/Telegram SecureString 입력
- strict runtime preflight 통과
- Telegram 알림 수신 확인
- Kill Switch 동작 확인
- RiskGovernor 차단 동작 확인
- KIS API가 모의투자 또는 실계좌 환경에서 올바르게 연결되는지 확인
