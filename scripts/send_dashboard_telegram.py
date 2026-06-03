#!/usr/bin/env python3
"""Send dashboard recommendation and portfolio summary to Telegram."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
RUNTIME_ENV = ROOT / "config" / "runtime.env"


def main() -> int:
    load_runtime_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print(json.dumps({"ok": False, "reason": "telegram_secret_missing"}, ensure_ascii=False))
        return 2
    text = build_message()
    send_telegram(token, chat_id, text)
    print(json.dumps({"ok": True, "sent_chars": len(text)}, ensure_ascii=False))
    return 0


def load_runtime_env() -> None:
    if not RUNTIME_ENV.exists():
        return
    for raw in RUNTIME_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def rows_from_recommendation(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, value in data.items():
        if key == "metadata" or not isinstance(value, list):
            continue
        rows.extend(value)
    return rows


def price(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number:,.0f}"


def score(row: dict[str, Any]) -> str:
    for key in ("ai_win_score", "adaptive_profit_score", "profit_score"):
        try:
            return f"{float(row.get(key)):.2f}"
        except Exception:
            continue
    return "-"


def build_message() -> str:
    portfolio = read_json(DASHBOARD / "portfolio_status.json")
    history = read_json(DASHBOARD / "recommendation_history.json")
    latest = read_json(DASHBOARD / "prism_latest_morning.json")

    summary = portfolio.get("summary", {}) if isinstance(portfolio.get("summary"), dict) else {}
    lines = [
        "agents_invest 일간 요약",
        f"기간: {portfolio.get('start_date', '-')} ~ {portfolio.get('end_date', '-')}",
        f"포트폴리오: {summary.get('total_return_pct', '0.00%')} / 연환산 {summary.get('annualized_return_pct', '-')}",
        f"보유: {summary.get('open_positions', 0)}종목 · {summary.get('open_units', 0)}단위 · 매도신호 {summary.get('sell_signal_count', 0)}건",
        "",
    ]

    items = history.get("items") if isinstance(history.get("items"), list) else []
    if items:
        latest_item = items[-1]
        lines.append(f"최근 추천 후보 · {latest_item.get('date', '-')}")
        sections = latest_item.get("sections") if isinstance(latest_item.get("sections"), dict) else {}
        rec_rows = []
        for value in sections.values():
            if isinstance(value, list):
                rec_rows.extend(value)
    else:
        meta = latest.get("metadata", {}) if isinstance(latest.get("metadata"), dict) else {}
        lines.append(f"최근 추천 후보 · {meta.get('date_label') or meta.get('trade_date') or '-'}")
        rec_rows = rows_from_recommendation(latest)

    if rec_rows:
        for row in rec_rows[:7]:
            reason = row.get("recommendation_reason") or row.get("trigger_type") or "-"
            lines.append(
                f"- {row.get('code', '-')} {row.get('name', '-')} "
                f"AI {score(row)} · {reason} · "
                f"손절 {price(row.get('stop_loss_price'))} 목표 {price(row.get('target_price'))}"
            )
    else:
        lines.append("- 추천 후보 없음")

    lines.append("")
    lines.append("현재 보유 포트폴리오")
    holdings = portfolio.get("holdings") if isinstance(portfolio.get("holdings"), list) else []
    if holdings:
        for row in holdings[:8]:
            lines.append(f"- {row.get('ticker')} {row.get('company_name')} {row.get('return_pct', '0.00%')} · {row.get('units', 0)}단위")
    else:
        lines.append("- 보유 포지션 없음")

    lines.append("")
    lines.append("최근 매도 신호")
    sells = portfolio.get("sell_signals") if isinstance(portfolio.get("sell_signals"), list) else []
    if sells:
        for row in sells[-5:]:
            entries = row.get("entry_dates") or row.get("entry_date") or "-"
            if isinstance(entries, list):
                entries = ",".join(entries)
            lines.append(f"- {row.get('date')} {row.get('company_name')} {row.get('reason')} {row.get('realized_return_pct')} · 매수일 {entries}")
    else:
        lines.append("- 최근 매도 신호 없음")

    return "\n".join(lines)[:3900]


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


if __name__ == "__main__":
    raise SystemExit(main())
