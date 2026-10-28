"""Creation, validation, and repair of Hydra .desktop entries."""
from __future__ import annotations

import configparser
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from .config import Config
from .log import Logger
from .models import DesktopEntry, Game
from .text import desktop_value, safe_filename

_APPID = re.compile(r"objectId=([^&\"'\s]+)")
_BROKEN_SHEBANG = "#!/user/bin/env xdg-open"
_GOOD_SHEBANG = "#!/usr/bin/env xdg-open"
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _parse_values(text: str) -> Optional[dict[str, str]]:
    parser = configparser.RawConfigParser(
        interpolation=None,
        strict=False,
        allow_no_value=True,
    )
    parser.optionxform = str  # preserve key case
    try:
        parser.read_string(text)
    except (configparser.Error, UnicodeError):
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    values: dict[str, str] = {}
    for key, value in parser.items("Desktop Entry", raw=True):
        values[key] = "" if value is None else value
    return values


def extract_appid(text: str) -> Optional[str]:
    match = _APPID.search(text)
    return match.group(1) if match else None


def parse_desktop(
    path: Path, logger: Optional[Logger] = None
) -> Optional[DesktopEntry]:
    try:
        if path.stat().st_size > 1_000_000:
            if logger:
                logger.debug(f"ignoring oversized desktop entry: {path.name}")
            return None
        text = path.read_text(errors="ignore")
    except OSError as error:
        if logger:
            logger.debug(f"cannot read {path.name}: {error}")
        return None
    values = _parse_values(text)
    if values is None:
        if logger:
            logger.debug(f"ignoring malformed desktop entry: {path.name}")
        return None
    exec_value = values.get("Exec")
    appid = extract_appid(exec_value or "")
    managed = bool(exec_value and "hydralauncher://run" in exec_value)
    hidden = values.get("Hidden", "").strip().lower() == "true"
    return DesktopEntry(
        path=path,
        text=text,
        name=values.get("Name"),
        icon=values.get("Icon"),
        exec_value=exec_value,
        startup_wm_class=values.get("StartupWMClass"),
        hidden=hidden,
        appid=appid,
        managed=managed,
    )


def scan_desktop_entries(directory: Path, logger: Logger) -> list[DesktopEntry]:
    if not directory.is_dir():
        return []
    entries = []
    try:
        paths = sorted(directory.glob("*.desktop"), key=lambda path: path.name)
    except OSError as error:
        logger.warning(f"cannot list {directory}: {error}")
        return []
    for path in paths:
        entry = parse_desktop(path, logger)
        if entry is not None:
            entries.append(entry)
    return entries


def validate_text(text: str) -> list[str]:
    """Return human-readable reasons why generated/edited content is unsafe."""
    errors: list[str] = []
    values = _parse_values(text)
    if values is None:
        return ["missing or malformed [Desktop Entry] section"]
    if _CONTROL.search(text):
        errors.append("contains control characters")
    if values.get("Type", "").strip() != "Application":
        errors.append("Type must be Application")
    name = desktop_value(values.get("Name", ""))
    if not name:
        errors.append("Name is required")
    exec_value = values.get("Exec", "").strip()
    if not exec_value:
        errors.append("Exec is required")
    elif "hydralauncher://run" not in exec_value:
        errors.append("Exec does not contain a Hydra launch URL")
    icon = values.get("Icon", "").strip()
    if not icon:
        errors.append("Icon is required")
    if not values.get("StartupWMClass", "").strip():
        errors.append("StartupWMClass is required")
    if values.get("Hidden", "").strip().lower() == "true":
        errors.append("Hidden=true must not be present")
    terminal = values.get("Terminal", "").strip().lower()
    if terminal and terminal not in {"true", "false"}:
        errors.append("Terminal must be true or false")
    return errors


def quote_exec_arg(value: str) -> str:
    value = str(value)
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("`", "\\`")
    value = value.replace("$", "\\$")
    value = value.replace("%", "%%")
    return f'"{value}"'


def render_desktop(config: Config, game: Game) -> str:
    if config.hydra_bin is None:
        raise ValueError("Hydra launcher binary is not configured")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", game.appid):
        raise ValueError(f"unsafe Hydra app ID: {game.appid!r}")
    url = f"hydralauncher://run?shop=steam&objectId={game.appid}"
    lines = [
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        f"Name={desktop_value(game.name)}",
        "Comment=Managed by hydra-launcher-icon-fix",
        f"Exec={quote_exec_arg(str(config.hydra_bin))} {quote_exec_arg(url)}",
        f"Icon=steam_icon_{game.appid}",
        "Terminal=false",
        "Categories=Game;",
        f"StartupWMClass={config.startup_wm_class(game.appid)}",
        "X-Hydra-Fix=true",
        f"X-Hydra-AppId={game.appid}",
    ]
    text = "\n".join(lines) + "\n"
    errors = validate_text(text)
    if errors:
        raise ValueError("refusing to write invalid desktop entry: " + "; ".join(errors))
    return text


def _path_is_reusable(path: Path, appid: str, logger: Logger) -> bool:
    if path.is_symlink():
        return False
    if not path.exists():
        return True
    entry = parse_desktop(path, logger)
    return bool(entry and entry.managed and entry.appid == appid)


def choose_target(config: Config, game: Game, logger: Logger) -> Path:
    """Pick a shortcut path without ever overwriting an unrelated entry."""
    filename = safe_filename(game.name) + ".desktop"
    candidate = config.applications_dir / filename
    if _path_is_reusable(candidate, game.appid, logger):
        return candidate

    fallback = config.applications_dir / f"hydra-{game.appid}.desktop"
    if _path_is_reusable(fallback, game.appid, logger):
        return fallback

    for index in range(2, 100):
        numbered = config.applications_dir / f"hydra-{game.appid}-{index}.desktop"
        if _path_is_reusable(numbered, game.appid, logger):
            return numbered
    raise OSError(f"could not find a safe shortcut name for {game.name}")


def _atomic_write(path: Path, text: str, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError(f"refusing to overwrite symlink: {path}")
    if mode is None:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            mode = 0o644
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_generated_desktop(
    config: Config,
    game: Game,
    target: Path,
    dry_run: bool,
    logger: Logger,
) -> bool:
    """Write a generated shortcut, returning True when content changed."""
    text = render_desktop(config, game)
    errors = validate_text(text)
    if errors:
        raise ValueError("invalid generated shortcut: " + "; ".join(errors))

    if target.is_symlink():
        raise OSError(f"refusing to overwrite symlink: {target}")
    if target.exists():
        existing = parse_desktop(target, logger)
        if existing is None:
            raise OSError(f"refusing to overwrite unreadable desktop entry: {target.name}")
        if not (existing.managed and existing.appid == game.appid):
            raise OSError(f"refusing to overwrite unrelated desktop entry: {target.name}")
        if existing.text == text:
            return False
    if dry_run:
        return True
    _atomic_write(target, text)
    logger.debug(f"wrote {target}")
    return True


def repair_hydra_desktop(
    entry: DesktopEntry,
    appid: str,
    config: Config,
    dry_run: bool,
    logger: Logger,
) -> bool:
    """Repair a Hydra shortcut on the Desktop (or in the app menu)."""
    if not entry.managed:
        return False
    if entry.path.is_symlink():
        logger.warning(f"skipping symlinked desktop entry: {entry.path}")
        return False

    text = entry.text
    original = text

    if _BROKEN_SHEBANG in text:
        text = text.replace(_BROKEN_SHEBANG, _GOOD_SHEBANG)

    if not re.search(r"^Type\s*=", text, re.M):
        text = text.rstrip("\n") + "\nType=Application\n"

    if not re.search(r"^Name\s*=", text, re.M):
        name = entry.name or f"Hydra Game {appid}"
        text = text.rstrip("\n") + f"\nName={desktop_value(name)}\n"

    icon_value = entry.icon or ""
    expected_icon = f"Icon=steam_icon_{appid}"
    icon_lines = re.findall(r"^Icon\s*=.*$", text, re.M)
    if icon_lines != [expected_icon] or icon_value.lower().endswith(".ico"):
        text = re.sub(r"^Icon\s*=.*\n?", "", text, flags=re.M)
        text = text.rstrip("\n") + f"\n{expected_icon}\n"

    wm_class = f"StartupWMClass={config.startup_wm_class(appid)}"
    wm_lines = re.findall(r"^StartupWMClass\s*=.*$", text, re.M)
    if wm_lines != [wm_class]:
        text = re.sub(r"^StartupWMClass\s*=.*\n?", "", text, flags=re.M)
        text = text.rstrip("\n") + f"\n{wm_class}\n"

    if text == original:
        return False

    errors = validate_text(text)
    if errors:
        logger.warning(
            f"not repairing {entry.path.name}: " + "; ".join(errors)
        )
        return False
    if dry_run:
        return True
    try:
        _atomic_write(entry.path, text)
    except OSError as error:
        logger.warning(f"cannot repair {entry.path}: {error}")
        return False
    logger.debug(f"repaired {entry.path}")
    return True
