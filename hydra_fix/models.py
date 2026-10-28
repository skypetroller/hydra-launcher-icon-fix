"""Typed data used across discovery, desktop generation, and cleanup."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class GameRecord:
    """A game record read from Hydra's LevelDB database."""

    appid: str
    title: Optional[str] = None
    is_deleted: bool = False
    executable_path: Optional[Path] = None


@dataclass(frozen=True)
class Discovery:
    """Everything learned from Hydra's files before any change is made."""

    records: Optional[Mapping[str, GameRecord]]
    db_error: Optional[str]
    umu_paths: Mapping[str, Tuple[Path, ...]]
    umu_names: Mapping[str, str]
    asset_dirs: Mapping[str, Path]

    @property
    def database_available(self) -> bool:
        return self.records is not None


@dataclass(frozen=True)
class Game:
    """An installed game that the fixer may need to process."""

    appid: str
    name: str
    executable_path: Optional[Path]
    asset_dir: Optional[Path]
    record: Optional[GameRecord] = None


@dataclass(frozen=True)
class DesktopEntry:
    """A parsed .desktop file relevant to Hydra."""

    path: Path
    text: str
    name: Optional[str]
    icon: Optional[str]
    exec_value: Optional[str]
    startup_wm_class: Optional[str]
    hidden: bool
    appid: Optional[str]
    managed: bool

    @property
    def is_symlink(self) -> bool:
        return self.path.is_symlink()


@dataclass(frozen=True)
class IconResult:
    """The outcome of trying to install one game's icon."""

    path: Path
    changed: bool
    source: Optional[Path] = None
    frame: int = 0
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class CheckResult:
    """One environment check shown by ``hydra-fix --check``."""

    name: str
    status: str  # "ok", "warn", or "error"
    detail: str
    hint: Optional[str] = None


class RunMode(str, Enum):
    FULL = "full"
    ICONS_ONLY = "icons-only"
    DESKTOP_ONLY = "desktop-only"


@dataclass(frozen=True)
class RunOptions:
    dry_run: bool = False
    mode: RunMode = RunMode.FULL
    only: Tuple[str, ...] = ()
    prune: bool = True
    force: bool = False
    update_caches: bool = True


@dataclass
class RunSummary:
    """Counts collected while a run is in progress."""

    games: int = 0
    icons_written: int = 0
    icons_unchanged: int = 0
    icon_errors: int = 0
    desktops_written: int = 0
    desktops_unchanged: int = 0
    purged: int = 0
    repaired: int = 0
    cache_updates: int = 0
    warnings: int = 0
    errors: int = 0
    changed: bool = False
    messages: list[str] = field(default_factory=list)

    def note_change(self) -> None:
        self.changed = True
