import tempfile
import unittest
from pathlib import Path

from support import make_config, write

from hydra_fix.cleanup import (
    cleanup_directory,
    purge_reason,
    remove_duplicate_shortcuts,
)
from hydra_fix.log import Logger
from hydra_fix.models import Discovery, GameRecord


def hydra_entry(appid: str, name: str = "Game", extra: str = "") -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f'Exec="/opt/Hydra/hydralauncher" "hydralauncher://run?shop=steam&objectId={appid}"\n'
        f"Icon=steam_icon_{appid}\n"
        "Terminal=false\n"
        f"StartupWMClass=steam_app_{appid}\n"
        f"{extra}"
    )


class CleanupTests(unittest.TestCase):
    def test_purges_hidden_deleted_and_installed_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            installed_exe = root / "game.exe"
            installed_exe.touch()
            hidden = write(config.applications_dir / "Hidden.desktop", hydra_entry("1", extra="Hidden=true\n"))
            deleted = write(config.applications_dir / "Deleted.desktop", hydra_entry("2"))
            kept = write(config.applications_dir / "Kept.desktop", hydra_entry("3"))
            unknown = write(config.applications_dir / "Unknown.desktop", hydra_entry("4"))
            discovery = Discovery(
                records={
                    "1": GameRecord("1"),
                    "2": GameRecord("2", is_deleted=True),
                    "3": GameRecord("3", executable_path=installed_exe),
                },
                db_error=None,
                umu_paths={},
                umu_names={},
                asset_dirs={},
            )

            result = cleanup_directory(
                config.applications_dir,
                {"3": installed_exe},
                discovery,
                config,
                Logger(quiet=True),
                repair=False,
            )

            names = {path.name for path in result.purged}
            self.assertEqual(names, {"Hidden.desktop", "Deleted.desktop"})
            self.assertFalse(hidden.exists())
            self.assertFalse(deleted.exists())
            self.assertTrue(kept.exists())
            self.assertTrue(unknown.exists())

    def test_purges_log_fallback_when_executable_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            entry = write(config.applications_dir / "Gone.desktop", hydra_entry("1"))
            discovery = Discovery(
                records=None,
                db_error="unavailable",
                umu_paths={"1": (root / "missing.exe",)},
                umu_names={},
                asset_dirs={},
            )
            reason = purge_reason(
                __import__("hydra_fix.desktop", fromlist=["parse_desktop"]).parse_desktop(entry),
                {},
                discovery,
            )
            self.assertEqual(reason, "game executable is missing")

    def test_unknown_entry_is_kept_without_database_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            entry_path = write(config.applications_dir / "Custom.desktop", hydra_entry("1"))
            from hydra_fix.desktop import parse_desktop

            entry = parse_desktop(entry_path)
            discovery = Discovery(None, "unavailable", {}, {}, {})
            self.assertIsNone(purge_reason(entry, {}, discovery))

    def test_only_mode_disables_pruning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            path = write(config.applications_dir / "Hidden.desktop", hydra_entry("1", extra="Hidden=true\n"))
            discovery = Discovery({}, None, {}, {}, {})
            result = cleanup_directory(
                config.applications_dir,
                {},
                discovery,
                config,
                Logger(quiet=True),
                only=("1",),
                repair=False,
            )
            self.assertEqual(result.purged, [])
            self.assertTrue(path.exists())

    def test_remove_duplicate_shortcuts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            primary = write(config.applications_dir / "Primary.desktop", hydra_entry("1"))
            duplicate = write(config.applications_dir / "Duplicate.desktop", hydra_entry("1"))
            unrelated = write(
                config.applications_dir / "Other.desktop",
                "[Desktop Entry]\nType=Application\nName=Other\nExec=/bin/true\n",
            )
            removed = remove_duplicate_shortcuts(
                config.applications_dir,
                {"1": primary},
                Logger(quiet=True),
            )
            self.assertEqual(removed, [duplicate])
            self.assertFalse(duplicate.exists())
            self.assertTrue(primary.exists())
            self.assertTrue(unrelated.exists())

    def test_dry_run_does_not_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            path = write(config.applications_dir / "Hidden.desktop", hydra_entry("1", extra="Hidden=true\n"))
            discovery = Discovery({}, None, {}, {}, {})
            result = cleanup_directory(
                config.applications_dir,
                {},
                discovery,
                config,
                Logger(quiet=True),
                repair=False,
                dry_run=True,
            )
            self.assertEqual(len(result.purged), 1)
            self.assertTrue(path.exists())

    def test_repairs_desktop_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.desktop_dir.mkdir(parents=True)
            path = write(
                config.desktop_dir / "Game.desktop",
                "#!/user/bin/env xdg-open\n" + hydra_entry("1").replace("StartupWMClass=steam_app_1\n", ""),
            )
            exe = root / "game.exe"
            exe.touch()
            discovery = Discovery(
                records={"1": GameRecord("1", executable_path=exe)},
                db_error=None,
                umu_paths={},
                umu_names={},
                asset_dirs={},
            )
            result = cleanup_directory(
                config.desktop_dir,
                {"1": exe},
                discovery,
                config,
                Logger(quiet=True),
                repair=True,
            )
            self.assertEqual(result.repaired, [path])
            text = path.read_text()
            self.assertIn("#!/usr/bin/env xdg-open", text)
            self.assertIn("StartupWMClass=steam_app_1", text)


if __name__ == "__main__":
    unittest.main()
