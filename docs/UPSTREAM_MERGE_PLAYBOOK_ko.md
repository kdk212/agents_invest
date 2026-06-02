# PRISM-INSIGHT 원본 병합 플레이북

## 목적

`dragon1086/prism-insight` 원본 코드를 `kdk212/agents_invest` 작업 저장소에 가져와, 기존 에이전트를 유지하면서 `optimization/` 보완 모듈을 연결한다.

## 전제

- GitHub 저장소: `kdk212/agents_invest`
- 원본 저장소: `dragon1086/prism-insight`
- 원본 라이선스: AGPL-3.0
- 기본 운영 모드: paper

## 빠른 자동 병합

가능하면 먼저 자동 스크립트를 사용한다. 스크립트는 원본을 `prism-insight/` 하위 폴더로 가져오고, 테스트와 프리플라이트를 실행한다.

Windows PowerShell:

```powershell
.\scripts\integrate_prism_insight.ps1
```

Linux/macOS/AWS EC2:

```bash
bash scripts/integrate_prism_insight.sh
```

병합 상태 확인:

```bash
python scripts/check_integration.py
```

자동 스크립트가 실패하면 아래 수동 절차를 따른다.

## 권장 작업 경로

Windows OneDrive 한글 경로에서는 Git 작업이 실패할 수 있다. 가능하면 영문 경로를 사용한다.

예시:

```powershell
C:\work\agents_invest
```

## 1. 저장소 복제

```powershell
git clone https://github.com/kdk212/agents_invest.git C:\work\agents_invest
cd C:\work\agents_invest
```

## 2. 원본 remote 추가

```powershell
git remote add upstream https://github.com/dragon1086/prism-insight.git
git fetch upstream main
```

## 3. 병합 브랜치 생성

```powershell
git checkout -b integrate-prism-insight
```

## 4. 원본 병합

빈 저장소에서 시작한 경우에는 다음 중 하나를 선택한다.

### 방법 A: 원본을 하위 폴더에 보관

충돌 위험이 낮다.

```powershell
git read-tree --prefix=prism-insight/ -u upstream/main
```

이 경우 보완 모듈은 루트에 있고 원본은 `prism-insight/` 아래에 있다.

장점:

- 원본과 보완 모듈 경계가 명확하다.
- 라이선스 고지 유지가 쉽다.
- 초기에 안전하다.

단점:

- import 경로를 조정해야 할 수 있다.

### 방법 B: 원본을 루트에 병합

실제 실행 구조를 빨리 만들 수 있다.

```powershell
git merge upstream/main --allow-unrelated-histories
```

장점:

- 원본 실행 명령을 거의 그대로 쓸 수 있다.

단점:

- `README.md`, `pyproject.toml`, 문서 충돌 가능성이 높다.
- 보완 모듈과 원본 파일이 섞인다.

초기에는 방법 A를 권장한다.

## 5. 라이선스 확인

원본을 가져온 뒤 다음 파일이 포함되어야 한다.

- `LICENSE`
- 원본 README
- 원본 저작권/라이선스 고지

하위 폴더 방식이면 다음 위치가 된다.

```text
prism-insight/LICENSE
prism-insight/README.md
prism-insight/README_ko.md
```

## 6. 보완 모듈 연결 순서

### 6.1 후보 점수화 연결

대상 원본 파일:

```text
trigger_batch.py
```

연결 함수:

```python
from optimization import enrich_candidates_with_profit_scores
```

후보 리스트 생성 후:

```python
candidates = enrich_candidates_with_profit_scores(candidates)
```

### 6.2 매수 전 리스크 차단 연결

대상 원본 파일:

```text
stock_tracking_agent.py
```

연결 함수:

```python
from optimization import apply_risk_governor_to_scenario
```

Buy Specialist 시나리오 생성 후, 주문 실행 전:

```python
scenario = apply_risk_governor_to_scenario(
    scenario=scenario,
    candidate=candidate_context,
    portfolio=portfolio_context,
    market=market_context,
)

if scenario["decision"] == "no_entry":
    return scenario
```

### 6.3 후보 성과 추적 DB 연결

스키마:

```text
db/candidate_performance_tracker.sql
```

연결 대상:

```text
tracking/journal.py
tracking/db_schema.py
```

저장 대상:

- 매수한 후보
- 매수하지 않은 후보
- RiskGovernor가 차단한 후보
- 7/14/30일 후행 성과

## 7. 테스트

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/check_integration.py
```

## 8. AWS 배포 전 점검

```powershell
python -m runtime.preflight --json
python -m agents_invest_runner --once
```

기본 paper 모드에서는 통과해야 한다.

live 모드는 다음 조건이 모두 충족되어야 한다.

- `APP_ENV=production`
- `TRADING_MODE=live`
- `PAPER_VALIDATION_APPROVED=true`
- `KILL_SWITCH=false`

## 권장 다음 작업

1. 방법 A로 원본을 `prism-insight/` 하위 폴더에 가져온다.
2. 원본 실행을 먼저 paper/demo 모드로 확인한다.
3. `trigger_batch.py`에 후보 점수화 연결을 한다.
4. `stock_tracking_agent.py`에 RiskGovernor를 연결한다.
5. 페이퍼트레이딩 후보 성과 추적을 켠다.
6. GitHub Actions와 로컬 테스트를 통과시킨다.
