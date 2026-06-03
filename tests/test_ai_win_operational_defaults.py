from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rebuild_runner_uses_robust_backtest_windows_by_default() -> None:
    text = (ROOT / "scripts" / "run_ai_win_rebuild_and_validate.sh").read_text(encoding="utf-8")

    assert 'PERIOD_MONTHS="${PERIOD_MONTHS:-24,18,12}"' in text
    assert 'PERIOD_MONTHS:-24,18,12,6,3' not in text


def test_daily_timer_uses_robust_backtest_windows() -> None:
    text = (ROOT / "scripts" / "install_daily_ai_win_timer.sh").read_text(encoding="utf-8")

    assert "Environment=PERIOD_MONTHS=24,18,12" in text
    assert "Environment=PERIOD_MONTHS=24,18,12,6,3" not in text
