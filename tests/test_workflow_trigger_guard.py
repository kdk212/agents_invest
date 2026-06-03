from pathlib import Path

from scripts.check_workflow_triggers import check_workflows


def test_workflow_trigger_guard_accepts_manual_only(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "manual.yml").write_text(
        "name: manual\n\non:\n  workflow_dispatch:\n\njobs:\n  ok:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        encoding="utf-8",
    )

    result = check_workflows(workflow_dir)

    assert result["ok"] is True
    assert result["issues"] == []


def test_workflow_trigger_guard_rejects_push_trigger(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "push.yml").write_text(
        "name: push\n\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\n\njobs:\n  bad:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo bad\n",
        encoding="utf-8",
    )

    result = check_workflows(workflow_dir)

    assert result["ok"] is False
    assert result["issues"][0]["forbidden_triggers"] == ["push"]


def test_workflow_trigger_guard_rejects_missing_manual_trigger(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "schedule.yml").write_text(
        "name: scheduled\n\non:\n  schedule:\n    - cron: '0 0 * * *'\n\njobs:\n  bad:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo bad\n",
        encoding="utf-8",
    )

    result = check_workflows(workflow_dir)

    assert result["ok"] is False
    assert result["issues"][0]["forbidden_triggers"] == ["schedule"]
    assert result["issues"][0]["missing_workflow_dispatch"] is True
