from scripts.check_integration import build_report, is_success


def test_integration_report_matches_current_upstream_state():
    report = build_report()

    assert report["optimization_modules_present"]
    assert report["next_steps"]

    if report["upstream_present"]:
        assert report["ready_for_adapter_wiring"]
        assert not report["upstream_missing"]
        assert is_success(report) == report["fully_wired"]
    else:
        assert not report["ready_for_adapter_wiring"]
        assert "prism-insight/trigger_batch.py" in report["upstream_missing"]
        assert not is_success(report)
        assert is_success(report, allow_missing_upstream=True)
