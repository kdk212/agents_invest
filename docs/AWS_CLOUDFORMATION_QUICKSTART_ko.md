# AWS CloudFormation 빠른 배포

이 문서는 `agents_invest`를 AWS `ap-southeast-2` EC2에서 24시간 paper 모드로 실행하고, 진행상황 대시보드를 여는 빠른 경로입니다.

## 1. 스택 만들기

AWS 콘솔에서 다음 위치로 이동합니다.

```text
CloudFormation > Stacks > Create stack > With new resources
```

템플릿 파일은 저장소의 다음 파일을 사용합니다.

```text
deploy/aws/cloudformation_agents_invest_ec2.yml
```

주요 입력값:

- `GitHubRepoOwner`: `kdk212`
- `GitHubRepoName`: `agents_invest`
- `GitHubBranch`: `main`
- `GitHubToken`: 저장소가 private이면 clone 권한이 있는 토큰을 입력합니다. public이면 비워둡니다.
- `InstanceType`: 처음에는 `t3.small` 권장
- `AdminCidr`: 본인 IP만 허용하는 값 권장. 예: `123.123.123.123/32`
- `DashboardPort`: `80`
- `SsmParameterPrefix`: `/agents-invest`

`GitHubToken`은 `NoEcho` 값으로 받습니다. GitHub에 커밋하지 않고, EC2가 private 저장소를 내려받을 때만 사용합니다.

## 2. 생성 후 대시보드 주소 확인

스택 생성이 끝나면 CloudFormation 스택의 `Outputs` 탭을 봅니다.

```text
DashboardUrl
PublicIp
```

`http://EC2_PUBLIC_IP/`에서 `EC2_PUBLIC_IP`는 실제 값이 아닙니다. `Outputs`의 `PublicIp` 값으로 바꿔야 합니다.

예:

```text
PublicIp = 13.211.10.20
DashboardUrl = http://13.211.10.20:80/
```

포트가 80이면 브라우저에서는 다음처럼 열어도 됩니다.

```text
http://13.211.10.20/
```

## 3. 비밀값 입력

CloudFormation은 기본 운영 설정만 만듭니다. OpenAI, KIS, Telegram 원문 값은 직접 AWS Systems Manager Parameter Store의 SecureString으로 입력합니다.

입력 위치:

```text
Systems Manager > Parameter Store
```

필요한 SecureString 이름:

```text
/agents-invest/openai/api-key
/agents-invest/kis/app-key
/agents-invest/kis/app-secret
/agents-invest/kis/account-no
/agents-invest/telegram/bot-token
/agents-invest/telegram/chat-id
```

Telegram은 사용자가 토큰과 chat id를 입력할 수 있게 되어 있습니다. OpenAI 키도 같은 위치에 넣으면 EC2 런타임이 읽습니다.

## 4. 안전 운영

처음에는 반드시 paper 모드입니다.

```text
/agents-invest/trading-mode = paper
/agents-invest/paper-validation-approved = false
/agents-invest/kill-switch = false
```

즉시 멈추고 싶으면 다음 값을 true로 바꿉니다.

```text
/agents-invest/kill-switch = true
```

실계좌 live 전환은 PRISM 통합 PR, paper 검증, Telegram 알림, RiskGovernor, Kill Switch 동작 확인이 끝난 뒤에만 진행합니다.

## 5. 상태 확인

EC2 콘솔에서 인스턴스를 선택하면 `Public IPv4 address`가 보입니다. 그 값이 대시보드 주소의 IP입니다.

서버 내부 상태는 Session Manager 또는 SSH로 접속한 뒤 확인합니다.

```bash
sudo systemctl status agents-invest --no-pager
sudo journalctl -u agents-invest -f
```
