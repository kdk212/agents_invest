# agents_invest

PRISM-INSIGHT 기반 수익 최적화 보완 작업 저장소입니다.

## 목표

`dragon1086/prism-insight`의 기존 에이전트를 최대한 그대로 활용하되, 실전 운영 전에 검증 가능한 보완 계층을 추가합니다.

- 후보 종목 수익 기대값 점수화
- 매수 전 리스크 차단
- Buy Specialist 프롬프트에 수익 기대값, 과거 트리거 성과, 위험 제어 컨텍스트 추가
- 페이퍼트레이딩 검증
- 트리거/섹터/에이전트별 성과 피드백
- Telegram 알림과 AWS 24시간 운영 준비

수익은 보장할 수 없습니다. 이 구조의 목적은 무리한 매매를 줄이고, 검증된 후보만 통과시키며, 중단 가능한 자동화로 운영 리스크를 낮추는 것입니다.

## 현재 포함된 모듈

- `optimization/profit_scoring.py`: 후보 종목 점수화 엔진
- `optimization/risk_governor.py`: 매수 직전 리스크 게이트
- `optimization/paper_validator.py`: 페이퍼트레이딩 실계좌 전환 검증
- `optimization/adapters.py`: PRISM-INSIGHT 후보 DataFrame/시나리오 dict 연결 어댑터
- `runtime/`: paper/live 시작 전 안전 점검, 프리플라이트 CLI, 로컬 env 파일 로딩, 선택적 AWS SSM 설정 오버레이
- `runtime/ssm.py`: `/agents-invest/*` 운영 파라미터를 읽어 킬스위치와 리스크 한도에 반영
- `scripts/`: 원본 병합, 자동 패치, Telegram 설정, 통합 상태 점검 보조 스크립트
- `deploy/aws/`: EC2 부트스트랩, SSM 기본값, IAM 정책 예시
- `docs/`: PRISM-INSIGHT 연결 설계, AWS 운영, Telegram 설정, 라이선스, 병합 플레이북

## 빠른 시작 순서

1. 로컬 또는 AWS EC2에 저장소를 준비합니다.
2. Telegram 알림을 받을 bot token/chat id를 입력합니다.
3. OpenAI LLM 키와 KIS API 키를 로컬 `config/runtime.env` 또는 AWS Parameter Store에 저장합니다.
4. PRISM-INSIGHT 원본을 병합하고 자동 패치를 적용합니다.
5. `paper` 모드로 충분히 검증한 뒤에만 `live` 전환을 검토합니다.

Telegram 값은 채팅창이나 GitHub에 붙여넣지 말고 전용 도구로 입력합니다.

```bash
python scripts/configure_telegram.py --target local
```

AWS Parameter Store에 넣을 때는 다음처럼 실행합니다.

```bash
python scripts/configure_telegram.py --target ssm --region ap-southeast-2
```

기본 `config/runtime.env` 경로를 쓰기 어려운 환경에서는 별도 env 파일을 지정할 수 있습니다.

```powershell
$env:AGENTS_INVEST_ENV_FILE="C:\Users\kdk21\.codex\memories\agents_invest_runtime.env"
python -m runtime.preflight --json
```

자세한 절차는 [Telegram 알림 설정](docs/TELEGRAM_SETUP_ko.md)을 따릅니다.

## 빠른 점검

원본 PRISM-INSIGHT를 아직 가져오기 전에는 저장소 보완 모듈만 먼저 점검합니다.

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m runtime.preflight --json
python scripts/check_integration.py --allow-missing-upstream
python -m agents_invest_runner --once
```

원본을 `prism-insight/`에 붙이고 자동 패치까지 끝난 뒤에는 엄격한 최종 점검을 실행합니다.

```bash
python scripts/patch_prism_adapters.py
python scripts/check_integration.py
python scripts/patch_prism_adapters.py --check
python -m pytest -q
python -m runtime.preflight --json
```

기본 실행은 `paper` 모드입니다. `live` 모드는 다음 조건을 모두 만족해야 시작됩니다.

- `APP_ENV=production`
- `TRADING_MODE=live`
- `PAPER_VALIDATION_APPROVED=true`
- `KILL_SWITCH=false`

AWS EC2에서는 `ENABLE_SSM_SETTINGS=true`를 켜면 `/agents-invest/kill-switch`와 주요 리스크 한도가 환경값 위에 덮어써집니다. `live` 모드에서는 SSM 로딩 실패도 시작 차단 사유입니다.

## 원본 가져오기와 자동 연결

### GitHub Actions에서 실행

로컬 Git 경로 문제가 있으면 GitHub에서 수동 워크플로를 실행합니다.

1. 저장소의 `Actions` 탭으로 이동합니다.
2. `integrate-prism-insight` 워크플로를 선택합니다.
3. `Run workflow`를 실행합니다.
4. 결과 브랜치 `integrate-prism-insight`를 확인합니다.
5. 테스트가 통과하면 PR 또는 main 병합을 진행합니다.

자동 패치는 다음 원본 파일에 보완을 연결합니다.

- `prism-insight/trigger_batch.py`
- `prism-insight/stock_tracking_agent.py`
- `prism-insight/cores/agents/trading_agents.py`

### 로컬에서 실행

Windows PowerShell:

```powershell
.\scripts\integrate_prism_insight.ps1
python scripts\patch_prism_adapters.py
python scripts\check_integration.py
```

Linux/macOS/AWS EC2:

```bash
bash scripts/integrate_prism_insight.sh
python scripts/patch_prism_adapters.py
python scripts/check_integration.py
```

## AWS 24시간 운영

초기 운영은 EC2 `paper` 모드를 권장합니다.

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
python scripts/configure_telegram.py --target ssm --region ap-southeast-2
sudo REPO_URL=https://github.com/kdk212/agents_invest.git \
  AWS_REGION=ap-southeast-2 \
  RUNTIME_MODE=paper \
  bash deploy/aws/bootstrap_ec2_ubuntu.sh
```

AWS 콘솔에서 직접 확인할 항목은 [AWS 콘솔 설정 체크리스트](docs/AWS_CONSOLE_CHECKLIST_ko.md)를 따릅니다. 자세한 EC2 절차는 [AWS EC2 24시간 실행 가이드](docs/AWS_EC2_SETUP_ko.md)를 따릅니다.

## 적용 방향

1. PRISM-INSIGHT 원본을 별도 작업 경로에 준비합니다.
2. [원본 병합 플레이북](docs/UPSTREAM_MERGE_PLAYBOOK_ko.md)에 따라 원본을 병합합니다.
3. `python scripts/patch_prism_adapters.py`로 세 원본 파일에 보완 어댑터를 자동 연결합니다.
4. 자동 패치가 실패하면 [어댑터 연결 가이드](docs/ADAPTER_WIRING_GUIDE_ko.md)에 따라 수동 연결합니다.
5. 페이퍼트레이딩 결과를 `PaperTradingValidator`로 검증합니다.
6. 검증 기준을 통과한 뒤 [AWS 24시간 운영 초안](docs/AWS_24H_OPERATION_ko.md)에 따라 배포합니다.

## 주요 문서

- [Telegram 알림 설정](docs/TELEGRAM_SETUP_ko.md)
- [PRISM-INSIGHT 에이전트별 보완 매트릭스](docs/AGENT_ENHANCEMENT_MATRIX_ko.md)
- [PRISM-INSIGHT 보완 구현 지도](docs/IMPLEMENTATION_MAP_ko.md)
- [어댑터 연결 가이드](docs/ADAPTER_WIRING_GUIDE_ko.md)
- [원본 병합 플레이북](docs/UPSTREAM_MERGE_PLAYBOOK_ko.md)
- [AWS 콘솔 설정 체크리스트](docs/AWS_CONSOLE_CHECKLIST_ko.md)
- [AWS EC2 24시간 실행 가이드](docs/AWS_EC2_SETUP_ko.md)
- [AWS 24시간 운영 초안](docs/AWS_24H_OPERATION_ko.md)
- [PRISM-INSIGHT 라이선스 고지](docs/LICENSING_NOTICE_ko.md)

## 주의

실계좌 자동매매는 충분한 페이퍼트레이딩, 손실 한도, 모니터링, 비상 정지 장치가 준비된 뒤에만 켜야 합니다.

PRISM-INSIGHT는 AGPL-3.0 및 상업 라이선스 조건이 있으므로, 외부 제공 서비스나 SaaS 형태로 운영할 경우 원저작자 라이선스 조건을 별도로 확인해야 합니다.
