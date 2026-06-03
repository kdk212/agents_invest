"""Adaptive scoring layer for PRISM candidates.

This module imports the useful ideas from kdk212/ai_win_invest without modifying
that source repository: momentum/trend/liquidity/risk scoring, volatility stops,
and periodic backtest-driven parameter selection. It acts as a post-processor for
PRISM output JSON so the upstream PRISM agents can keep producing candidates while
agents_invest adds a self-tuning ranking layer.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGY_PATH = ROOT / "runtime" / "adaptive_strategy.json"
DEFAULT_DASHBOARD_STRATEGY_PATH = ROOT / "dashboard" / "adaptive_strategy.json"

DEFAULT_PARAMS = {
    "source": "default_ai_win_invest_style",
    "selected_period_months": 18,
    "top_n": 7,
    "universe_size": 160,
    "rebalance_days": 5,
    "transaction_cost_bps": 20,
    "score_threshold": 2.0,
    "stop_multiplier": 2.5,
    "take_profit_trigger_pct": 0.30,
    "take_profit_trailing_pct": 0.10,
    "prism_weight": 0.45,
    "ai_win_weight": 0.55,
    "updated_at": None,
}


@dataclass(frozen=True)
class BacktestSummary:
    period_months: int
    start: str
    end: str
    top_n: int
    universe_size: int
    score_threshold: float
    stop_multiplier: float
    take_profit_trigger_pct: float
    take_profit_trailing_pct: float
    total_return: float
    cagr: float
    mdd: float
    sharpe: float
    exposure: float


def enhance_prism_output(
    output_file: str | Path,
    *,
    strategy_path: str | Path = DEFAULT_STRATEGY_PATH,
) -> dict[str, Any]:
    """Add adaptive scores to a PRISM output file and rewrite it in place."""

    path = Path(output_file)
    if not path.exists():
        return {"ok": False, "reason": f"output_not_found: {path}"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "reason": f"json_load_failed: {exc.__class__.__name__}: {exc}"}

    rows = _flatten_prism_rows(data)
    if not rows:
        return {"ok": True, "enhanced": 0, "reason": "no_candidates"}

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    trade_date = str(metadata.get("trade_date") or "").replace("-", "")
    if not trade_date:
        trade_date = _nearest_business_day(_today_ymd())

    params = load_strategy_params(strategy_path)
    factor_rows = []
    start = _date_shift_ymd(trade_date, days=-430)
    for row in rows:
        ticker = str(row.get("code") or row.get("ticker") or "").zfill(6)
        if not ticker:
            continue
        try:
            history = _get_ohlcv_by_date(start, trade_date, ticker)
            factors = score_history_frame(history)
        except Exception:
            factors = None
        if factors:
            factor_rows.append({"ticker": ticker, **factors})

    if not factor_rows:
        _attach_adaptive_metadata(data, params, status="factor_data_unavailable")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "enhanced": 0, "reason": "factor_data_unavailable"}

    factors_df = pd.DataFrame(factor_rows).set_index("ticker")
    scored_factors = _score_factor_frame(factors_df)
    enhanced_count = 0

    for trigger_type, value in data.items():
        if trigger_type == "metadata" or not isinstance(value, list):
            continue
        trigger_items = []
        for item in value:
            if not isinstance(item, dict):
                trigger_items.append(item)
                continue
            ticker = str(item.get("code") or item.get("ticker") or "").zfill(6)
            if ticker in scored_factors.index:
                _apply_adaptive_score(item, ticker, scored_factors, params)
                enhanced_count += 1
            trigger_items.append(item)
        data[trigger_type] = sorted(trigger_items, key=_adaptive_sort_key, reverse=True)

    _attach_adaptive_metadata(data, params, status="enhanced", enhanced_count=enhanced_count)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "enhanced": enhanced_count, "strategy": _public_params(params)}


def optimize_and_write_strategy(
    *,
    end: str | None = None,
    periods_months: tuple[int, ...] = (24, 18, 12),
    top_n: int | None = None,
    universe_size: int | None = None,
    strategy_path: str | Path = DEFAULT_STRATEGY_PATH,
    dashboard_strategy_path: str | Path = DEFAULT_DASHBOARD_STRATEGY_PATH,
) -> dict[str, Any]:
    """Run rolling-period backtests and write the best adaptive parameters."""

    end_ymd = _nearest_business_day((end or _today_ymd()).replace("-", ""))
    base = load_strategy_params(strategy_path)
    top_n = int(top_n or base["top_n"])
    universe_size = int(universe_size or base["universe_size"])

    summaries: list[BacktestSummary] = []
    for months in periods_months:
        start = _date_shift_ymd(end_ymd, days=-int(months * 30.5))
        summaries.extend(
            run_parameter_grid_backtest(
                start=start,
                end=end_ymd,
                period_months=months,
                top_n=top_n,
                universe_size=universe_size,
            )
        )

    if not summaries:
        return {"ok": False, "reason": "no_backtest_results"}

    best = sorted(
        summaries,
        key=lambda item: (item.total_return, item.cagr, item.sharpe, item.mdd),
        reverse=True,
    )[0]
    next_params = {
        **DEFAULT_PARAMS,
        "source": "weekly_backtest_optimizer",
        "selected_period_months": best.period_months,
        "top_n": best.top_n,
        "universe_size": best.universe_size,
        "score_threshold": best.score_threshold,
        "stop_multiplier": best.stop_multiplier,
        "take_profit_trigger_pct": best.take_profit_trigger_pct,
        "take_profit_trailing_pct": best.take_profit_trailing_pct,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "best_summary": asdict(best),
        "candidate_summaries": [asdict(item) for item in summaries[:80]],
    }

    _write_json(Path(strategy_path), next_params)
    _write_json(Path(dashboard_strategy_path), _public_params(next_params))
    return {"ok": True, "strategy_path": str(strategy_path), "selected": asdict(best)}


def run_parameter_grid_backtest(
    *,
    start: str,
    end: str,
    period_months: int,
    top_n: int,
    universe_size: int,
) -> list[BacktestSummary]:
    tickers = _top_liquid_tickers(end, universe_size)
    if not tickers:
        return []

    warmup_start = _date_shift_ymd(start, days=-260)
    prices = _price_panel(tickers, warmup_start, end).dropna(axis=1, thresh=130)
    if prices.empty or len(prices) < 150:
        return []

    configs = []
    for threshold in (1.5, 2.0, 2.5, 3.0):
        for stop_multiplier in (1.7, 2.2, 2.5, 2.8):
            for trigger, trailing in ((0.25, 0.08), (0.30, 0.10), (0.35, 0.12), (0.40, 0.15)):
                configs.append((threshold, stop_multiplier, trigger, trailing))

    summaries: list[BacktestSummary] = []
    for threshold, stop_multiplier, trigger, trailing in configs:
        daily = _run_backtest_on_prices(
            prices,
            start=start,
            top_n=top_n,
            score_threshold=threshold,
            stop_multiplier=stop_multiplier,
            take_profit_trigger_pct=trigger,
            take_profit_trailing_pct=trailing,
        )
        if daily.empty:
            continue
        stats = _summarize_equity(daily)
        summaries.append(
            BacktestSummary(
                period_months=period_months,
                start=_iso_date(start),
                end=_iso_date(end),
                top_n=top_n,
                universe_size=universe_size,
                score_threshold=threshold,
                stop_multiplier=stop_multiplier,
                take_profit_trigger_pct=trigger,
                take_profit_trailing_pct=trailing,
                **stats,
            )
        )

    return sorted(summaries, key=lambda item: (item.total_return, item.cagr, item.sharpe), reverse=True)


def score_history_frame(df: pd.DataFrame) -> dict[str, float] | None:
    if df.empty or len(df) < 130:
        return None
    close = df["close"].astype(float)
    trading_value = df.get("trading_value", close * df.get("volume", 0)).astype(float)
    daily = close.pct_change(fill_method=None)
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    peak20 = close.tail(20).max()
    trough20 = close.tail(20).min()
    peak60 = close.tail(60).max()
    latest = float(close.iloc[-1])
    mom20 = latest / close.iloc[-21] - 1
    mom60 = latest / close.iloc[-61] - 1
    mom120 = latest / close.iloc[-121] - 1
    trend = latest / ma60 - 1 + (ma20 / ma60 - 1)
    vol60 = float(daily.tail(60).std() * math.sqrt(252))
    hit20 = float((daily.tail(20) > 0).mean())
    pullback_resilience = float(latest / peak20 - trough20 / peak20) if peak20 else 0.0
    acceleration = float(mom20 - (mom60 - mom20) / 2)
    overextension = float(latest / ma20 - 1) if ma20 else 0.0
    drawdown = float(latest / peak60 - 1) if peak60 else 0.0
    parabolic_penalty = max(0.0, mom20 - 0.80) + max(0.0, mom60 - 2.20) + max(0.0, overextension - 0.35)
    risk_score = vol60 + max(0.0, -drawdown) + max(0.0, overextension - 0.18)
    turnover_change = float(trading_value.tail(5).mean() / trading_value.tail(60).mean() - 1)
    daily_risk = float(daily.tail(20).std())
    return {
        "close": latest,
        "mom20": float(mom20),
        "mom60": float(mom60),
        "mom120": float(mom120),
        "trend": float(trend),
        "vol60": vol60,
        "hit20": hit20,
        "pullback_resilience": pullback_resilience,
        "acceleration": acceleration,
        "overextension": overextension,
        "drawdown_from_60d_peak": drawdown,
        "risk_score": float(risk_score),
        "parabolic_penalty": float(parabolic_penalty),
        "turnover_change": turnover_change,
        "daily_risk": daily_risk,
        "avg_trading_value_20": float(trading_value.tail(20).mean()),
    }


def load_strategy_params(strategy_path: str | Path = DEFAULT_STRATEGY_PATH) -> dict[str, Any]:
    path = Path(strategy_path)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return {**DEFAULT_PARAMS, **loaded}
        except Exception:
            pass
    return dict(DEFAULT_PARAMS)


def _run_backtest_on_prices(
    prices: pd.DataFrame,
    *,
    start: str,
    top_n: int,
    score_threshold: float,
    stop_multiplier: float,
    take_profit_trigger_pct: float,
    take_profit_trailing_pct: float,
) -> pd.DataFrame:
    returns = prices.pct_change(fill_method=None).fillna(0)
    start_ts = pd.to_datetime(_iso_date(start))
    rebalance_days = int(DEFAULT_PARAMS["rebalance_days"])
    cost = float(DEFAULT_PARAMS["transaction_cost_bps"]) / 10000
    equity = 1.0
    active_holdings: set[str] = set()
    entry_prices = pd.Series(dtype=float)
    peak_prices = pd.Series(dtype=float)
    rows = []

    for idx in range(130, len(prices) - 1):
        current_date = prices.index[idx]
        if current_date < start_ts:
            continue
        should_rebalance = len(rows) == 0 or len(rows) % rebalance_days == 0
        if should_rebalance:
            factors = _factor_frame_for_panel(prices, idx)
            ranked = factors["score"].dropna().sort_values(ascending=False)
            selected = ranked[ranked >= score_threshold].head(top_n)
            next_holdings = set(selected.index)
            turnover = len(next_holdings.symmetric_difference(active_holdings)) / max(top_n, 1)
            equity *= 1 - cost * turnover
            active_holdings = next_holdings
            if active_holdings:
                entry_prices = prices.loc[current_date, sorted(active_holdings)].astype(float)
                peak_prices = entry_prices.copy()
            else:
                entry_prices = pd.Series(dtype=float)
                peak_prices = pd.Series(dtype=float)

        if active_holdings:
            active = sorted(active_holdings)
            today_prices = prices.loc[current_date, active].astype(float)
            peak_prices.loc[active] = pd.concat([peak_prices.loc[active], today_prices], axis=1).max(axis=1)
            stop_pct = _dynamic_stop_pct(prices, idx, active, stop_multiplier)
            drawdown_entry = today_prices / entry_prices.loc[active] - 1
            drawdown_peak = today_prices / peak_prices.loc[active] - 1
            stop_mask = (drawdown_entry <= -stop_pct) | (drawdown_peak <= -(stop_pct * 0.85))
            take_profit_mask = (
                (peak_prices.loc[active] / entry_prices.loc[active] - 1 >= take_profit_trigger_pct)
                & (drawdown_peak <= -take_profit_trailing_pct)
            )
            exited = set(stop_mask[stop_mask].index) | set(take_profit_mask[take_profit_mask].index)
            active_holdings -= exited

        next_date = prices.index[idx + 1]
        next_return = returns.loc[next_date, sorted(active_holdings)].mean() if active_holdings else 0.0
        equity *= 1 + float(next_return)
        rows.append(
            {
                "date": next_date.date().isoformat(),
                "equity": equity,
                "daily_return": float(next_return),
                "active_positions": len(active_holdings),
                "max_positions": top_n,
            }
        )

    return pd.DataFrame(rows)


def _factor_frame_for_panel(prices: pd.DataFrame, idx: int) -> pd.DataFrame:
    window = prices.iloc[: idx + 1]
    close = window.iloc[-1]
    daily = window.pct_change(fill_method=None)
    ma20 = window.rolling(20).mean().iloc[-1]
    ma60 = window.rolling(60).mean().iloc[-1]
    peak20 = window.tail(20).max()
    trough20 = window.tail(20).min()
    peak60 = window.tail(60).max()
    frame = pd.DataFrame(
        {
            "mom20": close / window.iloc[-21] - 1,
            "mom60": close / window.iloc[-61] - 1,
            "mom120": close / window.iloc[-121] - 1,
            "trend": close / ma60 - 1 + (ma20 / ma60 - 1),
            "vol60": daily.tail(60).std() * math.sqrt(252),
            "hit20": (daily.tail(20) > 0).mean(),
            "pullback_resilience": close / peak20 - trough20 / peak20,
            "acceleration": close / window.iloc[-21] - 1 - ((close / window.iloc[-61] - 1) - (close / window.iloc[-21] - 1)) / 2,
            "drawdown_from_60d_peak": close / peak60 - 1,
        }
    )
    frame["risk_score"] = frame["vol60"] + (-frame["drawdown_from_60d_peak"]).clip(lower=0) + ((close / ma20 - 1) - 0.18).clip(lower=0)
    return _score_factor_frame(frame)


def _score_factor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.replace([np.inf, -np.inf], np.nan).copy()
    out["forward_quality_score"] = (
        0.22 * _zscore(out["hit20"])
        + 0.18 * _zscore(out["pullback_resilience"])
        + 0.18 * _zscore(out["acceleration"])
        + 0.12 * _zscore(out.get("turnover_change", pd.Series(0.0, index=out.index)).clip(-1, 5))
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


def _apply_adaptive_score(item: dict[str, Any], ticker: str, factors: pd.DataFrame, params: dict[str, Any]) -> None:
    row = factors.loc[ticker]
    prism_score = _float(item.get("profit_score"), _float(item.get("final_score"), 0.0))
    prism_norm = _bounded_rank_score(prism_score)
    ai_norm = float(row.get("ai_win_score_100", 50.0)) / 100.0
    adaptive = (float(params["prism_weight"]) * prism_norm + float(params["ai_win_weight"]) * ai_norm) * 100
    latest = _float(item.get("current_price"), _float(row.get("close"), 0.0))
    daily_risk = _float(row.get("daily_risk"), 0.0)
    stop_pct = min(max(float(params["stop_multiplier"]) * daily_risk * math.sqrt(5), 0.045), 0.18)
    if latest > 0:
        item["stop_loss_pct"] = round(stop_pct * 100, 2)
        item["stop_loss_price"] = round(latest * (1 - stop_pct), 0)
        item["take_profit_trigger_pct"] = round(float(params["take_profit_trigger_pct"]) * 100, 2)
        item["take_profit_trailing_pct"] = round(float(params["take_profit_trailing_pct"]) * 100, 2)
        item["take_profit_trigger_price"] = round(latest * (1 + float(params["take_profit_trigger_pct"])), 0)
    item["ai_win_score"] = round(float(row.get("ai_win_score", 0.0)), 4)
    item["ai_win_score_100"] = round(float(row.get("ai_win_score_100", 0.0)), 2)
    item["forward_quality_score"] = round(float(row.get("forward_quality_score", 0.0)), 4)
    item["adaptive_profit_score"] = round(adaptive, 2)
    item["profit_score"] = round(adaptive, 2)
    item["adaptive_strategy_source"] = str(params.get("source") or "default")
    item["adaptive_selected_period_months"] = int(params.get("selected_period_months") or 0)


def _adaptive_sort_key(item: Any) -> float:
    if not isinstance(item, dict):
        return -1.0
    return _float(item.get("adaptive_profit_score"), _float(item.get("profit_score"), _float(item.get("final_score"), 0.0)))


def _flatten_prism_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in data.items():
        if key == "metadata" or not isinstance(value, list):
            continue
        rows.extend(item for item in value if isinstance(item, dict))
    return rows


def _top_liquid_tickers(end: str, universe_size: int) -> list[str]:
    cap = _get_market_cap_by_ticker(end)
    if cap.empty:
        return []
    value_col = _first_column(cap, ["trading_value", "거래대금", "Amount", "시가총액", "market_cap"])
    if value_col is None:
        return []
    cap[value_col] = pd.to_numeric(cap[value_col], errors="coerce")
    return cap.sort_values(value_col, ascending=False).head(universe_size).index.astype(str).str.zfill(6).tolist()


def _price_panel(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        try:
            df = _get_ohlcv_by_date(start, end, ticker)
        except Exception:
            continue
        if not df.empty and "close" in df.columns:
            frames.append(df["close"].rename(ticker))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).sort_index()


def _get_ohlcv_by_date(start: str, end: str, ticker: str) -> pd.DataFrame:
    from krx_data_client import get_market_ohlcv_by_date

    raw = get_market_ohlcv_by_date(start, end, ticker)
    return _normalize_ohlcv(raw)


def _get_market_cap_by_ticker(end: str) -> pd.DataFrame:
    from krx_data_client import get_market_cap_by_ticker

    try:
        raw = get_market_cap_by_ticker(end, market="ALL")
    except TypeError:
        raw = get_market_cap_by_ticker(end)
    out = raw.copy()
    out.index = out.index.astype(str).str.zfill(6)
    return out


def _nearest_business_day(target: str) -> str:
    try:
        from krx_data_client import get_nearest_business_day_in_a_week

        return str(get_nearest_business_day_in_a_week(target, prev=True))
    except Exception:
        return target


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Amount": "trading_value",
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
        "거래대금": "trading_value",
    }
    out = df.rename(columns=rename).copy()
    if "trading_value" not in out.columns and {"close", "volume"}.issubset(out.columns):
        out["trading_value"] = out["close"] * out["volume"]
    out.index = pd.to_datetime(out.index)
    required = ["open", "high", "low", "close", "volume"]
    for column in required:
        if column not in out.columns:
            return pd.DataFrame()
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["close"])


def _dynamic_stop_pct(prices: pd.DataFrame, idx: int, holdings: list[str], multiplier: float) -> pd.Series:
    daily = prices.iloc[: idx + 1][holdings].pct_change(fill_method=None)
    daily_risk = daily.tail(20).std()
    return (multiplier * daily_risk * math.sqrt(5)).clip(lower=0.045, upper=0.18)


def _summarize_equity(result: pd.DataFrame) -> dict[str, float]:
    equity = result["equity"]
    daily = result["daily_return"]
    years = max(len(result) / 252, 1 / 252)
    mdd = float((equity / equity.cummax() - 1).min())
    sharpe = float((daily.mean() / daily.std()) * math.sqrt(252)) if daily.std() else 0.0
    max_positions = float(result["max_positions"].iloc[0]) if "max_positions" in result else 1.0
    return {
        "total_return": float(equity.iloc[-1] - 1),
        "cagr": float(equity.iloc[-1] ** (1 / years) - 1),
        "mdd": mdd,
        "sharpe": sharpe,
        "exposure": float(result["active_positions"].mean() / max(max_positions, 1.0)),
    }


def _attach_adaptive_metadata(data: dict[str, Any], params: dict[str, Any], *, status: str, enhanced_count: int = 0) -> None:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    metadata["adaptive_strategy"] = {
        **_public_params(params),
        "status": status,
        "enhanced_count": enhanced_count,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
    }
    data["metadata"] = metadata


def _public_params(params: dict[str, Any]) -> dict[str, Any]:
    public_keys = [
        "source",
        "selected_period_months",
        "top_n",
        "universe_size",
        "score_threshold",
        "stop_multiplier",
        "take_profit_trigger_pct",
        "take_profit_trailing_pct",
        "prism_weight",
        "ai_win_weight",
        "updated_at",
        "best_summary",
    ]
    return {key: params.get(key) for key in public_keys if key in params}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _zscore(series: pd.Series) -> pd.Series:
    clean = series.replace([np.inf, -np.inf], np.nan)
    std = clean.std(skipna=True)
    if std is None or pd.isna(std) or math.isclose(float(std), 0.0):
        return pd.Series(0.0, index=series.index)
    return (clean - clean.mean(skipna=True)) / std


def _bounded_rank_score(value: float) -> float:
    if value <= 0:
        return 0.0
    if value <= 1.0:
        return value
    return min(value / 100.0, 1.0)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _first_column(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _today_ymd() -> str:
    return date.today().strftime("%Y%m%d")


def _date_shift_ymd(value: str, *, days: int) -> str:
    parsed = pd.to_datetime(_iso_date(value)).date()
    return (parsed + timedelta(days=days)).strftime("%Y%m%d")


def _iso_date(value: str) -> str:
    value = value.replace("-", "")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"
