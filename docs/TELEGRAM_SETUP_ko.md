# Telegram 알림 설정

Telegram 토큰과 chat id는 채팅창이나 GitHub 파일에 직접 붙여넣지 않습니다. 아래 도구로 로컬 설정 파일 또는 AWS Systems Manager Parameter Store에 입력합니다.

## 로컬 paper 실행

저장소 루트에서 실행합니다.

```bash
python scripts/configure_telegram.py --target local
```

입력값:

- `Telegram bot token`: BotFather에서 받은 토큰입니다. 입력 중 화면에 표시되지 않습니다.
- `Telegram chat id`: 알림을 받을 개인/그룹 chat id입니다.

도구는 `config/runtime.env`에 다음 값을 저장합니다.

```text
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

`config/runtime.env`는 커밋하지 않습니다.

## AWS EC2 24시간 실행

EC2 또는 AWS CLI가 설정된 터미널에서 실행합니다.

```bash
python scripts/configure_telegram.py --target ssm --region ap-southeast-2
```

도구는 값을 SecureString으로 저장합니다.

```text
/agents-invest/telegram/bot-token
/agents-invest/telegram/chat-id
```

로컬 파일과 AWS Parameter Store를 한 번에 넣고 싶으면 다음처럼 실행합니다.

```bash
python scripts/configure_telegram.py --target both --region ap-southeast-2
```

## 자동 입력이 필요한 경우

터미널 기록에 토큰이 남지 않도록 명령 인자로 토큰을 받지 않습니다. CI나 서버 자동화가 꼭 필요하면 환경변수로만 전달합니다.

```bash
TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." \
  python scripts/configure_telegram.py --target ssm --non-interactive
```

## 확인

AWS 콘솔에서는 다음 위치에서 값이 `SecureString`으로 저장됐는지만 확인합니다. 실제 값은 화면에 오래 노출하지 않습니다.

```text
Systems Manager > Parameter Store > /agents-invest/telegram/bot-token
Systems Manager > Parameter Store > /agents-invest/telegram/chat-id
```

알림 테스트는 실제 PRISM-INSIGHT Telegram 발송 로직이 병합된 뒤 paper 모드에서 먼저 확인합니다. 확인 전에는 `live` 모드로 전환하지 않습니다.
