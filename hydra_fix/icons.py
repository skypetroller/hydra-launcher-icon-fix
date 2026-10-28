"""Icon discovery and extraction with ImageMagick."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .config import Config
from .log import Logger
from .models import IconResult

ICON_EXTENSIONS = (".ico", ".png", ".webp", ".jpg", ".jpeg", ".bmp", ".gif")
ICON_SIZE = 256


@dataclass(frozen=True)
class IconFrame:
    source: Path
    index: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def spec(self) -> str:
        return f"{self.source}[{self.index}]"


def probe_icon(config: Config, path: Path) -> Optional[tuple[str, int, int]]:
    """Return (format, width, height) for a valid image, or None."""
    if not config.identify_cmd:
        return None
    try:
        if not path.is_file():
            return None
        result = subprocess.run(
            [*config.identify_cmd, "-format", "%m %w %h\n", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    first = result.stdout.splitlines()[0].strip() if result.stdout.splitlines() else ""
    parts = first.split()
    if len(parts) != 3:
        return None
    image_format, width, height = parts
    try:
        return image_format.upper(), int(width), int(height)
    except ValueError:
        return None


def validate_icon(config: Config, path: Path) -> bool:
    probed = probe_icon(config, path)
    return bool(probed and probed[0] == "PNG" and probed[1:] == (ICON_SIZE, ICON_SIZE))


def icon_sources(asset_dir: Path) -> list[Path]:
    """Return plausible cached image files, newest name ordering stable."""
    try:
        entries = sorted(asset_dir.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    return [
        entry
        for entry in entries
        if entry.is_file() and entry.suffix.lower() in ICON_EXTENSIONS
    ]


def _frames_for_source(
    config: Config, source: Path, logger: Logger
) -> list[IconFrame]:
    if not config.identify_cmd:
        return []
    try:
        result = subprocess.run(
            [
                *config.identify_cmd,
                "-format",
                "%w %h %p\n",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.debug(f"cannot inspect {source.name}: {error}")
        return []
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        logger.debug(
            f"ignoring unreadable image {source.name}"
            + (f": {detail[0]}" if detail else "")
        )
        return []

    frames = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            width, height, index = (int(part) for part in parts)
        except ValueError:
            continue
        if width <= 0 or height <= 0 or index < 0:
            continue
        frames.append(IconFrame(source=source, index=index, width=width, height=height))
    if not frames:
        logger.debug(f"no image frames found in {source.name}")
    return frames


def collect_frames(config: Config, asset_dir: Path, logger: Logger) -> list[IconFrame]:
    frames: list[IconFrame] = []
    for source in icon_sources(asset_dir):
        try:
            frames.extend(_frames_for_source(config, source, logger))
        except OSError as error:
            logger.debug(f"cannot read {source.name}: {error}")
    # Prefer the highest resolution, regardless of which file contains it.
    frames.sort(key=lambda frame: (frame.area, frame.width, frame.index), reverse=True)
    return frames


def icon_is_current(config: Config, output: Path, sources: Iterable[Path]) -> bool:
    if not validate_icon(config, output):
        return False
    source_list = list(sources)
    if not source_list:
        return True
    try:
        output_mtime = output.stat().st_mtime
        newest_source = max(source.stat().st_mtime for source in source_list)
    except OSError:
        return False
    return output_mtime >= newest_source


def _extract_frame(
    config: Config, frame: IconFrame, output: Path, logger: Logger
) -> bool:
    if not config.convert_cmd:
        return False
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=".tmp.png", dir=str(output.parent)
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        try:
            result = subprocess.run(
                [
                    *config.convert_cmd,
                    frame.spec,
                    "-background",
                    "none",
                    "-gravity",
                    "center",
                    "-resize",
                    f"{ICON_SIZE}x{ICON_SIZE}",
                    "-extent",
                    f"{ICON_SIZE}x{ICON_SIZE}",
                    "-depth",
                    "8",
                    str(temporary),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.debug(f"convert failed for {frame.source.name}: {error}")
            return False
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()
            logger.debug(
                f"convert failed for {frame.source.name}[{frame.index}]"
                + (f": {detail[0]}" if detail else "")
            )
            return False
        if not validate_icon(config, temporary):
            logger.debug(f"converted image is not a valid 256x256 PNG: {frame.source.name}")
            return False
        os.replace(temporary, output)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def extract_icon(
    config: Config,
    appid: str,
    asset_dir: Path,
    logger: Logger,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> Optional[IconResult]:
    """Install the largest cached frame as ``steam_icon_<appid>.png``.

    Returns ``None`` only when no usable image could be produced and no valid
    icon already exists. A returned result with ``changed=False`` means the
    existing icon is already current.
    """
    output = config.icon_dir / f"steam_icon_{appid}.png"
    sources = icon_sources(asset_dir)

    if not force and icon_is_current(config, output, sources):
        return IconResult(path=output, changed=False)

    frames = collect_frames(config, asset_dir, logger)
    if not frames:
        if validate_icon(config, output):
            return IconResult(path=output, changed=False)
        return None

    best = frames[0]
    if dry_run:
        return IconResult(
            path=output,
            changed=True,
            source=best.source,
            frame=best.index,
            width=ICON_SIZE,
            height=ICON_SIZE,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        if _extract_frame(config, frame, output, logger):
            logger.debug(
                f"icon {appid}: {frame.source.name}[{frame.index}] "
                f"{frame.width}x{frame.height} -> {output.name}"
            )
            return IconResult(
                path=output,
                changed=True,
                source=frame.source,
                frame=frame.index,
                width=ICON_SIZE,
                height=ICON_SIZE,
            )
    return None
