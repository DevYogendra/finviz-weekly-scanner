"""Logging redaction helpers."""

from __future__ import annotations

import logging

from finviz_scanner.utils import redact_secrets


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging(run_id: str = "-") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s run_id=%(run_id)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    old_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "run_id"):
            record.run_id = run_id
        return record

    logging.setLogRecordFactory(factory)
