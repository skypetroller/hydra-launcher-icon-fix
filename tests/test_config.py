import os
import tempfile
import unittest
from pathlib import Path

from support import executable, make_config


class ConfigTests(unittest.TestCase):
    def test_xdg_defaults_are_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = executable(root / "bin" / "hydralauncher")
            config = make_config(root, hydra_bin=binary)
            self.assertEqual(config.hydra_config_dir, root / "config" / "hydralauncher")
            self.assertEqual(config.assets_dir, root / "config" / "hydralauncher" / "Assets")
            self.assertEqual(config.icon_dir, root / "data" / "icons" / "hicolor" / "256x256" / "apps")
            self.assertEqual(config.applications_dir, root / "data" / "applications")
            self.assertEqual(config.desktop_dir, root / "Desktop")
            self.assertEqual(config.hydra_bin, binary)

    def test_custom_hydra_config_and_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(
                root,
                env={
                    "HYDRA_CONFIG_DIR": str(root / "custom-hydra"),
                    "HYDRA_ASSETS_DIR": str(root / "custom-assets"),
                },
            )
            self.assertEqual(config.hydra_config_dir, root / "custom-hydra")
            self.assertEqual(config.assets_dir, root / "custom-assets")
            self.assertEqual(config.db_path, root / "custom-hydra" / "hydra-db")
            self.assertEqual(config.umu_log, root / "custom-hydra" / "logs" / "umu.log")

    def test_home_and_custom_desktop_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(
                root,
                env={"HYDRA_DESKTOP_DIR": str(root / "My Desktop")},
            )
            self.assertEqual(config.home, root)
            self.assertEqual(config.desktop_dir, root / "My Desktop")

    def test_wm_class_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            self.assertEqual(config.startup_wm_class("42"), "steam_app_42")

    def test_environment_does_not_leak_into_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = os.environ.get("HYDRA_DESKTOP_DIR")
            os.environ["HYDRA_DESKTOP_DIR"] = str(root / "wrong")
            try:
                config = make_config(root, env={"HYDRA_DESKTOP_DIR": str(root / "right")})
            finally:
                if original is None:
                    os.environ.pop("HYDRA_DESKTOP_DIR", None)
                else:
                    os.environ["HYDRA_DESKTOP_DIR"] = original
            self.assertEqual(config.desktop_dir, root / "right")


if __name__ == "__main__":
    unittest.main()
