from datetime import datetime
from pathlib import Path

from agents_invest_runner import _prism_status, _selected_batch_modes


def test_selected_batch_modes_explicit_values():
    assert _selected_batch_modes("morning") == ["morning"]
    assert _selected_batch_modes("afternoon") == ["afternoon"]
    assert _selected_batch_modes("both") == ["morning", "afternoon"]


def test_selected_batch_modes_auto_uses_korea_market_half_day_split():
    assert _selected_batch_modes("auto", now=datetime(2026, 6, 3, 9, 30)) == ["morning"]
    assert _selected_batch_modes("auto", now=datetime(2026, 6, 3, 13, 10)) == ["afternoon"]


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