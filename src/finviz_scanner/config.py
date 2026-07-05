"""Configuration loading, validation, and first-run prompts."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from finviz_scanner.errors import ConfigurationError
from finviz_scanner.utils import validate_finviz_url

DEFAULT_OUTPUT_DIR = Path.cwd() / "Documents" / "FinvizWeeklyScanner"
CONFIG_PATH = Path.home() / "AppData" / "Local" / "finviz-weekly-scanner" / "settings.yaml"


class AppConfig(BaseModel):
    name: str = "finviz-stage2-weekly"
    timezone: str = "America/Denver"


class ScheduleConfig(BaseModel):
    day: str = "saturday"
    time: str = "08:00"
    retries: int = 2
    retry_delay_minutes: int = 15

    @field_validator("day")
    @classmethod
    def validate_day(cls, value: str) -> str:
        allowed = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        lowered = value.lower()
        if lowered not in allowed:
            msg = f"Schedule day must be one of {sorted(allowed)}."
            raise ValueError(msg)
        return lowered

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            msg = "Schedule time must be HH:MM."
            raise ValueError(msg)
        hour, minute = int(parts[0]), int(parts[1])
        if hour not in range(24) or minute not in range(60):
            msg = "Schedule time must be HH:MM in 24-hour time."
            raise ValueError(msg)
        return f"{hour:02d}:{minute:02d}"


class FinvizConfig(BaseModel):
    saved_screen_url: str
    expected_page_size: int = 20
    browser_headless: bool = True
    save_screenshots: bool = True
    extraction_mode: str = "dom"
    allow_ocr_fallback: bool = False

    @field_validator("saved_screen_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_finviz_url(value)


class ValidationConfig(BaseModel):
    require_exact_count: bool = True
    fail_on_unresolved_exchange: bool = True
    fail_on_duplicate_ticker: bool = False


class OutputConfig(BaseModel):
    root_directory: Path = Field(default_factory=lambda: DEFAULT_OUTPUT_DIR)
    tradingview_sort: str = "finviz_rank"
    generate_csv: bool = True
    generate_json: bool = True
    generate_markdown_report: bool = True


class NotificationConfig(BaseModel):
    provider: str = "local"
    recipients: list[str] = Field(default_factory=list)
    attach_tradingview_file: bool = True
    attach_report: bool = True


class TradingViewConfig(BaseModel):
    automated_upload_enabled: bool = False
    target_watchlist_name: str = "Stage 2 Weekly"


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    finviz: FinvizConfig
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    tradingview: TradingViewConfig = Field(default_factory=TradingViewConfig)


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    if not path.exists():
        msg = f"Configuration file not found: {path}. Run 'finviz-scanner configure'."
        raise ConfigurationError(msg)
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    try:
        return Settings.model_validate(raw)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def write_settings(settings: Settings, path: Path = CONFIG_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = settings.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, sort_keys=False)
    return path


def settings_exists(path: Path = CONFIG_PATH) -> bool:
    return path.exists()
