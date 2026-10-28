"""Command-line interface for hydra-fix."""
from __future__ import annotations

import argparse
import re
import sys
import traceback
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import Config
from .dependencies import check_environment, print_checks
from .errors import FatalError, HydraFixError
from .log import Logger
from .models import RunMode, RunOptions
from .runner import run

_APPID = re.compile(r"^[A-Za-z0-9_.-]+$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hydra-fix",
        description=(
            "Fix taskbar and application-menu icons for games installed with "
            "Hydra Launcher."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="report what would change without writing icons or shortcuts",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate dependencies, paths, and Hydra's install location",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fix-desktop-only",
        action="store_true",
        help="repair/purge shortcuts without extracting icons",
    )
    mode.add_argument(
        "--repair-icons-only",
        action="store_true",
        help="extract icons without changing desktop entries",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="APPID",
        default=[],
        help="limit work to one Hydra app ID (repeatable; disables pruning)",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="keep stale or duplicate shortcuts",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate icons even when the cached copy is current",
    )
    parser.add_argument(
        "--no-cache-update",
        action="store_true",
        help="do not run update-desktop-database or gtk-update-icon-cache",
    )
    parser.add_argument("--hydra-bin", metavar="PATH", help="Hydra launcher binary")
    parser.add_argument(
        "--config-dir",
        metavar="PATH",
        help="Hydra config directory (default: ~/.config/hydralauncher)",
    )
    parser.add_argument(
        "--assets-dir",
        metavar="PATH",
        help="Hydra asset directory (default: <config-dir>/Assets)",
    )
    parser.add_argument(
        "--desktop-dir",
        metavar="PATH",
        help="Desktop folder to repair (default: XDG desktop directory)",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show debug details",
    )
    output.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="only show warnings and errors",
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="also append diagnostic output to this file",
    )
    return parser


def _mode(args: argparse.Namespace) -> RunMode:
    if args.repair_icons_only:
        return RunMode.ICONS_ONLY
    if args.fix_desktop_only:
        return RunMode.DESKTOP_ONLY
    return RunMode.FULL


def _validate_only(values: Sequence[str], parser: argparse.ArgumentParser) -> tuple[str, ...]:
    result = []
    for value in values:
        if not _APPID.fullmatch(value):
            parser.error(f"invalid app ID: {value!r}")
        result.append(value)
    return tuple(dict.fromkeys(result))


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    only = _validate_only(args.only, parser)

    logger = Logger(
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=Path(args.log_file).expanduser() if args.log_file else None,
    )

    try:
        config = Config.from_env(
            hydra_bin=args.hydra_bin,
            config_dir=args.config_dir,
            assets_dir=args.assets_dir,
            desktop_dir=args.desktop_dir,
        )
        logger.debug(f"hydra config: {config.hydra_config_dir}")
        logger.debug(f"assets: {config.assets_dir}")
        logger.debug(f"applications: {config.applications_dir}")
        logger.debug(f"icons: {config.icon_dir}")

        if args.check:
            checks = check_environment(
                config, _mode(args), require_watcher=True
            )
            return 1 if print_checks(checks, logger) else 0

        options = RunOptions(
            dry_run=args.dry_run,
            mode=_mode(args),
            only=only,
            prune=not args.no_prune,
            force=args.force,
            update_caches=not args.no_cache_update,
        )
        run(config, options, logger)
        return 0
    except FatalError as error:
        logger.error(f"aborted: {error}")
        return 1
    except HydraFixError as error:
        logger.error(str(error))
        return 1
    except KeyboardInterrupt:
        logger.error("interrupted")
        return 130
    except Exception as error:  # pragma: no cover - last-resort guard
        if args.verbose:
            traceback.print_exc()
        logger.error(
            f"unexpected failure: {error} "
            "(run again with --verbose for a traceback)"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
