import importlib.machinery
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("hydra_fix", str(ROOT / "hydra-fix"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
hydra_fix = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(hydra_fix)


class HydraFixTests(unittest.TestCase):
    def test_db_records_are_used_for_install_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "installed.exe"
            installed.touch()

            result = hydra_fix.detect_installed_games(
                {"log-only": [installed]},
                {
                    "installed": {
                        "isDeleted": False,
                        "executablePath": str(installed),
                    },
                    "deleted": {
                        "isDeleted": True,
                        "executablePath": str(installed),
                    },
                },
            )

            self.assertEqual(set(result), {"installed", "log-only"})

    def test_log_detection_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "installed.exe"
            missing = Path(directory) / "missing.exe"
            installed.touch()

            result = hydra_fix.detect_installed_games(
                {"installed": [installed], "missing": [missing]},
            )

            self.assertEqual(set(result), {"installed"})

    def test_icon_extraction_chooses_largest_source(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory) / "assets"
            output = Path(directory) / "icons"
            assets.mkdir()
            output.mkdir()
            subprocess.run(
                ["convert", "-size", "16x16", "xc:red", str(assets / "icon-small.png")],
                check=True,
            )
            subprocess.run(
                ["convert", "-size", "64x64", "xc:blue", str(assets / "icon-large.png")],
                check=True,
            )

            original_icon_dir = hydra_fix.ICON_DIR
            hydra_fix.ICON_DIR = output
            try:
                result = hydra_fix.extract_icon("42", assets)
            finally:
                hydra_fix.ICON_DIR = original_icon_dir

            self.assertIsNotNone(result)
            self.assertEqual(result, output / "steam_icon_42.png")
            dimensions = subprocess.run(
                ["identify", "-format", "%wx%h", str(result)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(dimensions.stdout, "256x256")
            image_format = subprocess.run(
                ["identify", "-format", "%m", str(result)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(image_format.stdout, "PNG")
            color = subprocess.run(
                [
                    "convert",
                    str(result),
                    "-format",
                    "%[pixel:p{128,128}]",
                    "info:",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("0,0,255", color.stdout)


if __name__ == "__main__":
    unittest.main()
