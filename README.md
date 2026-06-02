# agents_invest

PRISM-INSIGHT 기반 수익 최적화 보완 작업 저장소입니다.

## 목표

`dragon1086/prism-insight`의 기존 에이전트를 최대한 그대로 활용하되, 다음 보완 계층을 추가해 실전 운영 전 검증 가능한 투자 자동화 구조를 만듭니다.

- 후보 종목 수익 기대값 점수화
- 매수 전 리스크 차단
- 페이퍼트레이딩 검증
- 트리거/섹터/에이전트별 성과 피드백
- 24시간 운영을 위한 AWS 배포 준비

## 현재 포함된 모듈

- `optimization/profit_scoring.py`: 후보 종목 점수화 엔진
- `optimization/risk_governor.py`: 매수 직전 리스크 게이트
- `optimization/paper_validator.py`: 페이퍼트레이딩 실계좌 전환 검증
- `optimization/adapters.py`: PRISM-INSIGHT 후보 DataFrame/시나리오 dict 연결 어댑터
- `runtime/`: paper/live 시작 전 안전 점검과 프리플라이트 CLI
- `db/candidate_performance_tracker.sql`: 후보 성과 추적 스키마
- `scripts/`: 원본 병합과 통합 상태 점검 보조 스크립트
- `tests/`: 대표 의사결정, 어댑터, 런타임 안전 테스트
- `docs/`: PRISM-INSIGHT 연결 설계, AWS 운영, 라이선스, 병합 플레이북

## 빠른 점검

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m runtime.preflight --json
python scripts/check_integration.py
python -m agents_invest_runner --once
```

기본 실행은 `paper` 모드입니다. `live` 모드는 다음 조건을 모두 만족해야 시작됩니다.

- `APP_ENV=production`
- `TRADING_MODE=live`
- `PAPER_VALIDATION_APPROVED=true`
- `KILL_SWITCH=false`

## 원본 가져오기

Windows PowerShell:

```powershell
.\scripts\integrate_prism_insight.ps1
```

Linux/macOS/AWS EC2:

```bash
bash scripts/integrate_prism_insight.sh
```

가져온 뒤 확인:

```bash
python scripts/check_integration.py
```

## 적용 방향

1. PRISM-INSIGHT 원본을 별도 작업 경로에 준비합니다.
2. [원본 병합 플레이북](docs/UPSTREAM_MERGE_PLAYBOOK_ko.md)에 따라 원본을 병합합니다.
3. [어댑터 연결 가이드](docs/ADAPTER_WIRING_GUIDE_ko.md)에 따라 `trigger_batch.py`에 `enrich_trigger_dataframe_with_profit_scores()`를 연결합니다.
4. `stock_tracking_agent.py`의 주문 실행 직전에 `apply_risk_governor_to_scenario()`를 연결합니다.
5. 페이퍼트레이딩 결과를 `PaperTradingValidator`로 검증합니다.
6. 검증 기준을 통과한 뒤 [AWS 24시간 운영 초안](docs/AWS_24H_OPERATION_ko.md)에 따라 배포합니다.

## 주요 문서

- [PRISM-INSIGHT 보완 구현 지도](docs/IMPLEMENTATION_MAP_ko.md)
- [어댑터 연결 가이드](docs/ADAPTER_WIRING_GUIDE_ko.md)
- [원본 병합 플레이북](docs/UPSTREAM_MERGE_PLAYBOOK_ko.md)
- [AWS 24시간 운영 초안](docs/AWS_24H_OPERATION_ko.md)
- [PRISM-INSIGHT 라이선스 고지](docs/LICENSING_NOTICE_ko.md)

## 주의

수익은 보장할 수 없습니다. 실계좌 자동매매는 충분한 페이퍼트레이딩, 손실 한도, 모니터링, 비상 정지 장치가 준비된 뒤에만 켜야 합니다.

PRISM-INSIGHT는 AGPL-3.0 및 상업 라이선스 조건이 있으므로, 외부 제공 서비스나 SaaS 형태로 운영할 경우 원저작자 라이선스 조건을 별도로 확인해야 합니다.
