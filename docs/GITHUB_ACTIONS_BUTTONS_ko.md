# GitHub Actions 버튼 확인 순서

이 문서는 `Run workflow` 버튼이 보이지 않거나 workflow가 하나도 제대로 실행되지 않을 때 확인하는 순서입니다.

## 1. 먼저 확인할 workflow

Actions 화면에서 왼쪽 목록의 `00-run-this-first`를 먼저 확인합니다.

주소:

https://github.com/kdk212/agents_invest/actions

`00-run-this-first`는 AWS, Python, 외부 설치를 전혀 사용하지 않습니다. 그래서 이 workflow도 보이지 않거나 `Run workflow` 버튼이 없으면 코드 문제가 아니라 GitHub 저장소 설정 문제일 가능성이 큽니다.

## 2. GitHub 저장소 설정

GitHub 저장소에서 아래로 이동합니다.

`Settings` -> `Actions` -> `General`

다음 값을 확인합니다.

- `Actions permissions`: `Allow all actions and reusable workflows`
- `Workflow permissions`: `Read and write permissions`
- `Allow GitHub Actions to create and approve pull requests`: 필요 시 체크

저장 후 Actions 화면을 새로고침합니다.

## 3. 버튼이 보여야 하는 workflow

다음 workflow는 수동 실행 버튼이 있어야 합니다.

- `00-run-this-first`
- `manual-health-check`
- `manual-ec2-repair`
- `prism-import-simple`

## 4. 먼저 실행할 순서

1. `00-run-this-first`
2. `manual-health-check`
3. `manual-ec2-repair`

`manual-ec2-repair`는 AWS 권한 시크릿이 필요합니다.

필요한 GitHub Secret:

```text
AWS_GITHUB_ACTIONS_ROLE_ARN
```

이 값이 없으면 버튼은 보여도 AWS 연결 단계에서 실패할 수 있습니다.

## 5. EC2 직접 수리 명령

GitHub Actions가 아직 안 되면 EC2 Session Manager에서 직접 실행합니다.

```bash
cd /opt/agents_invest
git pull
sudo RUN_PRISM_ONCE=true bash deploy/aws/repair_and_verify_ec2.sh
bash scripts/operator_status.sh
```

정상에 가까운 상태는 아래와 같습니다.

```text
OK   PRISM import smoke check: ready=true
OK   agents-invest service active
OK   nginx active
OK   local dashboard HTTP works
```

PRISM 실행 실패가 남으면 아래 로그를 붙여넣습니다.

```bash
cd /opt/agents_invest
sudo journalctl -u agents-invest -n 120 --no-pager
cat dashboard/runtime_status.json
```
