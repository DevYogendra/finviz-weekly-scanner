"""Configuration loading, validation, and first-run prompts."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from finviz_scanner.errors import ConfigurationError
from finviz_scanner.models import FinvizScreenConfig
from finviz_scanner.utils import validate_finviz_url

DEFAULT_OUTPUT_DIR = Path.cwd() / "Documents" / "FinvizWeeklyScanner"
CONFIG_PATH = Path.home() / "AppData" / "Local" / "finviz-weekly-scanner" / "settings.yaml"
SCREEN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")


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


class ScreenConfig(BaseModel):
    id: str
    name: str
    url: str
    enabled: bool = True
    tradingview_filename: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not SCREEN_ID_PATTERN.fullmatch(normalized):
            msg = "Screen ID must match ^[a-z0-9][a-z0-9_-]{0,49}$ and contain no path separators."
            raise ValueError(msg)
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Screen name must be non-empty."
            raise ValueError(msg)
        return stripped

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_finviz_url(value)

    @field_validator("tradingview_filename")
    @classmethod
    def validate_tradingview_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            msg = "TradingView output filename must be non-empty when configured."
            raise ValueError(msg)
        path = Path(stripped)
        if path.name != stripped or path.is_absolute() or "/" in stripped or "\\" in stripped:
            msg = "TradingView output filename must be a basename only."
            raise ValueError(msg)
        return stripped

    def to_domain(self) -> FinvizScreenConfig:
        return FinvizScreenConfig(
            id=self.id,
            name=self.name,
            url=self.url,
            enabled=self.enabled,
            tradingview_filename=self.tradingview_filename,
        )


class FinvizConfig(BaseModel):
    saved_screen_url: str | None = None
    screens: list[ScreenConfig] | None = None
    delay_between_screens_ms: int = 1000
    expected_page_size: int = 20
    browser_headless: bool = True
    save_screenshots: bool = True
    extraction_mode: str = "dom"
    allow_ocr_fallback: bool = False

    @field_validator("saved_screen_url")
    @classmethod
    def validate_legacy_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_finviz_url(value)

    @field_validator("delay_between_screens_ms")
    @classmethod
    def validate_delay(cls, value: int) -> int:
        if value < 0:
            msg = "Delay between screens must be zero or greater."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_screen_configuration(self) -> FinvizConfig:
        if self.screens is not None and self.saved_screen_url is not None:
            msg = "Configure either finviz.screens or finviz.saved_screen_url, not both."
            raise ValueError(msg)
        if self.screens is None and self.saved_screen_url is None:
            msg = "At least one Finviz screen must be configured."
            raise ValueError(msg)
        screens = self.resolved_screens()
        seen_ids: dict[str, str] = {}
        seen_outputs: dict[str, str] = {}
        for screen in screens:
            lowered_id = screen.id.lower()
            if lowered_id in seen_ids:
                msg = f"screen IDs must be unique. Duplicate ID: {screen.id}"
                raise ValueError(msg)
            seen_ids[lowered_id] = screen.id
            output = self.tradingview_filename_for(screen).lower()
            if output in seen_outputs:
                msg = (
                    f"screens '{seen_outputs[output]}' and '{screen.id}' "
                    f"both resolve to output file '{self.tradingview_filename_for(screen)}'."
                )
                raise ValueError(msg)
            seen_outputs[output] = screen.id
        return self

    def resolved_screens(self) -> list[FinvizScreenConfig]:
        if self.screens is not None:
            return [screen.to_domain() for screen in self.screens]
        if self.saved_screen_url is not None:
            return [
                FinvizScreenConfig(
                    id="default",
                    name="Default Screen",
                    url=self.saved_screen_url,
                    enabled=True,
                )
            ]
        return []

    @staticmethod
    def tradingview_filename_for(screen: FinvizScreenConfig) -> str:
        filename = screen.tradingview_filename or f"{screen.id}.txt"
        parsed = urlparse(filename)
        if parsed.scheme or parsed.netloc:
            msg = "TradingView output filename must be a basename only."
            raise ValueError(msg)
        return filename


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
