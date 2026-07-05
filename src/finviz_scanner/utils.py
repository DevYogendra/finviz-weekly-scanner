"""Small cross-cutting utilities."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

SECRET_PATTERNS = (
    re.compile(r"(cookie|password|token|secret|apikey|api_key)=([^&\s]+)", re.IGNORECASE),
    re.compile(r"(auth|session)[-_]?(id|token)?=([^&\s]+)", re.IGNORECASE),
)


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper().replace("/", ".")
    ticker = re.sub(r"\s+", "", ticker)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", ticker):
        msg = f"Invalid ticker: {value!r}"
        raise ValueError(msg)
    return ticker


def fingerprint_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(0).split("=")[0] + "=<redacted>", redacted)
    return redacted


def validate_finviz_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        msg = "Finviz URL must use HTTPS."
        raise ValueError(msg)
    host = parsed.hostname or ""
    if host not in {"finviz.com", "www.finviz.com"}:
        msg = "Finviz URL must point to finviz.com."
        raise ValueError(msg)
    normalized_path = parsed.path.lower().rstrip("/")
    if normalized_path not in {"/screener", "/screener.ashx"}:
        msg = "Finviz URL must appear to be a screener URL."
        raise ValueError(msg)
    lowered = url.lower()
    if "copy_exact" in lowered or "placeholder" in lowered or "example" in lowered:
        msg = "Finviz URL cannot be a placeholder."
        raise ValueError(msg)
    return url.strip()


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
