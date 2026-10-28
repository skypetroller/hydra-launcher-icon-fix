"""Pre-flight environment checks with actionable messages."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

from .config import Config
from .log import Logger
from .models import CheckResult, RunMode


def _command(name: str) -> bool:
    return shutil.which(name) is not None


def check_environment(
    config: Config,
    mode: RunMode,
    *,
    require_watcher: bool = False,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    needs_icons = mode in {RunMode.FULL, RunMode.ICONS_ONLY}
    needs_desktop = mode in {RunMode.FULL, RunMode.DESKTOP_ONLY}

    if config.assets_dir.is_dir():
        checks.append(CheckResult("Hydra Assets", "ok", str(config.assets_dir)))
    else:
        checks.append(
            CheckResult(
                "Hydra Assets",
                "error",
                f"directory not found: {config.assets_dir}",
                "Start Hydra once so it creates its data directories, or set "
                "HYDRA_CONFIG_DIR / --config-dir.",
            )
        )

    if config.hydra_bin is None:
        checks.append(
            CheckResult(
                "Hydra launcher",
                "error" if needs_desktop else "warn",
                "hydralauncher binary not found",
                "Install Hydra, or pass --hydra-bin /path/to/hydralauncher "
                "(or set HYDRA_BIN).",
            )
        )
    elif not config.hydra_bin.is_file():
        checks.append(
            CheckResult(
                "Hydra launcher",
                "error" if needs_desktop else "warn",
                f"not a file: {config.hydra_bin}",
                "Pass --hydra-bin with the real launcher path.",
            )
        )
    elif not os.access(config.hydra_bin, os.X_OK):
        checks.append(
            CheckResult(
                "Hydra launcher",
                "error",
                f"not executable: {config.hydra_bin}",
                "Fix the file permissions or pass the correct --hydra-bin.",
            )
        )
    else:
        checks.append(CheckResult("Hydra launcher", "ok", str(config.hydra_bin)))

    if config.db_path.is_dir():
        checks.append(CheckResult("Hydra database", "ok", str(config.db_path)))
    else:
        checks.append(
            CheckResult(
                "Hydra database",
                "warn",
                f"not found: {config.db_path}",
                "New games will be detected from umu.log until Hydra creates "
                "its database.",
            )
        )

    if config.umu_log.is_file():
        checks.append(CheckResult("Launch log", "ok", str(config.umu_log)))
    else:
        checks.append(
            CheckResult(
                "Launch log",
                "warn",
                f"not found: {config.umu_log}",
                "Games are still detected from Hydra's database.",
            )
        )

    if needs_icons:
        if config.identify_cmd:
            checks.append(
                CheckResult("ImageMagick identify", "ok", " ".join(config.identify_cmd))
            )
        else:
            checks.append(
                CheckResult(
                    "ImageMagick identify",
                    "error",
                    "identify command not found",
                    "Install it with: sudo apt install imagemagick "
                    "(or your distribution's package).",
                )
            )
        if config.convert_cmd:
            checks.append(
                CheckResult("ImageMagick convert", "ok", " ".join(config.convert_cmd))
            )
        else:
            checks.append(
                CheckResult(
                    "ImageMagick convert",
                    "error",
                    "convert command not found",
                    "Install it with: sudo apt install imagemagick "
                    "(or your distribution's package).",
                )
            )
    else:
        checks.append(
            CheckResult(
                "ImageMagick",
                "ok",
                "not needed for --fix-desktop-only",
            )
        )

    if config.update_desktop_db_cmd:
        checks.append(CheckResult("update-desktop-database", "ok", config.update_desktop_db_cmd))
    else:
        checks.append(
            CheckResult(
                "update-desktop-database",
                "warn",
                "command not found",
                "Install desktop-file-utils for reliable menu refreshes: "
                "sudo apt install desktop-file-utils",
            )
        )

    if config.gtk_update_icon_cache_cmd:
        checks.append(
            CheckResult("gtk-update-icon-cache", "ok", config.gtk_update_icon_cache_cmd)
        )
    else:
        checks.append(
            CheckResult(
                "gtk-update-icon-cache",
                "warn",
                "command not found",
                "Install gtk-update-icon-cache (usually part of GTK) to refresh icons.",
            )
        )

    if config.desktop_dir.is_dir():
        checks.append(CheckResult("Desktop folder", "ok", str(config.desktop_dir)))
    else:
        checks.append(
            CheckResult(
                "Desktop folder",
                "warn",
                f"not found: {config.desktop_dir}",
                "Desktop shortcut repair will be skipped. Set HYDRA_DESKTOP_DIR "
                "if your Desktop is elsewhere.",
            )
        )

    if require_watcher:
        for command, package in (
            ("inotifywait", "inotify-tools"),
            ("flock", "util-linux"),
            ("systemctl", "systemd"),
        ):
            if _command(command):
                checks.append(CheckResult(command, "ok", shutil.which(command) or ""))
            else:
                checks.append(
                    CheckResult(
                        command,
                        "error",
                        "command not found",
                        f"Install it with your package manager ({package}).",
                    )
                )

    return checks


def print_checks(checks: Iterable[CheckResult], logger: Logger) -> int:
    """Print a check table and return the number of errors."""
    errors = 0
    for check in checks:
        if check.status == "ok":
            logger.info(f"check {check.name}: OK ({check.detail})")
        elif check.status == "warn":
            logger.warning(f"check {check.name}: {check.detail}")
            if check.hint:
                logger.warning(f"  hint: {check.hint}")
        else:
            errors += 1
            logger.error(f"check {check.name}: {check.detail}")
            if check.hint:
                logger.error(f"  hint: {check.hint}")
    return errors


def format_check(check: CheckResult) -> str:
    suffix = f" - {check.hint}" if check.hint else ""
    return f"{check.name}: {check.status} ({check.detail}){suffix}"
