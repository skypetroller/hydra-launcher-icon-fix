"""Shared helpers for the unit test suite."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hydra_fix.config import Config  # noqa: E402


def image_command() -> list[str]:
    """Return an ImageMagick command, supporting version 6 and 7."""
    magick = shutil.which("magick")
    if magick:
        return [magick]
    convert = shutil.which("convert")
    if convert:
        return [convert]
    raise RuntimeError("ImageMagick is required for the test suite")


def make_image(path: Path, size: int, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [*image_command(), "-size", f"{size}x{size}", f"xc:{color}", str(path)],
        check=True,
        capture_output=True,
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def make_config(
    root: Path,
    *,
    hydra_bin: Path | None = None,
    env: dict[str, str] | None = None,
) -> Config:
    """Create an isolated Config whose paths all live under ``root``."""
    binary = hydra_bin or executable(root / "bin" / "hydralauncher")
    environment = {
        "HOME": str(root),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "HYDRA_BIN": str(binary),
        "HYDRA_DESKTOP_DIR": str(root / "Desktop"),
    }
    if env:
        environment.update(env)
    return Config.from_env(env=environment, home=str(root))


def make_dirs(config: Config) -> None:
    config.assets_dir.mkdir(parents=True, exist_ok=True)
    config.applications_dir.mkdir(parents=True, exist_ok=True)
    config.desktop_dir.mkdir(parents=True, exist_ok=True)
    config.umu_log.parent.mkdir(parents=True, exist_ok=True)


def clear_environment() -> None:
    """Remove variables that could make a test read the live system."""
    for name in (
        "HYDRA_BIN",
        "HYDRA_CONFIG_DIR",
        "HYDRA_ASSETS_DIR",
        "HYDRA_DB_PATH",
        "HYDRA_UMU_LOG",
        "HYDRA_ICON_DIR",
        "HYDRA_APPLICATIONS_DIR",
        "HYDRA_DESKTOP_DIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    ):
        os.environ.pop(name, None)
