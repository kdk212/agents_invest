"""pykrx-backed compatibility layer for PRISM's krx_data_client imports.

The upstream PRISM runtime imports ``krx_data_client`` and recent versions of
that package require KRX_ID/KRX_PW. EC2 paper operation should not depend on a
separate KRX direct-login account, so the PRISM import patch copies this module
into the imported ``prism-insight/`` checkout as ``krx_data_client.py``.
"""

from __future__ import annotations

import datetime as _dt
import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Any, Callable

import pandas as pd
import requests
from pykrx import stock

_MAX_BUSINESS_DAY_SEARCH_DAYS = 45
_MARKETS_FOR_ALL = ("KOSPI", "KOSDAQ", "KONEX")
_NAVER_TIMEOUT = 8
_NAVER_FALLBACK_TICKERS = (
    "005930", "000660", "373220", "207940", "005380", "005935", "000270", "068270",
    "105560", "035420", "012330", "055550", "028260", "012450", "032830", "086790",
    "051910", "006400", "035720", "003550", "066570", "015760", "034730", "017670",
    "096770", "010130", "009150", "018260", "033780", "030200", "259960", "000810",
    "316140", "003670", "011200", "010950", "090430", "024110", "086520", "247540",
    "091990", "028300", "196170", "277810", "263750", "293490", "041510", "035900",
    "058470", "112040", "005290", "145020", "068760", "357780", "214150", "403870",
)


def get_nearest_business_day_in_a_week(target_date: str, prev: bool = True) -> str:
    """Return the nearest KRX date that actually has public OHLCV data."""
    fallback_date = os.getenv("AGENTS_INVEST_FALLBACK_TRADE_DATE", "").strip()
    if fallback_date:
        return fallback_date

    base = _parse_date(target_date)
    step = -1 if prev else 1
    for offset in range(0, _MAX_BUSINESS_DAY_SEARCH_DAYS + 1):
        candidate = base + _dt.timedelta(days=step * offset)
        date_text = candidate.strftime("%Y%m%d")
        try:
            df = get_market_ohlcv_by_ticker(date_text, market="ALL")
            if df is not None and not df.empty:
                return date_text
        except Exception:
            continue

    try:
        nearest = str(stock.get_nearest_business_day_in_a_week(target_date, prev=prev))
        if nearest:
            return nearest
    except Exception:
        pass

    direction = "previous" if prev else "next"
    raise RuntimeError(
        f"Could not find {direction} KRX business day with public OHLCV data near {target_date} "
        f"within {_MAX_BUSINESS_DAY_SEARCH_DAYS} days. "
        "Set AGENTS_INVEST_FALLBACK_TRADE_DATE=YYYYMMDD to run paper mode with a known data date."
    )


def get_market_ohlcv_by_ticker(date: str, market: str = "ALL", *args: Any, **kwargs: Any) -> pd.DataFrame:
    try:
        df = _fetch_by_market(stock.get_market_ohlcv_by_ticker, date, market=market, *args, **kwargs)
        normalized = _normalize_ohlcv_ticker_frame(df)
        if not normalized.empty:
            return normalized
    except Exception:
        pass
    return _fetch_naver_market_ohlcv_by_ticker(date)


def get_market_ohlcv_by_date(
    fromdate: str,
    todate: str,
    ticker: str,
    adjusted: bool = True,
    *args: Any,
    **kwargs: Any,
) -> pd.DataFrame:
    try:
        df = stock.get_market_ohlcv_by_date(fromdate, todate, ticker, adjusted=adjusted, *args, **kwargs)
        normalized = _normalize_ohlcv_date_frame(df)
        if not normalized.empty:
            return normalized
    except Exception:
        pass
    return _fetch_naver_ohlcv_by_date(ticker, todate, count=30)


def get_market_cap_by_ticker(date: str, market: str = "ALL", *args: Any, **kwargs: Any) -> pd.DataFrame:
    try:
        df = _fetch_by_market(stock.get_market_cap_by_ticker, date, market=market, *args, **kwargs)
        normalized = _normalize_market_cap_frame(df)
        if not normalized.empty:
            return normalized
    except Exception:
        pass
    ohlcv = get_market_ohlcv_by_ticker(date, market=market)
    if ohlcv.empty:
        return pd.DataFrame()
    cap = pd.DataFrame(index=ohlcv.index)
    cap["Close"] = ohlcv.get("Close", 0)
    cap["Volume"] = ohlcv.get("Volume", 0)
    cap["Amount"] = ohlcv.get("Amount", 0)
    cap["MarketCap"] = 0
    cap["Market Cap"] = 0
    cap["market_cap"] = 0
    return cap


@lru_cache(maxsize=4096)
def get_market_ticker_name(ticker: str) -> str:
    try:
        return str(stock.get_market_ticker_name(ticker))
    except Exception:
        return str(ticker)


def _fetch_by_market(fetcher: Callable[..., pd.DataFrame], *args: Any, market: str = "ALL", **kwargs: Any) -> pd.DataFrame:
    if market and market.upper() != "ALL":
        return fetcher(*args, market=market, **kwargs)

    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for market_name in _MARKETS_FOR_ALL:
        try:
            df = fetcher(*args, market=market_name, **kwargs)
        except Exception as exc:
            errors.append(f"{market_name}: {exc.__class__.__name__}: {exc}")
            continue
        if df is not None and not df.empty:
            frames.append(df)

    if frames:
        combined = pd.concat(frames, axis=0)
        return combined[~combined.index.duplicated(keep="first")]

    if errors:
        raise RuntimeError("pykrx market fetch failed for all markets: " + " | ".join(errors[-3:]))
    return pd.DataFrame()


def _fetch_naver_market_ohlcv_by_ticker(date: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker in _fallback_tickers():
        history = _fetch_naver_ohlcv_by_date(ticker, date, count=90)
        if history.empty:
            continue
        row = history[history.index.astype(str) <= date].tail(1)
        if row.empty:
            continue
        item = row.iloc[0].to_dict()
        item["ticker"] = ticker
        rows.append(item)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("ticker")
    return _normalize_ohlcv_ticker_frame(df)


def _fetch_naver_ohlcv_by_date(ticker: str, end_date: str, count: int = 30) -> pd.DataFrame:
    url = "https://fchart.stock.naver.com/sise.nhn"
    params = {"symbol": ticker, "timeframe": "day", "count": str(count), "requestType": "0"}
    try:
        response = requests.get(url, params=params, timeout=_NAVER_TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for item in root.findall(".//item"):
        data = item.attrib.get("data", "")
        parts = data.split("|")
        if len(parts) < 6:
            continue
        date, open_, high, low, close, volume = parts[:6]
        if date > end_date:
            continue
        open_i = _to_int(open_)
        high_i = _to_int(high)
        low_i = _to_int(low)
        close_i = _to_int(close)
        volume_i = _to_int(volume)
        rows.append(
            {
                "Date": date,
                "Open": open_i,
                "High": high_i,
                "Low": low_i,
                "Close": close_i,
                "Volume": volume_i,
                "Amount": close_i * volume_i,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("Date")


def _fallback_tickers() -> tuple[str, ...]:
    raw = os.getenv("AGENTS_INVEST_FALLBACK_TICKERS", "").strip()
    if not raw:
        return _NAVER_FALLBACK_TICKERS
    tickers = tuple(item.strip() for item in raw.split(",") if item.strip())
    return tickers or _NAVER_FALLBACK_TICKERS


def _normalize_ohlcv_ticker_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    renamed = df.rename(
        columns={
            "시가": "Open",
            "고가": "High",
            "저가": "Low",
            "종가": "Close",
            "거래량": "Volume",
            "거래대금": "Amount",
            "등락률": "ChangeRate",
        }
    ).copy()
    _ensure_numeric(renamed, ["Open", "High", "Low", "Close", "Volume", "Amount"])
    return renamed


def _normalize_ohlcv_date_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    renamed = df.rename(
        columns={
            "시가": "Open",
            "고가": "High",
            "저가": "Low",
            "종가": "Close",
            "거래량": "Volume",
            "거래대금": "Amount",
            "등락률": "ChangeRate",
        }
    ).copy()
    _ensure_numeric(renamed, ["Open", "High", "Low", "Close", "Volume", "Amount"])
    return renamed


def _normalize_market_cap_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    renamed = df.rename(
        columns={
            "시가총액": "MarketCap",
            "상장주식수": "ListedShares",
            "종가": "Close",
            "거래량": "Volume",
            "거래대금": "Amount",
        }
    ).copy()
    if "Market Cap" not in renamed.columns and "MarketCap" in renamed.columns:
        renamed["Market Cap"] = renamed["MarketCap"]
    if "market_cap" not in renamed.columns and "MarketCap" in renamed.columns:
        renamed["market_cap"] = renamed["MarketCap"]
    _ensure_numeric(renamed, ["MarketCap", "Market Cap", "market_cap", "ListedShares", "Close", "Volume", "Amount"])
    return renamed


def _ensure_numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)


def _to_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except Exception:
        return 0


def _parse_date(value: str) -> _dt.date:
    return _dt.datetime.strptime(str(value), "%Y%m%d").date()
