import tempfile
import unittest
from pathlib import Path

from support import make_config, write

from hydra_fix.desktop import (
    choose_target,
    parse_desktop,
    render_desktop,
    repair_hydra_desktop,
    validate_text,
    write_generated_desktop,
)
from hydra_fix.log import Logger
from hydra_fix.models import Game
from hydra_fix.text import desktop_value, safe_filename


def game(appid="123", name="Test Game") -> Game:
    return Game(
        appid=appid,
        name=name,
        executable_path=Path("/tmp/game.exe"),
        asset_dir=Path("/tmp/assets"),
    )


def hydra_desktop(appid="123", name="Test Game", extra="") -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f'Exec="/opt/Hydra/hydralauncher" "hydralauncher://run?shop=steam&objectId={appid}"\n'
        f"Icon=steam_icon_{appid}\n"
        "Terminal=false\n"
        f"{extra}"
    )


class DesktopTests(unittest.TestCase):
    def test_render_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            text = render_desktop(config, game())
            self.assertEqual(validate_text(text), [])
            path = write(root / "entry.desktop", text)
            entry = parse_desktop(path)
            self.assertIsNotNone(entry)
            self.assertTrue(entry.managed)
            self.assertEqual(entry.appid, "123")
            self.assertEqual(entry.name, "Test Game")
            self.assertEqual(entry.startup_wm_class, "steam_app_123")
            self.assertIn("X-Hydra-Fix=true", text)

    def test_choose_target_avoids_unrelated_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            write(
                config.applications_dir / "Test Game.desktop",
                "[Desktop Entry]\nType=Application\nName=Other\nExec=/bin/true\n",
            )
            target = choose_target(config, game(), Logger(quiet=True))
            self.assertEqual(target.name, "hydra-123.desktop")

    def test_choose_target_reuses_matching_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            config.applications_dir.mkdir(parents=True)
            expected = write(
                config.applications_dir / "Test Game.desktop",
                hydra_desktop(),
            )
            target = choose_target(config, game(), Logger(quiet=True))
            self.assertEqual(target, expected)

    def test_write_refuses_unrelated_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            target = write(
                root / "data" / "applications" / "Test Game.desktop",
                "[Desktop Entry]\nType=Application\nName=Other\nExec=/bin/true\n",
            )
            with self.assertRaises(OSError):
                write_generated_desktop(
                    config, game(), target, dry_run=False, logger=Logger(quiet=True)
                )

    def test_repairs_broken_shebang_icon_and_missing_wmclass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            path = write(
                root / "Desktop" / "Test Game.desktop",
                "#!/user/bin/env xdg-open\n"
                + hydra_desktop(extra="Icon=/home/user/icon.ico\n"),
            )
            entry = parse_desktop(path)
            changed = repair_hydra_desktop(
                entry, "123", config, dry_run=False, logger=Logger(quiet=True)
            )
            self.assertTrue(changed)
            text = path.read_text()
            self.assertIn("#!/usr/bin/env xdg-open", text)
            self.assertEqual(text.count("Icon=steam_icon_123"), 1)
            self.assertIn("StartupWMClass=steam_app_123", text)

    def test_repair_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            original = "#!/user/bin/env xdg-open\n" + hydra_desktop()
            path = write(root / "Desktop" / "Test Game.desktop", original)
            entry = parse_desktop(path)
            changed = repair_hydra_desktop(
                entry, "123", config, dry_run=True, logger=Logger(quiet=True)
            )
            self.assertTrue(changed)
            self.assertEqual(path.read_text(), original)

    def test_validate_rejects_hidden_and_missing_fields(self):
        text = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Test\n"
            "Hidden=true\n"
        )
        errors = validate_text(text)
        self.assertTrue(any("Hidden" in error for error in errors))
        self.assertTrue(any("Exec" in error for error in errors))
        self.assertTrue(any("Icon" in error for error in errors))
        self.assertTrue(any("StartupWMClass" in error for error in errors))

    def test_malformed_desktop_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(Path(directory) / "bad.desktop", "not a desktop file")
            self.assertIsNone(parse_desktop(path, Logger(quiet=True)))

    def test_text_helpers_prevent_path_traversal(self):
        self.assertEqual(safe_filename("../evil/game"), "evil-game")
        self.assertNotIn("/", safe_filename("a/b"))
        self.assertEqual(desktop_value("line one\nline two"), "line one line two")


if __name__ == "__main__":
    unittest.main()
