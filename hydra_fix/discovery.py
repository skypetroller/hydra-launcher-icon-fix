"""Read-only discovery of Hydra's games, assets, and launch history."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .config import Config
from .log import Logger
from .models import Discovery, Game, GameRecord
from .text import title_case

_UMU_LINE = re.compile(r"umu-(\d+)")
_EXE_VALUE = re.compile(r"'([^']+\.exe)'")
_OBJECT_ID = re.compile(r"objectId=([^&\"'\s]+)")


def parse_umu_log(path: Path) -> Tuple[Dict[str, Tuple[Path, ...]], Dict[str, str]]:
    """Parse Hydra's umu launch log without trusting any individual line."""
    paths: Dict[str, list[Path]] = {}
    names: Dict[str, str] = {}
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return {}, {}

    for line in text.splitlines():
        if "Command:" not in line or ".exe" not in line:
            continue
        appid_match = _UMU_LINE.search(line)
        path_match = _EXE_VALUE.search(line)
        if not (appid_match and path_match):
            continue
        appid = appid_match.group(1)
        executable = Path(path_match.group(1))
        bucket = paths.setdefault(appid, [])
        if executable not in bucket:
            bucket.append(executable)
        executable_name = executable.name
        if executable_name.lower().endswith(".exe"):
            names.setdefault(appid, executable_name[:-4])

    return {appid: tuple(values) for appid, values in paths.items()}, names


def _query_script() -> str:
    return r'''
const { ClassicLevel } = require("classic-level");
const db = new ClassicLevel(process.env.HYDRA_DB_SNAPSHOT, {
  keyEncoding: "utf8",
  valueEncoding: "utf8",
  createIfMissing: false
});
(async () => {
  await db.open();
  try {
    for await (const [key, value] of db.iterator({ gte: "!games!", lt: "!games~" })) {
      if (!key.startsWith("!games!")) continue;
      let game;
      try {
        game = JSON.parse(value);
      } catch (error) {
        continue;
      }
      console.log(JSON.stringify({
        id: game.objectId,
        title: game.title || null,
        isDeleted: game.isDeleted === true,
        executablePath: typeof game.executablePath === "string" ? game.executablePath : null
      }));
    }
  } finally {
    await db.close();
  }
})().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
'''


def read_hydra_records(
    config: Config, logger: Logger
) -> Tuple[Optional[Dict[str, GameRecord]], Optional[str]]:
    """Read the current game records from a temporary LevelDB snapshot.

    Returns ``(records, error)``. ``records`` is ``None`` when the database
    could not be read at all; callers must then fall back to the launch log.
    The live database is never opened directly, so Hydra can keep running.
    """
    if not config.db_path.is_dir():
        return None, f"Hydra database not found at {config.db_path}"
    if config.hydra_bin is None:
        return None, "Hydra launcher binary not found (set HYDRA_BIN or --hydra-bin)"
    if not config.hydra_bin.is_file():
        return None, f"Hydra launcher binary is not a file: {config.hydra_bin}"

    hydra_root = config.hydra_bin.parent
    node_paths = []
    for candidate in (
        hydra_root / "resources" / "app.asar" / "node_modules",
        hydra_root / "resources" / "app.asar.unpacked" / "node_modules",
    ):
        # Node can resolve modules from inside app.asar through Electron's
        # asar integration even though the archive itself is a file.
        if candidate.is_dir() or candidate.parent.is_file():
            node_paths.append(str(candidate))
    if not node_paths:
        return None, "Hydra bundled LevelDB modules were not found"

    try:
        with tempfile.TemporaryDirectory(prefix="hydra-fix-db-") as temporary:
            snapshot = Path(temporary) / "db"
            shutil.copytree(
                config.db_path,
                snapshot,
                ignore=shutil.ignore_patterns("LOCK"),
            )
            environment = os.environ.copy()
            environment["ELECTRON_RUN_AS_NODE"] = "1"
            environment["HYDRA_DB_SNAPSHOT"] = str(snapshot)
            environment["NODE_PATH"] = os.pathsep.join(
                node_paths
                + ([environment["NODE_PATH"]] if environment.get("NODE_PATH") else [])
            )
            result = subprocess.run(
                [str(config.hydra_bin), "-e", _query_script()],
                capture_output=True,
                text=True,
                timeout=15,
                env=environment,
                check=False,
            )
    except (OSError, shutil.Error, subprocess.SubprocessError) as error:
        return None, f"could not snapshot Hydra database: {error}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        return None, f"Hydra database query failed: {detail[:400]}"

    records: Dict[str, GameRecord] = {}
    malformed = 0
    for line in result.stdout.splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        appid = raw.get("id")
        if not appid:
            malformed += 1
            continue
        executable = raw.get("executablePath")
        records[str(appid)] = GameRecord(
            appid=str(appid),
            title=str(raw["title"]) if raw.get("title") else None,
            is_deleted=bool(raw.get("isDeleted")),
            executable_path=Path(executable) if executable else None,
        )
    if malformed:
        logger.debug(f"ignored {malformed} malformed Hydra database record(s)")
    return records, None


def scan_asset_dirs(assets_dir: Path, logger: Logger) -> Dict[str, Path]:
    """Map app IDs to ``Assets/steam-<appid>`` directories."""
    result: Dict[str, Path] = {}
    if not assets_dir.is_dir():
        return result
    try:
        entries = sorted(assets_dir.iterdir(), key=lambda path: path.name)
    except OSError as error:
        logger.warning(f"cannot list Hydra assets: {error}")
        return result
    for entry in entries:
        if not entry.is_dir() or not entry.name.startswith("steam-"):
            continue
        appid = entry.name.split("-", 1)[1]
        if not appid or not re.fullmatch(r"[A-Za-z0-9_.-]+", appid):
            logger.debug(f"ignoring unusual asset directory: {entry.name}")
            continue
        result[appid] = entry
    return result


def discover(config: Config, logger: Logger) -> Discovery:
    """Collect database, log, and asset information without mutating anything."""
    records, db_error = read_hydra_records(config, logger)
    if db_error:
        logger.debug(f"database unavailable: {db_error}")
    umu_paths, umu_names = parse_umu_log(config.umu_log)
    asset_dirs = scan_asset_dirs(config.assets_dir, logger)
    return Discovery(
        records=records,
        db_error=db_error,
        umu_paths=umu_paths,
        umu_names=umu_names,
        asset_dirs=asset_dirs,
    )


def resolve_installed(
    discovery: Discovery, logger: Logger
) -> Dict[str, Path]:
    """Return app ID -> executable path for games that are installed now."""
    installed: Dict[str, Path] = {}
    records = discovery.records

    if records is not None:
        skipped_deleted = 0
        skipped_missing = 0
        for appid, record in records.items():
            if record.is_deleted:
                skipped_deleted += 1
                continue
            executable = record.executable_path
            if executable and executable.is_file():
                installed[appid] = executable
            else:
                skipped_missing += 1
        logger.debug(
            f"database records: {len(installed)} installed, "
            f"{skipped_deleted} deleted, {skipped_missing} without an executable"
        )
        # Preserve support for records that exist only in the launch log (for
        # example games installed by an older Hydra version).
        for appid, paths in discovery.umu_paths.items():
            if appid in records:
                continue
            existing = _latest_existing(paths)
            if existing:
                installed[appid] = existing
        return installed

    for appid, paths in discovery.umu_paths.items():
        existing = _latest_existing(paths)
        if existing:
            installed[appid] = existing
    return installed


def _latest_existing(paths: Iterable[Path]) -> Optional[Path]:
    for path in reversed(list(paths)):
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def existing_managed_name(
    applications_dir: Path, appid: str, logger: Logger
) -> Optional[str]:
    """Find a visible Name from a Hydra shortcut without importing desktop.py."""
    if not applications_dir.is_dir():
        return None
    for path in sorted(applications_dir.glob("*.desktop")):
        if path.is_symlink():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if "hydralauncher://run" not in text:
            continue
        match = _OBJECT_ID.search(text)
        if not match or match.group(1) != appid:
            continue
        if re.search(r"^Hidden\s*=\s*true\s*$", text, re.M | re.I):
            continue
        name_match = re.search(r"^Name\s*=\s*(.+)$", text, re.M)
        if name_match and name_match.group(1).strip():
            return name_match.group(1).strip()
    return None


def game_name(
    appid: str,
    config: Config,
    discovery: Discovery,
    logger: Logger,
) -> str:
    """Choose the most trustworthy name available for a game."""
    if appid in config.known_names:
        return config.known_names[appid]
    record = discovery.records.get(appid) if discovery.records is not None else None
    if record and record.title:
        return record.title
    existing = existing_managed_name(config.applications_dir, appid, logger)
    if existing:
        return existing
    if appid in discovery.umu_names:
        return title_case(discovery.umu_names[appid])
    return f"Hydra Game {appid}"


def build_games(
    config: Config,
    discovery: Discovery,
    installed: Mapping[str, Path],
    logger: Logger,
    only: Sequence[str] = (),
) -> list[Game]:
    """Build the sorted list of games to process."""
    selected = set(only)
    games = []
    for appid in sorted(installed):
        if selected and appid not in selected:
            continue
        record = discovery.records.get(appid) if discovery.records is not None else None
        games.append(
            Game(
                appid=appid,
                name=game_name(appid, config, discovery, logger),
                executable_path=installed[appid],
                asset_dir=discovery.asset_dirs.get(appid),
                record=record,
            )
        )
    return games
