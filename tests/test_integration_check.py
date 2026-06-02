from scripts.check_integration import build_report


def test_integration_report_knows_upstream_is_not_imported_yet():
    report = build_report()

    assert report["optimization_modules_present"]
    assert not report["upstream_present"]
    assert not report["ready_for_adapter_wiring"]
    assert "prism-insight/trigger_batch.py" in report["upstream_missing"]
    assert report["next_steps"]
