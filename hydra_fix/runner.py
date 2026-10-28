"""Orchestration for one complete or partial repair run."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .cleanup import (
    cleanup_directory,
    remove_duplicate_shortcuts,
)
from .config import Config
from .dependencies import check_environment
from .desktop import (
    choose_target,
    scan_desktop_entries,
    write_generated_desktop,
)
from .discovery import build_games, discover, resolve_installed
from .errors import FatalError
from .icons import extract_icon
from .log import Logger
from .models import RunMode, RunOptions, RunSummary


def _report_checks(config: Config, mode: RunMode, logger: Logger) -> None:
    checks = check_environment(config, mode)
    errors = [check for check in checks if check.status == "error"]
    for check in checks:
        if check.status == "error":
            logger.error(f"check {check.name}: {check.detail}")
            if check.hint:
                logger.error(f"  hint: {check.hint}")
        elif check.status == "warn":
            logger.warning(f"check {check.name}: {check.detail}")
            if check.hint:
                logger.warning(f"  hint: {check.hint}")
        else:
            logger.debug(f"check {check.name}: OK ({check.detail})")
    if errors:
        raise FatalError("environment check failed; fix the errors above and retry")


def _refresh_caches(
    config: Config,
    logger: Logger,
    dry_run: bool,
    update_desktop: bool,
    update_icons: bool,
) -> int:
    updated = 0
    if update_desktop:
        if not config.update_desktop_db_cmd:
            logger.debug("update-desktop-database not installed; skipping menu cache")
        elif dry_run:
            logger.info("would refresh the desktop application database")
        else:
            try:
                result = subprocess.run(
                    [config.update_desktop_db_cmd, str(config.applications_dir)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as error:
                logger.warning(f"cannot refresh desktop database: {error}")
            else:
                if result.returncode == 0:
                    updated += 1
                else:
                    detail = (result.stderr or "").strip().splitlines()
                    logger.warning(
                        "update-desktop-database failed"
                        + (f": {detail[0]}" if detail else "")
                    )

    if update_icons:
        if not config.gtk_update_icon_cache_cmd:
            logger.debug("gtk-update-icon-cache not installed; skipping icon cache")
        elif not config.icon_theme_dir.is_dir():
            logger.debug(f"icon theme directory missing: {config.icon_theme_dir}")
        elif dry_run:
            logger.info("would refresh the icon cache")
        else:
            try:
                result = subprocess.run(
                    [
                        config.gtk_update_icon_cache_cmd,
                        "-f",
                        str(config.icon_theme_dir),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as error:
                logger.warning(f"cannot refresh icon cache: {error}")
            else:
                if result.returncode == 0:
                    updated += 1
                else:
                    # gtk-update-icon-cache can reject user themes with a
                    # pre-existing malformed cache. Removing it lets GTK fall
                    # back to scanning the directory.
                    stale_cache = config.icon_theme_dir / ".icon-theme.cache"
                    if stale_cache.exists():
                        try:
                            stale_cache.unlink()
                        except OSError:
                            pass
                    detail = (result.stderr or "").strip().splitlines()
                    # A user hicolor theme can contain unrelated icons whose
                    # dimensions do not match their folder, which makes
                    # gtk-update-icon-cache reject the whole cache. Removing
                    # the cache is safe: GTK then scans the theme directly.
                    # This is not actionable for the user, so keep it at debug
                    # level instead of producing a warning on every change.
                    logger.debug(
                        "gtk-update-icon-cache rejected the user theme; "
                        "removed the cache so GTK can scan icons directly"
                        + (f": {detail[0]}" if detail else "")
                    )
    return updated


def run(config: Config, options: RunOptions, logger: Logger) -> RunSummary:
    """Execute a repair run. Raises FatalError for unsafe conditions."""
    _report_checks(config, options.mode, logger)

    discovery = discover(config, logger)
    if discovery.records is None:
        if config.db_path.is_dir():
            logger.warning(
                "Hydra database could not be read; falling back to umu.log"
                + (f" ({discovery.db_error})" if discovery.db_error else "")
            )
        else:
            logger.debug(
                "Hydra database not available; using umu.log"
                + (f" ({discovery.db_error})" if discovery.db_error else "")
            )
    else:
        logger.debug(f"read {len(discovery.records)} Hydra game record(s)")

    installed = resolve_installed(discovery, logger)
    selected = set(options.only)
    if selected:
        missing = sorted(selected - set(installed))
        if missing:
            logger.warning("requested app ID(s) are not installed: " + ", ".join(missing))

    games = build_games(config, discovery, installed, logger, options.only)
    # Hydra's database can also list games from a Steam library that Hydra did
    # not install. Only touch games that have Hydra's cached artwork or an
    # existing Hydra shortcut; otherwise we would create blank generic icons
    # and duplicate menu entries.
    managed_appids = {
        entry.appid
        for entry in scan_desktop_entries(config.applications_dir, logger)
        if entry.managed and entry.appid
    }
    games = [
        game
        for game in games
        if game.asset_dir is not None or game.appid in managed_appids
    ]
    summary = RunSummary()
    needs_icons = options.mode in {RunMode.FULL, RunMode.ICONS_ONLY}
    needs_desktop = options.mode in {RunMode.FULL, RunMode.DESKTOP_ONLY}

    if not options.dry_run:
        if needs_icons:
            config.icon_dir.mkdir(parents=True, exist_ok=True)
        if needs_desktop:
            config.applications_dir.mkdir(parents=True, exist_ok=True)

    # Remove hidden, deleted, and provably uninstalled app-menu entries before
    # creating the current set. This is also what makes repeated runs safe.
    if needs_desktop:
        app_cleanup = cleanup_directory(
            config.applications_dir,
            installed,
            discovery,
            config,
            logger,
            only=options.only,
            prune=options.prune,
            repair=False,
            dry_run=options.dry_run,
        )
        summary.purged += len(app_cleanup.purged)
        if app_cleanup.changed:
            summary.note_change()

    primary_by_appid: dict[str, Path] = {}

    for game in games:
        icon_ok = True
        desktop_ok = True

        if needs_icons:
            if game.asset_dir is None:
                logger.warning(
                    f"no cached icon folder for {game.name} ({game.appid}); "
                    "the shortcut will still be written"
                )
                summary.icon_errors += 1
                icon_ok = False
            else:
                result = extract_icon(
                    config,
                    game.appid,
                    game.asset_dir,
                    logger,
                    dry_run=options.dry_run,
                    force=options.force,
                )
                if result is None:
                    logger.warning(
                        f"could not extract an icon for {game.name} ({game.appid})"
                    )
                    summary.icon_errors += 1
                    icon_ok = False
                elif result.changed:
                    summary.icons_written += 1
                    summary.note_change()
                    logger.debug(
                        f"icon {'would be ' if options.dry_run else ''}updated: "
                        f"{result.path}"
                    )
                else:
                    summary.icons_unchanged += 1

        if needs_desktop:
            try:
                target = choose_target(config, game, logger)
                changed = write_generated_desktop(
                    config, game, target, options.dry_run, logger
                )
            except (OSError, ValueError) as error:
                logger.warning(
                    f"could not write a shortcut for {game.name} ({game.appid}): {error}"
                )
                summary.errors += 1
                desktop_ok = False
            else:
                primary_by_appid[game.appid] = target
                if changed:
                    summary.desktops_written += 1
                    summary.note_change()
                    action = "would write" if options.dry_run else "updated"
                    logger.debug(f"shortcut {action}: {target}")
                else:
                    summary.desktops_unchanged += 1

        if icon_ok and desktop_ok:
            logger.info(f"OK: {game.name} ({game.appid})")
        summary.games += 1

    if needs_desktop and options.prune and not options.only:
        duplicates = remove_duplicate_shortcuts(
            config.applications_dir,
            primary_by_appid,
            logger,
            dry_run=options.dry_run,
        )
        if duplicates:
            summary.purged += len(duplicates)
            summary.note_change()

    if needs_desktop:
        desktop_cleanup = cleanup_directory(
            config.desktop_dir,
            installed,
            discovery,
            config,
            logger,
            only=options.only,
            prune=options.prune,
            repair=True,
            dry_run=options.dry_run,
        )
        summary.purged += len(desktop_cleanup.purged)
        summary.repaired += len(desktop_cleanup.repaired)
        if desktop_cleanup.changed:
            summary.note_change()

    if options.update_caches:
        if summary.changed:
            summary.cache_updates = _refresh_caches(
                config,
                logger,
                options.dry_run,
                update_desktop=needs_desktop,
                update_icons=needs_icons,
            )
        else:
            logger.debug("no changes; desktop and icon caches were left alone")

    summary.warnings = logger.warning_count
    summary.errors += logger.error_count
    prefix = "dry run" if options.dry_run else "done"
    logger.info(
        f"{prefix}: {summary.games} games, "
        f"{summary.icons_written} icon(s) {'would be ' if options.dry_run else ''}updated, "
        f"{summary.desktops_written} shortcut(s) {'would be ' if options.dry_run else ''}updated, "
        f"{summary.purged} removed, {summary.repaired} repaired"
    )
    return summary
