"""Windows Task Scheduler command generation."""

from __future__ import annotations

import sys
from pathlib import Path

from finviz_scanner.config import Settings

TASK_NAME = "FinvizWeeklyScanner"


def scheduled_task_command(settings: Settings, project_dir: Path | None = None) -> str:
    root = project_dir or Path.cwd()
    script = root / "scripts" / "run_scan.ps1"
    logs = settings.output.root_directory / "logs"
    return (
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{script.resolve()}" '
        f'-ProjectRoot "{root.resolve()}" -LogDirectory "{logs.resolve()}"'
    )


def schtasks_create_args(settings: Settings, project_dir: Path | None = None) -> list[str]:
    return [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/SC",
        "WEEKLY",
        "/D",
        settings.schedule.day[:3].upper(),
        "/ST",
        settings.schedule.time,
        "/TR",
        scheduled_task_command(settings, project_dir),
        "/F",
    ]


def python_executable() -> Path:
    return Path(sys.executable).resolve()
