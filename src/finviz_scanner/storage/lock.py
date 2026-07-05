"""Process lock for non-overlapping runs."""

from __future__ import annotations

import os
from pathlib import Path

from finviz_scanner.errors import LockError
from finviz_scanner.utils import ensure_directory


class ProcessLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        ensure_directory(self.path.parent)
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self._fd, str(os.getpid()).encode("utf-8"))
        except FileExistsError as exc:
            raise LockError(f"Another run appears active: {self.path}") from exc

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self.path.exists():
            self.path.unlink()

    def __enter__(self) -> ProcessLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
