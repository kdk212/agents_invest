"""pykrx-backed compatibility layer for PRISM's krx_data_client imports.

The upstream PRISM runtime imports ``krx_data_client`` and recent versions of
that package require KRX_ID/KRX_PW. EC2 paper operation should not depend on a
separate KRX direct-login account, so the PRISM import patch copies this module
into the imported ``prism-insight/`` checkout as ``krx_data_client.py``.
"""

from __future__ import annotations

import datetime as _dt
from functools import lru_cache
from typing import Any

import pandas as pd
from pykrx import stock


def get_nearest_business_day_in_a_week(target_date: str, prev: bool = True) -> str:
    """Return the nearest KRX business day around ``target_date``.

    pykrx exposes ``get_nearest_business_day_in_a_week`` directly. A small
    fallback loop is kept for older pykrx releases or transient empty responses.
    """
    try:
        return str(stock.get_nearest_business_day_in_a_week(target_date, prev=prev))
    except Exception:
        base = _parse_date(target_date)
        step = -1 if prev else 1
        for offset in range(0, 8):
            candidate = base + _dt.timedelta(days=step * offset)
            date_text = candidate.strftime("%Y%m%d")
            try:
                df = stock.get_market_ohlcv_by_ticker(date_text, market="ALL")
                if not df.empty:
                    return date_text
            except Exception:
                continue
        raise


def get_market_ohlcv_by_ticker(date: str, market: str = "ALL", *args: Any, **kwargs: Any) -> pd.DataFrame:
    df = stock.get_market_ohlcv_by_ticker(date, market=market, *args, **kwargs)
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
    df = stock.get_market_cap_by_ticker(date, market=market, *args, **kwargs)
    return _normalize_market_cap_frame(df)


@lru_cache(maxsize=4096)
def get_market_ticker_name(ticker: str) -> str:
    try:
        return str(stock.get_market_ticker_name(ticker))
    except Exception:
        return str(ticker)


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
