# OpenAI/KIS/Telegram 비밀값 입력

이 문서는 `scripts/configure_runtime_secrets.py`로 런타임 비밀값을 안전하게 입력하는 절차입니다.

원문 키, 토큰, 계좌번호는 채팅이나 GitHub에 붙여넣지 않습니다. 이 도구는 입력값을 화면에 다시 보여주지 않고, 저장 위치와 변수명만 출력합니다.

## 저장되는 값

```text
OPENAI_API_KEY                  -> /agents-invest/openai/api-key
KIS_APP_KEY                     -> /agents-invest/kis/app-key
KIS_APP_SECRET                  -> /agents-invest/kis/app-secret
KIS_ACCOUNT_NO                  -> /agents-invest/kis/account-no
TELEGRAM_BOT_TOKEN              -> /agents-invest/telegram/bot-token
TELEGRAM_CHAT_ID                -> /agents-invest/telegram/chat-id
```

## 로컬 paper 실행용

로컬에서 먼저 paper 모드로 확인할 때 사용합니다.

```bash
python scripts/configure_runtime_secrets.py --target local
```

기본 저장 위치는 `config/runtime.env`입니다. 이 파일은 GitHub에 커밋하지 않습니다.

다른 위치에 저장하려면 다음처럼 실행합니다.

```bash
python scripts/configure_runtime_secrets.py --target local --env-path /safe/path/runtime.env
```

Windows에서 현재 준비된 OpenAI 키 파일을 사용할 때는 다음 환경변수를 지정합니다.

```powershell
$env:AGENTS_INVEST_ENV_FILE="C:\Users\kdk21\.codex\memories\agents_invest_runtime.env"
python -m runtime.preflight --json
```

## AWS EC2 24시간 실행용

AWS `ap-southeast-2`의 Systems Manager Parameter Store에 SecureString으로 저장합니다.

```bash
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2
```

로컬 env와 AWS SSM에 동시에 저장하려면 다음처럼 실행합니다.

```bash
python scripts/configure_runtime_secrets.py --target both --region ap-southeast-2
```

## 환경변수에서 읽어 자동 저장

CI, EC2 접속 세션, 또는 이미 안전한 환경변수에 값이 들어 있는 경우에는 대화식 입력 없이 저장할 수 있습니다.

```bash
OPENAI_API_KEY="..." \
TELEGRAM_BOT_TOKEN="..." \
TELEGRAM_CHAT_ID="..." \
python scripts/configure_runtime_secrets.py --target ssm --region ap-southeast-2 --non-interactive
```

`--non-interactive` 기본값에서는 `OPENAI_API_KEY`가 필수입니다. 모든 지원 값을 반드시 요구하려면 `--include-optional-empty`를 함께 사용합니다.

## 확인

값 자체가 아니라 존재 여부만 확인합니다.

```bash
python -m runtime.preflight --json
```

확인할 항목:

```text
secret_check.ok
secret_check.loaded_env_names
secret_check.missing_env_names
secret_env_present
```

## 주의

- `CHANGE_ME` 값은 실제 비밀값으로 취급하지 않습니다.
- AWS에서는 SecureString으로 저장합니다.
- EC2에는 `deploy/aws/iam_policy_agents_invest_runtime.json`의 런타임 권한만 연결합니다.
- 처음에는 반드시 `paper` 모드로 실행합니다.
