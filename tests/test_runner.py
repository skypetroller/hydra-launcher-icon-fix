import tempfile
import unittest
from pathlib import Path

from support import make_config, make_dirs, make_image, write

from hydra_fix.config import Config
from hydra_fix.desktop import parse_desktop
from hydra_fix.errors import FatalError
from hydra_fix.log import Logger
from hydra_fix.models import RunMode, RunOptions
from hydra_fix.runner import run


def add_game(
    config: Config,
    root: Path,
    appid: str,
    name: str,
    *,
    icon: bool = True,
) -> Path:
    executable = root / "games" / f"{name}.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.touch()
    assets = config.assets_dir / f"steam-{appid}"
    assets.mkdir(parents=True, exist_ok=True)
    if icon:
        make_image(assets / "icon.png", 64, "blue")
    with config.umu_log.open("a", encoding="utf-8") as log:
        log.write(
            f"Command: GAMEID='umu-{appid}' wine '{executable}'\n"
        )
    return executable


class RunnerTests(unittest.TestCase):
    def test_dry_run_reports_without_touching_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game")
            summary = run(
                config,
                RunOptions(dry_run=True, update_caches=False),
                Logger(quiet=True),
            )
            self.assertTrue(summary.changed)
            self.assertEqual(summary.games, 1)
            self.assertFalse(config.icon_dir.exists())
            self.assertEqual(list(config.applications_dir.glob("*.desktop")), [])

    def test_full_run_creates_icon_and_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game")
            summary = run(
                config,
                RunOptions(update_caches=False),
                Logger(quiet=True),
            )
            self.assertEqual(summary.games, 1)
            self.assertEqual(summary.icons_written, 1)
            self.assertEqual(summary.desktops_written, 1)
            icon = config.icon_dir / "steam_icon_42.png"
            shortcut = config.applications_dir / "My Game.desktop"
            self.assertTrue(icon.is_file())
            self.assertTrue(shortcut.is_file())
            entry = parse_desktop(shortcut)
            self.assertEqual(entry.appid, "42")
            self.assertEqual(entry.name, "My Game")
            self.assertEqual(entry.icon, "steam_icon_42")

    def test_missing_assets_directory_is_a_clear_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            with self.assertRaises(FatalError):
                run(config, RunOptions(update_caches=False), Logger(quiet=True))

    def test_icons_only_does_not_create_shortcuts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game")
            summary = run(
                config,
                RunOptions(mode=RunMode.ICONS_ONLY, update_caches=False),
                Logger(quiet=True),
            )
            self.assertEqual(summary.icons_written, 1)
            self.assertEqual(list(config.applications_dir.glob("*.desktop")), [])

    def test_desktop_only_does_not_extract_icons(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game")
            summary = run(
                config,
                RunOptions(mode=RunMode.DESKTOP_ONLY, update_caches=False),
                Logger(quiet=True),
            )
            self.assertEqual(summary.desktops_written, 1)
            self.assertFalse(config.icon_dir.exists())
            self.assertTrue((config.applications_dir / "My Game.desktop").is_file())

    def test_only_limits_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "First Game")
            add_game(config, root, "99", "Second Game")
            run(
                config,
                RunOptions(only=("42",), update_caches=False),
                Logger(quiet=True),
            )
            names = {path.name for path in config.applications_dir.glob("*.desktop")}
            self.assertEqual(names, {"First Game.desktop"})

    def test_hidden_stale_entry_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game")
            stale = write(
                config.applications_dir / "Old Game.desktop",
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Old Game\n"
                'Exec="/opt/Hydra/hydralauncher" "hydralauncher://run?shop=steam&objectId=7"\n'
                "Icon=steam_icon_7\n"
                "Hidden=true\n",
            )
            summary = run(
                config,
                RunOptions(update_caches=False),
                Logger(quiet=True),
            )
            self.assertFalse(stale.exists())
            self.assertGreaterEqual(summary.purged, 1)

    def test_missing_icon_still_writes_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game", icon=False)
            summary = run(
                config,
                RunOptions(update_caches=False),
                Logger(quiet=True),
            )
            self.assertEqual(summary.icon_errors, 1)
            self.assertEqual(summary.desktops_written, 1)
            self.assertTrue((config.applications_dir / "My Game.desktop").is_file())

    def test_unrelated_desktop_entry_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            add_game(config, root, "42", "My Game")
            unrelated = write(
                config.applications_dir / "My Game.desktop",
                "[Desktop Entry]\nType=Application\nName=My Game\nExec=/bin/true\n",
            )
            run(
                config,
                RunOptions(update_caches=False),
                Logger(quiet=True),
            )
            self.assertEqual(
                unrelated.read_text(),
                "[Desktop Entry]\nType=Application\nName=My Game\nExec=/bin/true\n",
            )
            self.assertTrue((config.applications_dir / "hydra-42.desktop").is_file())

    def test_managed_entry_without_assets_is_still_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            make_dirs(config)
            executable = add_game(config, root, "42", "My Game", icon=False)
            shortcut = write(
                config.applications_dir / "My Game.desktop",
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=My Game\n"
                'Exec="/opt/Hydra/hydralauncher" "hydralauncher://run?shop=steam&objectId=42"\n'
                "Icon=steam_icon_42\n",
            )
            summary = run(
                config,
                RunOptions(update_caches=False),
                Logger(quiet=True),
            )
            self.assertEqual(summary.games, 1)
            entry = parse_desktop(shortcut)
            self.assertEqual(entry.startup_wm_class, "steam_app_42")
            self.assertTrue(executable.exists())


if __name__ == "__main__":
    unittest.main()
