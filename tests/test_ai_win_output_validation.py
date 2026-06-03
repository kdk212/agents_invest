from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_dashboard(tmp_path: Path, selected_period: int) -> Path:
    dashboard = tmp_path / "dashboard"
    write_json(
        dashboard / "portfolio_status.json",
        {
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "price_source": "previous_close_signal_next_open_entry_intraday_sell_rules",
            "summary": {"total_return_pct": "0.00%"},
            "equity_curve": [{"date": "2026-06-01"}, {"date": "2026-06-02"}],
        },
    )
    write_json(
        dashboard / "adaptive_strategy.json",
        {
            "source": "ai_win_realistic_backtest_intraday_sells",
            "selected_top_n": 3,
            "selected_period_months": selected_period,
            "tested": [{"period_months": selected_period}],
        },
    )
    write_json(
        dashboard / "recommendation_history.json",
        {
            "items": [
                {
                    "date": "2026-06-01",
                    "sections": {
                        "AI WIN": [
                            {
                                "code": "001820",
                                "name": "삼화콘덴서",
                                "recommendation_reason": "60일 모멘텀 우위",
                                "previous_close_price": 100000,
                            }
                        ]
                    },
                }
            ]
        },
    )
    write_json(
        dashboard / "prism_latest_morning.json",
        {
            "metadata": {},
            "AI WIN": [
                {
                    "code": "001820",
                    "name": "삼화콘덴서",
                    "recommendation_reason": "60일 모멘텀 우위",
                    "previous_close_price": 100000,
                }
            ],
        },
    )
    return dashboard


def run_validator(dashboard: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_ai_win_outputs.py"),
            "--portfolio-start",
            "2026-06-01",
            "--dashboard-dir",
            str(dashboard),
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def test_validator_rejects_short_selected_period(tmp_path: Path) -> None:
    result = run_validator(make_dashboard(tmp_path, selected_period=6))

    assert result.returncode == 1
    assert "selected_period_too_short" in result.stdout


def test_validator_accepts_twelve_month_selected_period(tmp_path: Path) -> None:
    result = run_validator(make_dashboard(tmp_path, selected_period=12))

    assert result.returncode == 0
    assert '"ok": true' in result.stdout
