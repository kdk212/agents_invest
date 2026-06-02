"""pykrx-backed compatibility layer for PRISM's krx_data_client imports.

The upstream PRISM runtime imports ``krx_data_client`` and recent versions of
that package require KRX_ID/KRX_PW. EC2 paper operation should not depend on a
separate KRX direct-login account, so the PRISM import patch copies this module
into the imported ``prism-insight/`` checkout as ``krx_data_client.py``.
"""

from __future__ import annotations

import datetime as _dt
import os
from functools import lru_cache
from typing import Any, Callable

import pandas as pd
from pykrx import stock

_MAX_BUSINESS_DAY_SEARCH_DAYS = 45
_MARKETS_FOR_ALL = ("KOSPI", "KOSDAQ", "KONEX")


def get_nearest_business_day_in_a_week(target_date: str, prev: bool = True) -> str:
    """Return the nearest KRX date that actually has public OHLCV data.

    pykrx's own nearest-day helper can raise ``IndexError`` when the target date
    has no nearby rows. This shim searches a bounded range and fails quickly so
    the 24h service does not appear frozen. For paper catch-up runs, set
    ``AGENTS_INVEST_FALLBACK_TRADE_DATE=YYYYMMDD``.
    """
    fallback_date = os.getenv("AGENTS_INVEST_FALLBACK_TRADE_DATE", "").strip()
    if fallback_date:
        return fallback_date

    base = _parse_date(target_date)
    step = -1 if prev else 1
    for offset in range(0, _MAX_BUSINESS_DAY_SEARCH_DAYS + 1):
        candidate = base + _dt.timedelta(days=step * offset)
        date_text = candidate.strftime("%Y%m%d")
        try:
            df = _fetch_by_market(stock.get_market_ohlcv_by_ticker, date_text, market="ALL")
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
    df = _fetch_by_market(stock.get_market_ohlcv_by_ticker, date, market=market, *args, **kwargs)
    return _normalize_ohlcv_ticker_frame(df)


def get_market_ohlcv_by_date(
    fromdate: str,
    todate: str,
    ticker: str,
    adjusted: bool = True,
    *args: Any,
    **kwargs: Any,
) -> pd.DataFrame:
    df = stock.get_market_ohlcv_by_date(fromdate, todate, ticker, adjusted=adjusted, *args, **kwargs)
    return _normalize_ohlcv_date_frame(df)


def get_market_cap_by_ticker(date: str, market: str = "ALL", *args: Any, **kwargs: Any) -> pd.DataFrame:
    df = _fetch_by_market(stock.get_market_cap_by_ticker, date, market=market, *args, **kwargs)
    return _normalize_market_cap_frame(df)


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


def _parse_date(value: str) -> _dt.date:
    return _dt.datetime.strptime(str(value), "%Y%m%d").date()
