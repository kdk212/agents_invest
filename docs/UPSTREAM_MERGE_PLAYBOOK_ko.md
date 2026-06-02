# PRISM-INSIGHT 원본 병합 플레이북

## 목적

`dragon1086/prism-insight` 원본 코드를 `kdk212/agents_invest` 작업 저장소에 가져와, 기존 에이전트를 유지하면서 `optimization/` 보완 모듈을 연결한다.

## 전제

- GitHub 저장소: `kdk212/agents_invest`
- 원본 저장소: `dragon1086/prism-insight`
- 원본 라이선스: AGPL-3.0
- 기본 운영 모드: paper

## GitHub Actions로 병합

로컬 Git, Windows 경로, 인증서 문제가 있으면 GitHub Actions 수동 워크플로를 사용한다. 화면별 절차는 [GitHub Actions PRISM-INSIGHT 통합 실행](GITHUB_ACTIONS_PRISM_INTEGRATION_ko.md)을 따른다.

1. GitHub 저장소의 `Actions` 탭으로 이동한다.
2. `integrate-prism-insight` 워크플로를 선택한다.
3. `Run workflow`를 누른다.
4. 기본값 그대로 실행하면 `integrate-prism-insight` 브랜치가 생성 또는 업데이트된다.
5. 워크플로는 원본 import, 어댑터 자동 패치, 테스트, 통합 점검, 프리플라이트를 실행한다.
6. 성공하면 draft PR을 자동 생성하거나 기존 PR을 업데이트한다.
7. draft PR에서 라이선스, 패치 위치, paper/live 안전 조건을 검토한 뒤 main 병합을 진행한다.

이 방식은 `main`을 직접 수정하지 않는다.

## 로컬 빠른 자동 병합과 패치

가능하면 먼저 자동 스크립트를 사용한다. 스크립트는 원본을 `prism-insight/` 하위 폴더로 가져온다. 그 다음 패치 스크립트가 세 파일에 보완을 연결한다.

자동 패치 대상:

- `prism-insight/trigger_batch.py`
- `prism-insight/stock_tracking_agent.py`
- `prism-insight/cores/agents/trading_agents.py`

Windows PowerShell:

```powershell
.\scripts\integrate_prism_insight.ps1
python scripts\patch_prism_adapters.py
python scripts\check_integration.py
python scripts\patch_prism_adapters.py --check
```

Linux/macOS/AWS EC2:

```bash
bash scripts/integrate_prism_insight.sh
python scripts/patch_prism_adapters.py
python scripts/check_integration.py
python scripts/patch_prism_adapters.py --check
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

자동 패치 우선:

```bash
python scripts/patch_prism_adapters.py
```

자동 패치가 실패하면 아래 수동 연결을 따른다.

### 6.1 후보 점수화 연결

대상 원본 파일:

```text
prism-insight/trigger_batch.py
```

연결 함수:

```python
from optimization import enrich_trigger_dataframe_with_profit_scores
```

`select_final_tickers()`에서 `final_score` 계산 직후:

```python
scored_df = enrich_trigger_dataframe_with_profit_scores(
    scored_df,
    trigger_type=name,
    market_regime=_regime,
)
```

### 6.2 Buy Specialist 프롬프트 보완

대상 원본 파일:

```text
prism-insight/cores/agents/trading_agents.py
```

`JSON Response Format` / `JSON 응답 형식` 바로 앞에 Profit Optimization Addendum을 삽입한다. 자동 패치가 삽입하는 핵심 내용은 다음이다.

- `profit_score`, `expected_value`, `risk_penalty`는 CAN SLIM을 대체하지 않고 보조 근거로 사용
- `profit_score < 55`, `expected_value <= 0`, `risk_penalty >= 25`는 반드시 rationale 또는 rejection_reason에서 설명
- 과거 트리거 승률이 낮으면 추가 확인 1개 요구
- 출력 JSON에 `risk_governor_context`, `no_entry_reasons`, `risk_controls` 포함 권장

### 6.3 매수 전 리스크 차단 연결

대상 원본 파일:

```text
prism-insight/stock_tracking_agent.py
```

연결 함수:

```python
from optimization import apply_risk_governor_to_scenario
```

`process_reports()`에서 `analysis_result.get("decision") == "Enter"` 매수 실행 직전 RiskGovernor를 호출한다. 자세한 수동 패치 예시는 [어댑터 연결 가이드](ADAPTER_WIRING_GUIDE_ko.md)를 참고한다.

### 6.4 후보 성과 추적 DB 연결

스키마:

```text
db/candidate_performance_tracker.sql
```

연결 대상:
