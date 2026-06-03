from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "optimize_ai_win_count_and_portfolio.py"

spec = importlib.util.spec_from_file_location("ai_win_optimizer_for_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules["ai_win_optimizer_for_test"] = module
assert spec.loader is not None
spec.loader.exec_module(module)


def make_frame(open_price: float, high: float, low: float, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [open_price], "High": [high], "Low": [low], "Close": [close]},
        index=pd.to_datetime(["2026-06-02"]),
    )


def make_lot() -> dict:
    return {"entry": 100.0, "stop": 90.0, "target": 130.0, "peak": 100.0}


def test_sell_reason_uses_intraday_low_for_stop_even_if_close_recovers() -> None:
    reason, exit_price = module.sell_reason(make_frame(100, 110, 89, 105), make_lot(), date(2026, 6, 2))

    assert reason == "손절가 이탈"
    assert exit_price == 90.0


def test_sell_reason_uses_intraday_high_for_target_even_if_close_fades() -> None:
    reason, exit_price = module.sell_reason(make_frame(100, 131, 95, 110), make_lot(), date(2026, 6, 2))

    assert reason == "목표가 도달"
    assert exit_price == 130.0


def test_sell_reason_is_conservative_when_stop_and_target_touch_same_day() -> None:
    reason, exit_price = module.sell_reason(make_frame(100, 135, 89, 120), make_lot(), date(2026, 6, 2))

    assert reason == "손절가 이탈"
    assert exit_price == 90.0
