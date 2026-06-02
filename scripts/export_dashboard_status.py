"""Export a safe dashboard status JSON file.

The output is designed for dashboard/status.json and never includes plaintext
secrets. It reports only public readiness state and variable names/counts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime import evaluate_startup_safety, load_runtime_secrets, load_runtime_settings

DEFAULT_OUTPUT = Path("dashboard/status.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export agents_invest dashboard status")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="status JSON output path")
    parser.add_argument("--integration-present", action="store_true", help="mark PRISM integration as present")
    parser.add_argument("--paper-approved", action="store_true", help="mark paper validation as approved")
    args = parser.parse_args(argv)

    status = build_status(
        integration_present=args.integration_present or Path("prism-insight").exists(),
        paper_approved=args.paper_approved,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote dashboard status to {output_path}")
    return 0


def build_status(*, integration_present: bool = False, paper_approved: bool = False) -> dict[str, Any]:
    settings = load_runtime_settings()
    secrets = load_runtime_secrets(
        enabled=settings.ssm_settings_enabled,
        prefix=settings.ssm_parameter_prefix,
        region=settings.aws_region,
    )
    safety = evaluate_startup_safety(settings)
    git_sha = _git_value("rev-parse", "--short", "HEAD")
    git_branch = _git_value("rev-parse", "--abbrev-ref", "HEAD")

    kill_switch_off = not settings.kill_switch
    integration_state = "완료" if integration_present else "대기"
    validation_state = "통과" if paper_approved or settings.paper_validation_approved else "미검증"
    secret_state = "done" if secrets.loaded_env_names else "warning"
    overall = "blocked" if settings.kill_switch or not safety.allowed else "ok" if integration_present and validation_state == "통과" else "warning"

    return {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "overall": overall,
        "trading_mode": settings.trading_mode,
        "mode_detail": f"settings={settings.settings_source}, git={git_branch}@{git_sha}",
        "integration_state": integration_state,
        "integration_detail": "prism-insight 폴더 확인됨" if integration_present else "GitHub Actions에서 integrate-prism-insight 실행 필요",
        "kill_switch": "OFF" if kill_switch_off else "ON",
        "kill_switch_detail": "신규 실행 허용" if kill_switch_off else "신규 실행 차단",
        "validation_state": validation_state,
        "validation_detail": "paper 검증 통과" if validation_state == "통과" else "PaperTradingValidator 통과 전 live 금지",
        "timeline": [
            {"title": "보완 모듈 준비", "detail": "수익 점수화, 리스크 차단, 성과 피드백 코드 준비", "state": "done"},
            {"title": "PRISM 원본 통합", "detail": "prism-insight 폴더 확인" if integration_present else "Actions 실행 필요", "state": "done" if integration_present else "warning"},
            {"title": "paper 검증", "detail": "검증 통과" if validation_state == "통과" else "최소 거래 수와 검증 기준 충족 필요", "state": "done" if validation_state == "통과" else "warning"},
            {"title": "AWS 24시간 운영", "detail": "EC2 systemd 또는 GitHub Pages로 PC 없이 운영", "state": "running"},
            {"title": "live 전환", "detail": "모든 안전 조건 통과 전까지 금지", "state": "warning" if validation_state == "통과" else "blocked"},
        ],
        "safety_checks": [
            {"title": "Kill Switch", "detail": "OFF" if kill_switch_off else "ON - 신규 실행 차단", "state": "done" if kill_switch_off else "blocked"},
            {"title": "RiskGovernor", "detail": "주문 직전 포지션/손실/시장 리스크 차단", "state": "done"},
            {"title": "비밀값", "detail": f"loaded={len(secrets.loaded_env_names)}, missing={len(secrets.missing_env_names)}", "state": secret_state},
            {"title": "Startup Safety", "detail": "; ".join(safety.reasons) or "시작 안전 조건 통과", "state": "done" if safety.allowed else "blocked"},
        ],
        "feedback": {
            "trigger_edge": "준비됨",
            "sector_edge": "준비됨",
            "ticker_edge": "준비됨",
        },
    }


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
