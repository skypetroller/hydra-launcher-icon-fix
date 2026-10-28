"""Small leveled logger used by the command-line tool and the library code."""
from __future__ import annotations

import datetime as _datetime
import sys
from pathlib import Path
from typing import TextIO

DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40

_PREFIX = {
    DEBUG: "[hydra-fix] debug:",
    INFO: "[hydra-fix]",
    WARNING: "[hydra-fix] WARN:",
    ERROR: "[hydra-fix] ERROR:",
}


class Logger:
    """A deliberately small logger with journal-friendly plain output.

    Info and debug messages go to stdout; warnings and errors go to stderr.
    An optional log file receives every message with a timestamp.
    """

    def __init__(
        self,
        *,
        verbose: bool = False,
        quiet: bool = False,
        log_file: Path | str | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.level = DEBUG if verbose else WARNING if quiet else INFO
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.log_file = Path(log_file).expanduser() if log_file else None
        self.warning_count = 0
        self.error_count = 0

    def _write_file(self, level: int, message: str) -> None:
        if self.log_file is None:
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            stamp = _datetime.datetime.now().isoformat(timespec="seconds")
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp} {level}: {message}\n")
        except OSError:
            # Logging must never make the fixer fail.
            pass

    def _emit(self, level: int, message: str) -> None:
        if level < self.level:
            return
        stream = self.stderr if level >= WARNING else self.stdout
        print(f"{_PREFIX[level]} {message}", file=stream, flush=True)
        if level == WARNING:
            self.warning_count += 1
        elif level == ERROR:
            self.error_count += 1
        self._write_file(level, message)

    def debug(self, message: str) -> None:
        self._emit(DEBUG, message)

    def info(self, message: str) -> None:
        self._emit(INFO, message)

    def warning(self, message: str) -> None:
        self._emit(WARNING, message)

    def error(self, message: str) -> None:
        self._emit(ERROR, message)
