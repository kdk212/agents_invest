"""Safe entrypoint for the agents_invest runtime.

The runner keeps the existing startup safety checks, then delegates candidate
selection to the imported PRISM-INSIGHT batch runner when prism-insight/ is
available. It intentionally stays in paper-safe orchestration; live trading is
still blocked by runtime safety and paper validation gates.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:  # Python 3.9 on Amazon Linux has zoneinfo.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

from runtime import evaluate_startup_safety, load_runtime_secrets, load_runtime_settings
from runtime.candidate_history import record_prism_output

ROOT = Path(__file__).resolve().parent
DEFAULT_PRISM_DIR = ROOT / "prism-insight"
DEFAULT_DASHBOARD_DIR = ROOT / "dashboard"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="agents_invest safe runtime runner")
    parser.add_argument("--once", action="store_true", help="run startup checks once and exit")
    parser.add_argument(
        "--run-batch-once",
        action="store_true",
        help="run one PRISM batch cycle after startup checks and exit",
    )
    parser.add_argument(
        "--allow-missing-secrets",
        action="store_true",
        help="return success when only runtime secrets are missing; use for install checks, not trading",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=_env_int("RUN_INTERVAL_SECONDS", 3600),
        help="sleep interval between PRISM batch cycles",
    )
    parser.add_argument(
        "--batch-mode",
        choices=("auto", "morning", "afternoon", "both"),
        default=os.getenv("PRISM_BATCH_MODE", "auto"),
        help="PRISM trigger_batch mode to run",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="log level passed to PRISM trigger_batch.py",
    )
    parser.add_argument(
        "--prism-dir",
        default=os.getenv("PRISM_DIR", str(DEFAULT_PRISM_DIR)),
        help="path to imported PRISM-INSIGHT checkout",
    )
    parser.add_argument(
        "--dashboard-dir",
        default=os.getenv("DASHBOARD_DIR", str(DEFAULT_DASHBOARD_DIR)),
        help="directory where runtime JSON artifacts are written",
    )
    args = parser.parse_args(argv)

    settings = load_runtime_settings()
    secret_result = _load_secrets_for_settings(settings)
    safety = evaluate_startup_safety(settings)
    prism_status = _prism_status(Path(args.prism_dir))
    runtime_ready = _runtime_ready(safety_allowed=safety.allowed, secret_ok=secret_result.ok)
    service_loop = not args.once and not args.run_batch_once
    install_ready = _install_ready(
        safety_allowed=safety.allowed,
        secret_ok=secret_result.ok,
        allow_missing_secrets=args.allow_missing_secrets or service_loop,
    )
    print(
        json.dumps(
            {
                "settings": _public_settings(settings),
                "secrets": _public_secret_result(secret_result),
                "safety": asdict(safety),
                "prism": prism_status,
                "runtime_ready": runtime_ready,
                "install_ready": install_ready,
                "missing_secrets_allowed": bool(args.allow_missing_secrets or service_loop),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    if not install_ready:
        return 2

    if args.once:
        return 0

    if args.run_batch_once:
        if not runtime_ready:
            _print_runtime_waiting(settings=settings, secret_result=secret_result, safety=safety)
            return 2
        return _run_cycle(args, settings=settings, secret_result=secret_result, safety=safety)

    dashboard_dir = Path(args.dashboard_dir).resolve()
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    while True:
        settings = load_runtime_settings()
        secret_result = _load_secrets_for_settings(settings)
        safety = evaluate_startup_safety(settings)
        if not safety.allowed:
            print(
                json.dumps(
                    {
                        "status": "runtime_safety_blocked",
                        "settings": _public_settings(settings),
                        "secrets": _public_secret_result(secret_result),
                        "safety": asdict(safety),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 2

        if not secret_result.ok:
            _refresh_dashboard_status(dashboard_dir)
            _print_runtime_waiting(settings=settings, secret_result=secret_result, safety=safety)
            time.sleep(max(60, args.interval_seconds))
            continue

        result = _run_cycle(args, settings=settings, secret_result=secret_result, safety=safety)
        if result != 0:
            return result
        time.sleep(max(60, args.interval_seconds))


def _run_cycle(args, *, settings, secret_result, safety) -> int:
    prism_dir = Path(args.prism_dir).resolve()
    dashboard_dir = Path(args.dashboard_dir).resolve()
    status = _prism_status(prism_dir)
    if not status["ready"]:
        print(
            json.dumps(
                {
                    "status": "waiting_for_prism_insight_integration",
                    "prism": status,
                    "mode": settings.trading_mode,
                    "settings_source": settings.settings_source,
                    "secret_source": secret_result.source,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0

    dashboard_dir.mkdir(parents=True, exist_ok=True)
    cycle_results = []
    for mode in _selected_batch_modes(args.batch_mode):
        output_path = dashboard_dir / f"prism_latest_{mode}.json"
        cycle_results.append(
            _run_prism_batch(
                prism_dir=prism_dir,
                mode=mode,
                log_level=args.log_level,
                output_path=output_path,
            )
        )

    history_results = _record_candidate_history(cycle_results)
    _refresh_dashboard_status(dashboard_dir)
    ok = all(item["returncode"] == 0 for item in cycle_results)
    telegram_result = _maybe_send_telegram_summary(
        cycle_results=cycle_results,
        settings=settings,
        dashboard_url=os.getenv("DASHBOARD_PUBLIC_URL", "http://13.55.135.136/"),
    )
    print(
        json.dumps(
            {
                "status": "prism_batch_cycle_complete" if ok else "prism_batch_cycle_failed",
                "mode": settings.trading_mode,
                "safety": asdict(safety),
                "history": history_results,
                "telegram": telegram_result,
                "results": cycle_results,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if ok else 2


def _run_prism_batch(*, prism_dir: Path, mode: str, log_level: str, output_path: Path) -> dict[str, object]:
    timeout = _env_int("PRISM_BATCH_TIMEOUT_SECONDS", 900)
    env = os.environ.copy()
    pythonpath_parts = [str(ROOT), str(prism_dir)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    command = [sys.executable, "trigger_batch.py", mode, log_level, "--output", str(output_path)]
    started_at = datetime.now().isoformat(timespec="seconds")
    completed = subprocess.run(
        command,
        cwd=str(prism_dir),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "mode": mode,
        "returncode": completed.returncode,
        "output_file": str(output_path),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _record_candidate_history(cycle_results: list[dict[str, object]]) -> list[dict[str, object]]:
    history_results: list[dict[str, object]] = []
    for result in cycle_results:
        if int(result.get("returncode", 1)) != 0:
            history_results.append(
                {"mode": result.get("mode"), "ok": False, "inserted": 0, "reason": "batch_failed"}
            )
            continue
        output_file = Path(str(result.get("output_file", "")))
        recorded = record_prism_output(output_file, selected_at=str(result.get("finished_at") or ""))
        recorded["mode"] = result.get("mode")
        history_results.append(recorded)
    return history_results


def _maybe_send_telegram_summary(*, cycle_results: list[dict[str, object]], settings, dashboard_url: str) -> dict[str, object]:
    if not settings.telegram_enabled:
        return {"enabled": False, "sent": False, "reason": "telegram_disabled"}

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"enabled": True, "sent": False, "reason": "telegram_secret_missing"}

    summaries: list[str] = []
    for result in cycle_results:
        if int(result.get("returncode", 1)) != 0:
            summaries.append(f"{_label_for_mode(str(result.get('mode', '-')))} 실행 실패")
            continue
        output_file = Path(str(result.get("output_file", "")))
        candidates = _load_candidates(output_file)
        if not candidates:
            summaries.append(f"{_label_for_mode(str(result.get('mode', '-')))} 후보 없음")
            continue
        summaries.append(_format_candidate_summary(str(result.get("mode", "-")), candidates[:3]))

    if not summaries:
        return {"enabled": True, "sent": False, "reason": "no_summary"}

    text = "\n".join(
        [
            "agents_invest PRISM paper 결과",
            f"시간: {_now_seoul().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            *summaries,
            "",
            f"대시보드: {dashboard_url}",
        ]
    )
    return _send_telegram_message(token=token, chat_id=chat_id, text=text)


def _send_telegram_message(*, token: str, chat_id: str, text: str) -> dict[str, object]:
    try:
        import requests

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True},
            timeout=15,
        )
        if response.ok:
            return {"enabled": True, "sent": True, "status_code": response.status_code}
        return {
            "enabled": True,
            "sent": False,
            "status_code": response.status_code,
            "reason": _tail(response.text, lines=3, max_chars=500),
        }
    except Exception as exc:
        return {"enabled": True, "sent": False, "reason": f"{exc.__class__.__name__}: {exc}"}


def _load_candidates(output_file: Path) -> list[dict[str, Any]]:
    if not output_file.exists():
        return []
    try:
        data = json.loads(output_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for trigger_type, value in data.items():
        if trigger_type == "metadata" or not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                rows.append({**item, "trigger_type": trigger_type})
    return sorted(rows, key=lambda item: float(item.get("profit_score", item.get("final_score", 0)) or 0), reverse=True)


def _format_candidate_summary(mode: str, candidates: list[dict[str, Any]]) -> str:
    lines = [f"[{_label_for_mode(mode)} 후보 TOP {len(candidates)}]"]
    for index, item in enumerate(candidates, 1):
        score = _number_text(item.get("profit_score", item.get("final_score", item.get("agent_fit_score"))), 2)
        name = item.get("name") or "이름 없음"
        code = item.get("code") or "-"
        target = _price_text(item.get("target_price"))
        stop = _number_text(item.get("stop_loss_pct"), 2)
        lines.append(f"{index}. {name}({code}) 점수 {score} / 목표 {target} / 손절 {stop}%")
    return "\n".join(lines)


def _refresh_dashboard_status(dashboard_dir: Path) -> None:
    script = ROOT / "scripts" / "export_dashboard_status.py"
    if not script.exists():
        return
    output_path = dashboard_dir / "status.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")])
    subprocess.run(
        [sys.executable, str(script), "--output", str(output_path)],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _print_runtime_waiting(*, settings, secret_result, safety) -> None:
    print(
        json.dumps(
            {
                "status": "waiting_for_runtime_secrets",
                "settings": _public_settings(settings),
                "secrets": _public_secret_result(secret_result),
                "safety": asdict(safety),
                "next_action": "run scripts/configure_runtime_secrets.py --target ssm before PRISM batch execution",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def _selected_batch_modes(batch_mode: str, *, now: datetime | None = None) -> list[str]:
    if batch_mode == "both":
        return ["morning", "afternoon"]
    if batch_mode in {"morning", "afternoon"}:
        return [batch_mode]

    current = now or _now_seoul()
    return ["morning" if current.hour < 12 else "afternoon"]


def _now_seoul() -> datetime:
    if ZoneInfo is None:  # pragma: no cover
        return datetime.now()
    return datetime.now(ZoneInfo("Asia/Seoul"))


def _prism_status(prism_dir: Path) -> dict[str, object]:
    trigger = prism_dir / "trigger_batch.py"
    return {
        "path": str(prism_dir),
        "present": prism_dir.exists(),
        "trigger_batch_present": trigger.exists(),
        "ready": prism_dir.exists() and trigger.exists(),
    }


def _runtime_ready(*, safety_allowed: bool, secret_ok: bool) -> bool:
    return safety_allowed and secret_ok


def _install_ready(*, safety_allowed: bool, secret_ok: bool, allow_missing_secrets: bool) -> bool:
    if allow_missing_secrets:
        return safety_allowed
    return _runtime_ready(safety_allowed=safety_allowed, secret_ok=secret_ok)


def _load_secrets_for_settings(settings):
    return load_runtime_secrets(
        enabled=settings.ssm_settings_enabled,
        prefix=settings.ssm_parameter_prefix,
        region=settings.aws_region,
    )


def _public_settings(settings) -> dict[str, object]:
    public = asdict(settings)
    return {key: value for key, value in public.items() if "secret" not in key and "key" not in key}


def _public_secret_result(secret_result) -> dict[str, object]:
    return {
        "ok": secret_result.ok,
        "source": secret_result.source,
        "loaded_env_names": list(secret_result.loaded_env_names),
        "missing_env_names": list(secret_result.missing_env_names),
        "errors": list(secret_result.errors),
    }


def _label_for_mode(mode: str) -> str:
    return "오전" if mode == "morning" else "오후" if mode == "afternoon" else mode


def _number_text(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _price_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number <= 0:
        return "-"
    return f"{number:,.0f}"


def _tail(text: str, *, lines: int = 20, max_chars: int = 4000) -> str:
    if not text:
        return ""
    selected = "\n".join(text.splitlines()[-lines:])
    return selected[-max_chars:]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


if __name__ == "__main__":
    sys.exit(main())