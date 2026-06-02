"""Send a safe Telegram smoke-test message using runtime secrets.

This verifies that TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are present and that
Telegram accepts the message. Secret values are never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from runtime import load_runtime_secrets, load_runtime_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send agents_invest Telegram test alert")
    parser.add_argument("--message", default="agents_invest Telegram test: 알림 연결 확인", help="message text to send")
    parser.add_argument("--json", action="store_true", help="print JSON result")
    args = parser.parse_args(argv)

    settings = load_runtime_settings()
    secret_result = load_runtime_secrets(
        enabled=settings.ssm_settings_enabled,
        prefix=settings.ssm_parameter_prefix,
        region=settings.aws_region,
    )
    result = send_test_message(args.message)
    safe_result = {
        "settings_source": settings.settings_source,
        "secret_source": secret_result.source,
        "loaded_env_names": list(secret_result.loaded_env_names),
        "missing_env_names": list(secret_result.missing_env_names),
        "sent": result.get("sent", False),
        "status_code": result.get("status_code"),
        "reason": result.get("reason"),
    }

    if args.json:
        print(json.dumps(safe_result, ensure_ascii=False, indent=2))
    else:
        if safe_result["sent"]:
            print("Telegram test alert sent successfully.")
        else:
            print("Telegram test alert failed.")
            print(json.dumps(safe_result, ensure_ascii=False, indent=2))
    return 0 if safe_result["sent"] else 2


def send_test_message(message: str) -> dict[str, object]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"sent": False, "reason": "telegram_secret_missing"}

    text = "\n".join(
        [
            message,
            f"time: {datetime.now().isoformat(timespec='seconds')}",
        ]
    )
    try:
        import requests

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True},
            timeout=15,
        )
        if response.ok:
            return {"sent": True, "status_code": response.status_code}
        return {
            "sent": False,
            "status_code": response.status_code,
            "reason": response.text[-500:],
        }
    except Exception as exc:
        return {"sent": False, "reason": f"{exc.__class__.__name__}: {exc}"}


if __name__ == "__main__":
    raise SystemExit(main())