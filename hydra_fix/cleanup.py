"""Stale-entry cleanup and shortcut repair."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from .config import Config
from .desktop import (
    repair_hydra_desktop,
    scan_desktop_entries,
)
from .log import Logger
from .models import DesktopEntry, Discovery


@dataclass
class CleanupResult:
    purged: list[Path] = field(default_factory=list)
    repaired: list[Path] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.purged or self.repaired)


def purge_reason(
    entry: DesktopEntry,
    installed: Mapping[str, Path],
    discovery: Discovery,
    only: Sequence[str] = (),
) -> str | None:
    """Explain why a managed entry is stale, or return None to keep it."""
    if not entry.managed or not entry.appid:
        return None
    appid = entry.appid
    if only and appid not in only:
        return None
    if entry.hidden:
        return "Hidden=true"

    records = discovery.records
    record = records.get(appid) if records is not None else None
    if record is not None and record.is_deleted:
        return "game was removed from Hydra"

    if records is not None:
        if record is not None:
            if appid not in installed:
                return "game executable is missing"
            return None
        # The database is authoritative, but an entry may belong to a game
        # recorded only in the launch log after an older migration.
        if appid in discovery.umu_paths and appid not in installed:
            return "game executable is missing"
        return None

    if appid in discovery.umu_paths and appid not in installed:
        return "game executable is missing"
    return None


def _unlink(entry: DesktopEntry, dry_run: bool, logger: Logger) -> bool:
    if entry.path.is_symlink():
        logger.warning(f"skipping symlinked desktop entry: {entry.path}")
        return False
    if dry_run:
        logger.info(f"would remove: {entry.path.name}")
        return True
    try:
        entry.path.unlink()
    except OSError as error:
        logger.warning(f"cannot remove {entry.path}: {error}")
        return False
    logger.info(f"removed: {entry.path.name}")
    return True


def cleanup_directory(
    directory: Path,
    installed: Mapping[str, Path],
    discovery: Discovery,
    config: Config,
    logger: Logger,
    *,
    only: Sequence[str] = (),
    prune: bool = True,
    repair: bool = True,
    dry_run: bool = False,
) -> CleanupResult:
    """Remove stale Hydra shortcuts and repair the remaining ones."""
    result = CleanupResult()
    entries = scan_desktop_entries(directory, logger)

    purged_paths: set[Path] = set()
    if prune and not only:
        for entry in entries:
            reason = purge_reason(entry, installed, discovery, only)
            if reason is None:
                continue
            if _unlink(entry, dry_run, logger):
                result.purged.append(entry.path)
                purged_paths.add(entry.path)
                logger.debug(f"purge reason for {entry.path.name}: {reason}")

    if repair:
        for entry in entries:
            if entry.path in purged_paths or not entry.managed or not entry.appid:
                continue
            if only and entry.appid not in only:
                continue
            if entry.appid not in installed:
                continue
            if repair_hydra_desktop(
                entry, entry.appid, config, dry_run, logger
            ):
                result.repaired.append(entry.path)
                logger.info(f"repaired: {entry.path.name}")

    return result


def remove_duplicate_shortcuts(
    directory: Path,
    primary_by_appid: Mapping[str, Path],
    logger: Logger,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Remove extra managed app-menu entries for games we just regenerated."""
    if not primary_by_appid or not directory.is_dir():
        return []
    removed: list[Path] = []
    for entry in scan_desktop_entries(directory, logger):
        if not entry.managed or not entry.appid:
            continue
        primary = primary_by_appid.get(entry.appid)
        if primary is None or entry.path == primary:
            continue
        if not primary.exists() and not dry_run:
            continue
        if entry.path.is_symlink():
            logger.warning(f"skipping symlinked desktop entry: {entry.path}")
            continue
        if dry_run:
            logger.info(f"would remove duplicate: {entry.path.name}")
            removed.append(entry.path)
            continue
        try:
            entry.path.unlink()
        except OSError as error:
            logger.warning(f"cannot remove duplicate {entry.path}: {error}")
            continue
        logger.info(f"removed duplicate: {entry.path.name}")
        removed.append(entry.path)
    return removed
