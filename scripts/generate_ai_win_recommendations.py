#!/usr/bin/env python3
"""Generate AI WIN style recommendations without KRX direct login.

This is a fallback route for days when the PRISM/KRX direct-login batch is stuck.
It uses FinanceDataReader public data when available, scores liquid Korean stocks
with the ai_win_invest momentum/risk formula, and writes the same dashboard JSON
shape as PRISM so the dashboard can show fresh candidates.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dashboard" / "prism_latest_morning.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI WIN fallback recommendations")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--universe-size", type=int, default=220)
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "FinanceDataReader_missing",
                    "next_action": ".venv/bin/python -m pip install finance-datareader",
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
                ensure_ascii=False,
            )
        )
        return 2

    as_of = _parse_date(args.as_of_date) if args.as_of_date else date.today()
    start = as_of - timedelta(days=430)
    listing = _load_listing(fdr)
    if listing.empty:
        print(json.dumps({"ok": False, "reason": "listing_unavailable"}, ensure_ascii=False))
        return 2

    tickers = _select_universe(listing, args.universe_size)
    rows = []
    for ticker in tickers:
        try:
            df = fdr.DataReader(ticker, start.strftime("%Y-%m-%d"), as_of.strftime("%Y-%m-%d"))
            row = _score_ticker(ticker, df, listing)
        except Exception:
            row = None
        if row:
            rows.append(row)

    if not rows:
        print(json.dumps({"ok": False, "reason": "no_candidates"}, ensure_ascii=False))
        return 2

    frame = pd.DataFrame(rows).set_index("code")
    scored = _score_frame(frame).sort_values("ai_win_score", ascending=False).head(args.top_n)
    payload_rows = []
    for rank, (ticker, row) in enumerate(scored.iterrows(), 1):
        latest = float(row["current_price"])
        stop_pct = min(max(float(row["daily_risk"]) * math.sqrt(5) * 2.5, 0.045), 0.18)
        target_pct = 0.30
        payload_rows.append(
            {
                "rank": rank,
                "code": ticker,
                "name": row.get("name") or ticker,
                "trigger_type": "AI WIN 공개데이터 모멘텀 상위주",
                "current_price": round(latest, 0),
                "change_rate": round(float(row.get("mom20", 0.0)) * 100, 2),
                "profit_score": round(float(row["ai_win_score_100"]), 2),
                "adaptive_profit_score": round(float(row["ai_win_score_100"]), 2),
                "ai_win_score": round(float(row["ai_win_score"]), 4),
                "ai_win_score_100": round(float(row["ai_win_score_100"]), 2),
                "forward_quality_score": round(float(row["forward_quality_score"]), 4),
                "stop_loss_pct": round(stop_pct * 100, 2),
                "stop_loss_price": round(latest * (1 - stop_pct), 0),
                "target_price": round(latest * (1 + target_pct), 0),
                "take_profit_trigger_pct": 30.0,
                "take_profit_trailing_pct": 10.0,
                "source": "ai_win_public_fallback",
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "trigger_mode": "morning",
            "trade_date": as_of.strftime("%Y%m%d"),
            "source": "ai_win_public_fallback",
            "note": "KRX 직접 로그인 실패 시 공개 데이터 기반 AI WIN 후보를 우선 표시",
            "adaptive_strategy": {
                "status": "fallback_generated",
                "enhanced_count": len(payload_rows),
                "source": "ai_win_public_fallback",
            },
        },
        "AI WIN 공개데이터 모멘텀 상위주": payload_rows,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "candidates": len(payload_rows)}, ensure_ascii=False, indent=2))
    return 0


def _load_listing(fdr) -> pd.DataFrame:
    try:
        listing = fdr.StockListing("KRX")
    except Exception:
        return pd.DataFrame()
    if listing.empty:
        return listing
    listing["Code"] = listing["Code"].astype(str).str.zfill(6)
    return listing.set_index("Code", drop=False)


def _select_universe(listing: pd.DataFrame, universe_size: int) -> list[str]:
    filtered = listing.copy()
    if "Market" in filtered.columns:
        filtered = filtered[filtered["Market"].isin(["KOSPI", "KOSDAQ"])]
    sort_col = None
    for column in ("Amount", "Marcap", "MarketCap"):
        if column in filtered.columns:
            sort_col = column
            break
    if sort_col:
        filtered[sort_col] = pd.to_numeric(filtered[sort_col], errors="coerce")
        filtered = filtered.sort_values(sort_col, ascending=False)
    return filtered.index.astype(str).str.zfill(6)[:universe_size].tolist()


def _score_ticker(ticker: str, df: pd.DataFrame, listing: pd.DataFrame) -> dict[str, Any] | None:
    if df is None or df.empty or len(df) < 130 or "Close" not in df.columns:
        return None
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(close) < 130:
        return None
    volume = pd.to_numeric(df.get("Volume", pd.Series(index=df.index, data=0)), errors="coerce").fillna(0)
    trading_value = close.reindex(volume.index).ffill() * volume
    latest = float(close.iloc[-1])
    daily = close.pct_change(fill_method=None)
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    peak20 = close.tail(20).max()
    trough20 = close.tail(20).min()
    peak60 = close.tail(60).max()
    mom20 = latest / close.iloc[-21] - 1
    mom60 = latest / close.iloc[-61] - 1
    mom120 = latest / close.iloc[-121] - 1
    trend = latest / ma60 - 1 + (ma20 / ma60 - 1)
    vol60 = float(daily.tail(60).std() * math.sqrt(252))
    hit20 = float((daily.tail(20) > 0).mean())
    pullback_resilience = float(latest / peak20 - trough20 / peak20) if peak20 else 0.0
    acceleration = float(mom20 - (mom60 - mom20) / 2)
    drawdown = float(latest / peak60 - 1) if peak60 else 0.0
    overextension = float(latest / ma20 - 1) if ma20 else 0.0
    risk_score = vol60 + max(0.0, -drawdown) + max(0.0, overextension - 0.18)
    turnover_change = float(trading_value.tail(5).mean() / trading_value.tail(60).mean() - 1) if trading_value.tail(60).mean() else 0.0
    name = ticker
    if ticker in listing.index:
        name = str(listing.loc[ticker].get("Name") or ticker)
    return {
        "code": ticker,
        "name": name,
        "current_price": latest,
        "mom20": float(mom20),
        "mom60": float(mom60),
        "mom120": float(mom120),
        "trend": float(trend),
        "vol60": vol60,
        "hit20": hit20,
        "pullback_resilience": pullback_resilience,
        "acceleration": acceleration,
        "turnover_change": turnover_change,
        "drawdown_from_60d_peak": drawdown,
        "risk_score": float(risk_score),
        "daily_risk": float(daily.tail(20).std()),
    }


def _score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.replace([np.inf, -np.inf], np.nan).copy()
    out["forward_quality_score"] = (
        0.22 * _zscore(out["hit20"])
        + 0.18 * _zscore(out["pullback_resilience"])
        + 0.18 * _zscore(out["acceleration"])
        + 0.12 * _zscore(out["turnover_change"].clip(-1, 5))
        - 0.22 * _zscore(out["risk_score"])
        - 0.18 * _zscore(out["drawdown_from_60d_peak"].abs())
    )
    out["ai_win_score"] = (
        0.20 * _zscore(out["mom20"])
        + 0.30 * _zscore(out["mom60"])
        + 0.20 * _zscore(out["mom120"])
        + 0.15 * _zscore(out["trend"])
        - 0.15 * _zscore(out["vol60"])
        + out["forward_quality_score"]
    )
    out["ai_win_score_100"] = (out["ai_win_score"].rank(pct=True) * 100).clip(0, 100)
    return out


def _zscore(series: pd.Series) -> pd.Series:
    clean = series.replace([np.inf, -np.inf], np.nan)
    std = clean.std(skipna=True)
    if std is None or pd.isna(std) or math.isclose(float(std), 0.0):
        return pd.Series(0.0, index=series.index)
    return (clean - clean.mean(skipna=True)) / std


def _parse_date(value: str) -> date:
    return pd.to_datetime(value).date()


if __name__ == "__main__":
    raise SystemExit(main())
