# 런타임 비밀값 로딩

`agents_invest`는 비밀값 원문을 로그에 출력하지 않습니다. 로컬에서는 env 파일을 읽고, AWS EC2에서는 Parameter Store의 SecureString 값을 읽어 표준 환경변수로 올립니다.

## 로컬 실행

기본 경로는 `config/runtime.env`입니다.

```text
OPENAI_API_KEY=...
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

기본 경로를 쓰기 어려우면 `AGENTS_INVEST_ENV_FILE`로 별도 파일을 지정합니다.

```powershell
$env:AGENTS_INVEST_ENV_FILE="C:\Users\kdk21\.codex\memories\agents_invest_runtime.env"
python -m runtime.preflight --json
```

## AWS EC2 실행

EC2에서는 `config/runtime.env`에 다음 값이 있어야 합니다.

```text
ENABLE_SSM_SETTINGS=true
SSM_PARAMETER_PREFIX=/agents-invest
AWS_REGION=ap-southeast-2
```

이 상태에서 런타임은 다음 SecureString 값을 읽어 환경변수로 주입합니다.

```text
/agents-invest/openai/api-key      -> OPENAI_API_KEY
/agents-invest/kis/app-key         -> KIS_APP_KEY
/agents-invest/kis/app-secret      -> KIS_APP_SECRET
/agents-invest/kis/account-no      -> KIS_ACCOUNT_NO
/agents-invest/telegram/bot-token  -> TELEGRAM_BOT_TOKEN
/agents-invest/telegram/chat-id    -> TELEGRAM_CHAT_ID
```

`CHANGE_ME` 값은 비어 있는 값처럼 취급되어 주입하지 않습니다.

## 확인

프리플라이트는 값이 아니라 변수명과 존재 여부만 보여줍니다.

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

`missing_env_names`에 값이 있어도 paper 모드 자체를 무조건 막지는 않습니다. 다만 OpenAI, KIS, Telegram 실제 연동을 사용하기 전에는 필요한 변수들이 모두 `loaded_env_names` 또는 `secret_env_present`에 있어야 합니다.

## 주의

- API 키, 토큰, 계좌번호 원문은 채팅이나 GitHub에 붙여넣지 않습니다.
- `config/runtime.env`와 `.env` 파일은 커밋하지 않습니다.
- AWS에서는 SecureString으로 저장하고 EC2 Role에는 런타임 IAM 정책만 연결합니다.
