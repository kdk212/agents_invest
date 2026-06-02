import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from agents_invest_runner import (
    _format_candidate_summary,
    _install_ready,
    _load_candidates,
    _prism_status,
    _selected_batch_modes,
    _write_runtime_status,
)


def test_selected_batch_modes_explicit_values():
    assert _selected_batch_modes("morning") == ["morning"]
    assert _selected_batch_modes("afternoon") == ["afternoon"]
    assert _selected_batch_modes("both") == ["morning", "afternoon"]


def test_selected_batch_modes_auto_uses_korea_market_half_day_split():
    assert _selected_batch_modes("auto", now=datetime(2026, 6, 3, 9, 30)) == ["morning"]
    assert _selected_batch_modes("auto", now=datetime(2026, 6, 3, 13, 10)) == ["afternoon"]


def test_service_install_ready_can_wait_for_missing_secrets():
    assert _install_ready(safety_allowed=True, secret_ok=False, allow_missing_secrets=True) is True
    assert _install_ready(safety_allowed=False, secret_ok=False, allow_missing_secrets=True) is False
    assert _install_ready(safety_allowed=True, secret_ok=False, allow_missing_secrets=False) is False


def test_write_runtime_status_exports_public_heartbeat(tmp_path: Path):
    dashboard_dir = tmp_path / "dashboard"
    settings = SimpleNamespace(trading_mode="paper")
    secret_result = SimpleNamespace(
        ok=False,
        loaded_env_names=(),
        missing_env_names=("OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"),
    )
    safety = SimpleNamespace(allowed=True, reasons=("startup_safety_passed",), warnings=())

    _write_runtime_status(
        dashboard_dir,
        status="waiting_for_runtime_secrets",
        settings=settings,
        secret_result=secret_result,
        safety=safety,
        prism={"ready": True},
        runtime_ready=False,
        install_ready=True,
    )

    data = json.loads((dashboard_dir / "runtime_status.json").read_text(encoding="utf-8"))
    assert data["status"] == "waiting_for_runtime_secrets"
    assert data["trading_mode"] == "paper"
    assert data["install_ready"] is True
    assert data["runtime_ready"] is False
    assert data["missing_secret_names"] == ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"]
    assert "updated_at" in data


def test_prism_status_requires_trigger_batch(tmp_path: Path):
    missing = _prism_status(tmp_path / "missing")
    assert missing["ready"] is False

    prism_dir = tmp_path / "prism-insight"
    prism_dir.mkdir()
    assert _prism_status(prism_dir)["ready"] is False

    (prism_dir / "trigger_batch.py").write_text("print('ok')\n", encoding="utf-8")
    ready = _prism_status(prism_dir)
    assert ready["present"] is True
    assert ready["trigger_batch_present"] is True
    assert ready["ready"] is True


def test_load_candidates_flattens_and_sorts_prism_output(tmp_path: Path):
    output = tmp_path / "prism_latest_morning.json"
    output.write_text(
        json.dumps(
            {
                "거래량 급증 상위주": [
                    {"code": "000001", "name": "낮은점수", "profit_score": 55},
                    {"code": "000002", "name": "높은점수", "profit_score": 82},
                ],
                "metadata": {"trigger_mode": "morning"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    candidates = _load_candidates(output)

    assert [candidate["code"] for candidate in candidates] == ["000002", "000001"]
    assert candidates[0]["trigger_type"] == "거래량 급증 상위주"


def test_format_candidate_summary_includes_target_and_stop_loss():
    text = _format_candidate_summary(
        "morning",
        [
            {
                "code": "000002",
                "name": "테스트종목",
                "profit_score": 82.345,
                "target_price": 12345.6,
                "stop_loss_pct": 5,
            }
        ],
    )

    assert "[오전 후보 TOP 1]" in text
    assert "테스트종목(000002)" in text
    assert "점수 82.34" in text
    assert "목표 12,346" in text
    assert "손절 5.00%" in text