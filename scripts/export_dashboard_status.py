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


NEXT_ACTIONS_PENDING = [
    {
        "title": "EC2 한 방 복구/점검 실행",
        "detail": "최신 반영, PRISM import, 서비스 재시작, 진단을 한 번에 실행",
        "url": "https://github.com/kdk212/agents_invest/blob/main/docs/EC2_ONE_COMMAND_REPAIR_ko.md",
    },
    {
        "title": "비밀값 입력 확인",
        "detail": "OpenAI/KIS/Telegram SecureString 입력과 Telegram 수신 확인",
        "url": "https://github.com/kdk212/agents_invest/blob/main/docs/RUNTIME_SECRET_INPUT_ko.md",
    },
    {
        "title": "현재 다음 단계",
        "detail": "AWS, GitHub, EC2 설치 순서 전체 보기",
        "url": "https://github.com/kdk212/agents_invest/blob/main/docs/NEXT_STEPS_ko.md",
    },
]

NEXT_ACTIONS_INTEGRATED = [
    {
        "title": "EC2 한 방 복구/점검 실행",
        "detail": "서비스 상태, PRISM 후보 결과, Telegram 전송까지 확인",
        "url": "https://github.com/kdk212/agents_invest/blob/main/docs/EC2_ONE_COMMAND_REPAIR_ko.md",
    },
    {
        "title": "비밀값 입력 확인",
        "detail": "OpenAI/KIS/Telegram SecureString 입력과 Telegram 수신 확인",
        "url": "https://github.com/kdk212/agents_invest/blob/main/docs/RUNTIME_SECRET_INPUT_ko.md",
    },
    {
        "title": "live 전환 조건 확인",
        "detail": "paper 검증과 안전장치 확인 전까지 live 금지",
        "url": "https://github.com/kdk212/agents_invest/blob/main/docs/NEXT_STEPS_ko.md",
    },
]


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

    timeline = [
        {"title": "보완 모듈 준비", "detail": "수익 점수화, 리스크 차단, 성과 피드백, SSM 비밀값 로딩 준비", "state": "done"},
        {"title": "AWS Session Manager 복구", "detail": "CloudShell 복붙용 명령 또는 연결된 Session Manager로 EC2 접속 확인", "state": "done" if settings.ssm_settings_enabled else "warning"},
        {"title": "PRISM 원본 통합", "detail": "prism-insight 폴더 확인" if integration_present else "EC2에서 PRISM 원본 복사/패치 필요", "state": "done" if integration_present else "warning"},
        {"title": "EC2 24시간 paper 설치", "detail": "systemd 서비스와 nginx 대시보드 확인", "state": "running"},
        {"title": "paper 검증", "detail": "검증 통과" if validation_state == "통과" else "충분한 거래 수, Telegram 알림, Kill Switch, RiskGovernor 동작 확인 필요", "state": "done" if validation_state == "통과" else "warning"},
        {"title": "live 전환", "detail": "모든 안전 조건 통과 전까지 금지", "state": "warning" if validation_state == "통과" else "blocked"},
    ]

    return {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "overall": overall,
        "trading_mode": settings.trading_mode,
        "mode_detail": f"settings={settings.settings_source}, git={git_branch}@{git_sha}",
        "integration_state": integration_state,
        "integration_detail": "prism-insight 폴더 확인됨" if integration_present else "EC2에서 import_prism_runtime 실행 필요",
        "kill_switch": "OFF" if kill_switch_off else "ON",
        "kill_switch_detail": "신규 실행 허용" if kill_switch_off else "신규 실행 차단",
        "validation_state": validation_state,
        "validation_detail": "paper 검증 통과" if validation_state == "통과" else "PaperTradingValidator 통과 전 live 금지",
        "timeline": timeline,
        "safety_checks": [
            {"title": "Kill Switch", "detail": "OFF" if kill_switch_off else "ON - 신규 실행 차단", "state": "done" if kill_switch_off else "blocked"},
            {"title": "RiskGovernor", "detail": "주문 직전 포지션/손실/시장 리스크 차단", "state": "done"},
            {"title": "비밀값", "detail": f"loaded={len(secrets.loaded_env_names)}, missing={len(secrets.missing_env_names)}", "state": secret_state},
            {"title": "Startup Safety", "detail": "; ".join(safety.reasons) or "시작 안전 조건 통과", "state": "done" if safety.allowed else "blocked"},
            {"title": "PRISM 통합", "detail": "prism-insight 폴더 확인됨" if integration_present else "EC2에서 원본 복사와 패치 필요", "state": "done" if integration_present else "warning"},
        ],
        "feedback": {
            "trigger_edge": "준비됨",
            "sector_edge": "준비됨",
            "ticker_edge": "준비됨",
        },
        "next_actions": NEXT_ACTIONS_INTEGRATED if integration_present else NEXT_ACTIONS_PENDING,
    }


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())