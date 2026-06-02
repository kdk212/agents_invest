# agents_invest 지금 여기서 시작

현재 목표는 PRISM-INSIGHT 원본 에이전트를 가져와서 agents_invest 보완 계층을 붙이고, AWS EC2에서 24시간 paper 모드로 돌리는 것입니다.

수익은 보장할 수 없습니다. 먼저 paper 모드에서 후보 추출, Telegram 알림, 대시보드, 서비스 재시작까지 확인한 뒤 live 전환을 검토합니다.

## 1. GitHub Actions 버튼 확인

먼저 아래 주소로 갑니다.

https://github.com/kdk212/agents_invest/actions

왼쪽 workflow 목록에서 이것만 찾습니다.

```text
00-run-this-first
```

이 workflow는 AWS, Python, OpenAI, Telegram을 전혀 사용하지 않습니다. 버튼 확인 전용입니다.

### 보이면

`00-run-this-first`를 클릭하고 `Run workflow` 버튼을 누릅니다.

성공하면 다음으로 `manual-health-check`를 실행합니다.

### 안 보이면

코드 문제가 아니라 GitHub 저장소 설정 문제입니다.

GitHub 저장소에서 아래로 이동합니다.

```text
Settings -> Actions -> General
```

다음처럼 설정합니다.

```text
Actions permissions
-> Allow all actions and reusable workflows

Workflow permissions
-> Read and write permissions
```

저장 후 Actions 화면을 새로고침합니다.

## 2. GitHub Actions 실행 순서

버튼이 보이면 이 순서로만 실행합니다.

```text
1. 00-run-this-first
2. manual-health-check
3. manual-ec2-repair
```

`manual-ec2-repair`는 AWS 연결용이라 GitHub Secret이 필요합니다.

```text
AWS_GITHUB_ACTIONS_ROLE_ARN
```

이 값이 없으면 버튼은 보여도 AWS 권한 단계에서 실패할 수 있습니다.

## 3. GitHub Actions가 아직 안 되면 EC2에서 직접 실행

EC2 Session Manager에서 아래를 그대로 실행합니다.

```bash
cd /opt/agents_invest
git pull
sudo systemctl restart agents-invest
sleep 5
bash scripts/operator_status.sh
```

서비스가 아직 정리되지 않았거나 PRISM 재설치까지 필요하면 아래를 실행합니다.

```bash
cd /opt/agents_invest
git pull
sudo RUN_PRISM_ONCE=true bash deploy/aws/repair_and_verify_ec2.sh
bash scripts/operator_status.sh
```

## 4. 정상에 가까운 상태

아래가 보이면 설치와 웹은 정상에 가깝습니다.

```text
OK   PRISM import smoke check: ready=true
OK   agents-invest service active
OK   nginx active
OK   local dashboard HTTP works
```

대시보드 주소:

```text
http://13.55.135.136/
```

## 5. 아직 실패하면 붙여넣을 로그

아래 명령 결과를 붙여넣습니다.

```bash
cd /opt/agents_invest
sudo journalctl -u agents-invest -n 120 --no-pager
cat dashboard/runtime_status.json
bash scripts/operator_status.sh
```

이 로그가 있으면 다음 패치 위치를 바로 잡을 수 있습니다.
