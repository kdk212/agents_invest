#!/usr/bin/env python3
"""Generate OpenAI risk summaries for dashboard recommendations.

Reads current morning/afternoon recommendation JSON files, asks the OpenAI
Responses API for concise Korean risk notes, and writes
`dashboard/recommendation_risks.json`. The API key is loaded from environment or
config/runtime.env without printing secret values.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
RISK_OUTPUT = DASHBOARD / "recommendation_risks.json"
RUNTIME_ENV = ROOT / "config" / "runtime.env"


def main() -> int:
    load_runtime_env()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        write_error("OPENAI_API_KEY_missing", "OpenAI API 키가 설정되어 있지 않아 리스크 요약을 만들지 못했습니다.")
        return 2

    candidates = load_candidates()
    if not candidates:
        write_error("no_candidates", "추천 후보가 없어 리스크 요약을 만들지 못했습니다.")
        return 2

    prompt = build_prompt(candidates[:10])
    try:
        result_text, sources = call_openai(key, prompt)
        risks = parse_json_text(result_text)
    except Exception as exc:
        write_error(exc.__class__.__name__, str(exc))
        return 2

    payload = {
        "ok": True,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "openai_responses_web_search",
        "model": os.environ.get("OPENAI_RISK_MODEL", "gpt-5"),
        "note": "LLM 리스크 요약은 투자 판단 보조 정보이며 수익을 보장하지 않습니다.",
        "risks": risks.get("risks", risks if isinstance(risks, list) else []),
        "sources": sources[:20],
    }
    RISK_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(RISK_OUTPUT), "count": len(payload["risks"])}, ensure_ascii=False, indent=2))
    return 0


def load_runtime_env() -> None:
    if not RUNTIME_ENV.exists():
        return
    for raw in RUNTIME_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")


def load_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode, path in (("오전", DASHBOARD / "prism_latest_morning.json"), ("오후", DASHBOARD / "prism_latest_afternoon.json")):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("metadata", {})
        for key, value in data.items():
            if key == "metadata" or not isinstance(value, list):
                continue
            for item in value:
                code = str(item.get("code") or item.get("ticker") or "").zfill(6)
                if not code:
                    continue
                rows.append({
                    "session": mode,
                    "code": code,
                    "name": item.get("name") or item.get("company_name") or code,
                    "score": item.get("ai_win_score_100") or item.get("adaptive_profit_score") or item.get("profit_score"),
                    "change_rate": item.get("change_rate"),
                    "basis": meta.get("signal_basis") or item.get("signal_basis"),
                    "signal_at": meta.get("signal_at") or meta.get("trade_date"),
                })
    deduped: list[dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (row["session"], row["code"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_prompt(candidates: list[dict[str, Any]]) -> str:
    return (
        "한국 주식 추천 후보의 최근 리스크를 투자 보조용으로 요약해 주세요. "
        "가능하면 최신 웹 정보를 확인하고, 과장하지 말고 불확실하면 불확실하다고 쓰세요. "
        "각 종목마다 JSON만 반환하세요. 형식: "
        "{\"risks\":[{\"code\":\"000000\",\"name\":\"회사명\",\"session\":\"오전\","
        "\"risk_level\":\"낮음|보통|높음\",\"summary\":\"한 문장\","
        "\"risk_factors\":[\"요인1\",\"요인2\",\"요인3\"],\"watch\":\"확인할 것\"}]}\n\n"
        f"추천 후보:\n{json.dumps(candidates, ensure_ascii=False)}"
    )


def call_openai(key: str, prompt: str) -> tuple[str, list[dict[str, str]]]:
    model = os.environ.get("OPENAI_RISK_MODEL", "gpt-5")
    body = {
        "model": model,
        "reasoning": {"effort": "low"},
        "tools": [{"type": "web_search", "user_location": {"type": "approximate", "country": "KR", "timezone": "Asia/Seoul"}}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "input": prompt,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:800]
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc

    text_parts: list[str] = []
    sources: list[dict[str, str]] = []
    for item in data.get("output", []):
        action = item.get("action") or {}
        for source in action.get("sources", []) or []:
            sources.append({"title": source.get("title") or "", "url": source.get("url") or ""})
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text_parts.append(content.get("text") or "")
                for ann in content.get("annotations", []) or []:
                    if ann.get("type") == "url_citation":
                        sources.append({"title": ann.get("title") or "", "url": ann.get("url") or ""})
    return "\n".join(text_parts).strip(), dedupe_sources(sources)


def parse_json_text(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def dedupe_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    seen = set()
    for source in sources:
        url = source.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(source)
    return out


def write_error(reason: str, detail: str) -> None:
    payload = {"ok": False, "updated_at": datetime.now().isoformat(timespec="seconds"), "reason": reason, "detail": detail, "risks": []}
    RISK_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
