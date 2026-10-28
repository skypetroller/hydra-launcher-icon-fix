import tempfile
import unittest
from pathlib import Path

from support import executable, make_config, write

from hydra_fix.discovery import (
    build_games,
    discover,
    parse_umu_log,
    read_hydra_records,
    resolve_installed,
    scan_asset_dirs,
)
from hydra_fix.log import Logger
from hydra_fix.models import Discovery, GameRecord


class DiscoveryTests(unittest.TestCase):
    def test_parse_umu_log_ignores_malformed_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = write(
                root / "umu.log",
                "\n".join(
                    [
                        "not a launch line",
                        "Command: GAMEID='umu-123' wine '/games/My Game.exe'",
                        "Command: GAMEID='umu-123' wine '/games/My Game.exe'",
                        "Command: GAMEID='umu-456' wine '/games/Other.exe'",
                        "Command: no executable here",
                    ]
                ),
            )
            paths, names = parse_umu_log(log)
            self.assertEqual(paths["123"], (Path("/games/My Game.exe"),))
            self.assertEqual(paths["456"], (Path("/games/Other.exe"),))
            self.assertEqual(names["123"], "My Game")

    def test_missing_umu_log_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, names = parse_umu_log(Path(directory) / "missing.log")
            self.assertEqual(paths, {})
            self.assertEqual(names, {})

    def test_database_snapshot_unavailable_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root, hydra_bin=root / "missing-hydralauncher")
            logger = Logger(quiet=True)
            records, error = read_hydra_records(config, logger)
            self.assertIsNone(records)
            self.assertIn("database not found", error)

    def test_database_records_are_used_for_install_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "installed.exe"
            installed.touch()
            discovery = Discovery(
                records={
                    "123": GameRecord("123", executable_path=installed),
                    "456": GameRecord("456", is_deleted=True, executable_path=installed),
                    "789": GameRecord("789", executable_path=root / "missing.exe"),
                },
                db_error=None,
                umu_paths={"999": (installed,)},
                umu_names={},
                asset_dirs={},
            )
            result = resolve_installed(discovery, Logger(quiet=True))
            self.assertEqual(set(result), {"123", "999"})

    def test_log_detection_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "installed.exe"
            installed.touch()
            discovery = Discovery(
                records=None,
                db_error="unavailable",
                umu_paths={
                    "123": (root / "missing.exe", installed),
                    "456": (root / "also-missing.exe",),
                },
                umu_names={},
                asset_dirs={},
            )
            result = resolve_installed(discovery, Logger(quiet=True))
            self.assertEqual(set(result), {"123"})
            self.assertEqual(result["123"], installed)

    def test_asset_scan_ignores_non_steam_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "Assets"
            (assets / "steam-123").mkdir(parents=True)
            (assets / "steam-456").mkdir()
            (assets / "custom").mkdir()
            (assets / "steam-").mkdir()
            (assets / "file.txt").write_text("x")
            result = scan_asset_dirs(assets, Logger(quiet=True))
            self.assertEqual(set(result), {"123", "456"})

    def test_build_games_uses_database_title_and_known_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            installed = root / "game.exe"
            installed.touch()
            discovery = Discovery(
                records={
                    "1030300": GameRecord("1030300", title="Database Name"),
                    "999": GameRecord("999", title="Another Game"),
                },
                db_error=None,
                umu_paths={},
                umu_names={},
                asset_dirs={"1030300": root / "asset-a", "999": root / "asset-b"},
            )
            games = build_games(
                config, discovery, {"1030300": installed, "999": installed}, Logger(quiet=True)
            )
            names = {game.appid: game.name for game in games}
            self.assertEqual(names["1030300"], "Hollow Knight Silksong")
            self.assertEqual(names["999"], "Another Game")

    def test_discover_combines_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root, hydra_bin=root / "missing")
            config.assets_dir.mkdir(parents=True)
            (config.assets_dir / "steam-1").mkdir()
            executable(root / "game.exe")
            write(
                config.umu_log,
                "Command: GAMEID='umu-1' wine '/tmp/game.exe'",
            )
            result = discover(config, Logger(quiet=True))
            self.assertIsNone(result.records)
            self.assertIn("1", result.umu_paths)
            self.assertIn("1", result.asset_dirs)


if __name__ == "__main__":
    unittest.main()
