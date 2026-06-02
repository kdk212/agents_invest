# 현재 다음 단계

이 문서는 `agents_invest`를 실제 24시간 paper 운영까지 가져가기 위한 현재 진행 순서입니다.

현재 알려진 EC2:

```text
Instance ID: i-08bdbe63b2db7880f
Public IPv4: 13.55.135.136
Region: ap-southeast-2
```

## 1. AWS 접속 복구

현재 가장 먼저 해결할 일은 Session Manager 접속입니다.

보이는 오류:

```text
SSM Agent unable to acquire credentials
Ping status: Offline
Session Manager connection status: Not connected
```

가장 쉬운 방법은 아래 문서의 긴 명령 블록을 CloudShell에 그대로 붙여넣는 것입니다.

```text
docs/CLOUDSHELL_COPY_PASTE_SSM_ROLE_COMMAND_ko.md
```

이 방식은 저장소가 private이어도 raw 다운로드가 필요 없습니다.

저장소가 public이면 아래 두 줄도 사용할 수 있습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/kdk212/agents_invest/main/deploy/aws/cloudshell_attach_ssm_role.sh -o /tmp/cloudshell_attach_ssm_role.sh
bash /tmp/cloudshell_attach_ssm_role.sh
```

그 다음 EC2를 재부팅합니다.

```bash
aws ec2 reboot-instances --region ap-southeast-2 --instance-ids i-08bdbe63b2db7880f
```

복붙용 명령 문서는 마지막에 재부팅까지 같이 실행합니다.

2-5분 기다린 뒤 확인합니다.

```text
EC2 > Instances > i-08bdbe63b2db7880f > Connect > Session Manager
```

정상 목표:

```text
Ping status: Online
```

자세한 문서:

```text
docs/CLOUDSHELL_COPY_PASTE_SSM_ROLE_COMMAND_ko.md
docs/CLOUDSHELL_ATTACH_SSM_ROLE_ko.md
docs/SSM_SESSION_MANAGER_TROUBLESHOOTING_ko.md
```

## 2. GitHub에서 PRISM 원본 통합 실행

현재 원격 저장소에는 아직 아래가 없습니다.

```text
integrate-prism-insight 브랜치
PRISM 통합 draft PR
```

GitHub에서 수동 실행합니다.

```text
GitHub > kdk212/agents_invest > Actions > integrate-prism-insight > Run workflow
```

값은 기본값 그대로 둡니다.

```text
upstream_url=https://github.com/dragon1086/prism-insight.git
upstream_branch=main
target_branch=integrate-prism-insight
```

성공하면 다음이 생겨야 합니다.

```text
Code > Branches > integrate-prism-insight
Pull requests > Draft PR
```

실패하면 실패한 step 이름과 빨간 오류 20-40줄만 확인합니다.

자세한 문서:

```text
docs/GITHUB_ACTIONS_PRISM_INTEGRATION_ko.md
```

## 3. Session Manager가 Online 된 뒤 EC2 설치

EC2 안에서 실행합니다. CloudShell이 아닙니다.

```bash
sudo apt-get update
sudo apt-get install -y git

git clone https://github.com/kdk212/agents_invest.git
cd agents_invest
```

저장소가 private이면 일반 clone이 실패할 수 있습니다. 이 경우 GitHub token을 사용하거나 저장소를 임시로 public으로 바꿉니다.

운영 기본값 생성:

```bash
AWS_REGION=ap-southeast-2 bash deploy/aws/put_default_parameters.sh
```

OpenAI/KIS/Telegram 비밀값 입력:

```bash
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
```

서버 설치:

```bash
sudo REPO_URL=https://github.com/kdk212/agents_invest.git \
  AWS_REGION=ap-southeast-2 \
  RUNTIME_MODE=paper \
  bash deploy/aws/bootstrap_ec2_ubuntu.sh
```

대시보드 설치:

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

대시보드 주소:

```text
http://13.55.135.136/
```

## 4. 절대 바로 live로 전환하지 않기

처음은 반드시 paper 모드입니다.

live 전환 전 필수 확인:

- PRISM 통합 PR 성공
- paper 모드에서 충분한 거래 수 확보
- `PaperTradingValidator` 통과
- Telegram 알림 수신 확인
- strict runtime preflight 통과
- Kill Switch 동작 확인
- RiskGovernor 차단 동작 확인
- KIS API 연결 확인

수익은 보장할 수 없습니다. 목표는 원본 PRISM 에이전트를 유지하면서, 수익 기대값 점수화와 위험 차단, 성과 피드백으로 무리한 매매를 줄이고 검증 가능한 자동화로 만드는 것입니다.
