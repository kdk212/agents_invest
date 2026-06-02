from scripts.check_integration import build_report


def test_integration_report_matches_current_upstream_state():
    report = build_report()

    assert report["optimization_modules_present"]
    assert report["next_steps"]

    if report["upstream_present"]:
        assert report["ready_for_adapter_wiring"]
        assert not report["upstream_missing"]
    else:
        assert not report["ready_for_adapter_wiring"]
        assert "prism-insight/trigger_batch.py" in report["upstream_missing"]
