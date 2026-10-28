import subprocess
import tempfile
import unittest
from pathlib import Path

from support import make_config, make_image, write

from hydra_fix.icons import (
    collect_frames,
    extract_icon,
    icon_is_current,
    icon_sources,
    probe_icon,
    validate_icon,
)
from hydra_fix.log import Logger


def image(path: Path, size: int, color: str) -> None:
    make_image(path, size, color)


class IconTests(unittest.TestCase):
    def test_extract_largest_source_as_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            image(assets / "small.png", 16, "red")
            image(assets / "large.png", 64, "blue")

            result = extract_icon(config, "42", assets, Logger(quiet=True))

            self.assertIsNotNone(result)
            self.assertTrue(result.changed)
            output = config.icon_dir / "steam_icon_42.png"
            self.assertEqual(result.path, output)
            self.assertTrue(validate_icon(config, output))
            self.assertEqual(probe_icon(config, output)[0], "PNG")
            color = subprocess.run(
                ["convert", str(output), "-format", "%[pixel:p{128,128}]", "info:"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("0,0,255", color)

    def test_square_icon_is_preferred_over_larger_hero_art(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            make_image(assets / "hero.jpg", 400, "red", height=120)
            make_image(assets / "icon.png", 64, "blue")

            frames = collect_frames(config, assets, Logger(quiet=True))
            self.assertEqual(frames[0].source.name, "icon.png")

            result = extract_icon(config, "42", assets, Logger(quiet=True))
            self.assertIsNotNone(result)
            self.assertEqual(result.source.name, "icon.png")
            self.assertTrue(validate_icon(config, result.path))

    def test_missing_icon_frames_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            write(assets / "icon.png", "this is not an image")
            result = extract_icon(config, "42", assets, Logger(quiet=True))
            self.assertIsNone(result)
            self.assertFalse((config.icon_dir / "steam_icon_42.png").exists())

    def test_corrupt_file_is_skipped_for_a_valid_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            write(assets / "icon.ico", "broken")
            image(assets / "icon.png", 32, "green")

            result = extract_icon(config, "42", assets, Logger(quiet=True))

            self.assertIsNotNone(result)
            self.assertTrue(validate_icon(config, result.path))

    def test_existing_icon_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            image(assets / "icon.png", 32, "blue")

            first = extract_icon(config, "42", assets, Logger(quiet=True))
            second = extract_icon(config, "42", assets, Logger(quiet=True))

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertTrue(validate_icon(config, second.path))

    def test_force_regenerates_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            image(assets / "icon.png", 32, "blue")

            extract_icon(config, "42", assets, Logger(quiet=True))
            forced = extract_icon(config, "42", assets, Logger(quiet=True), force=True)

            self.assertTrue(forced.changed)

    def test_icon_is_current_rejects_wrong_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            output = config.icon_dir / "steam_icon_42.png"
            write(output, "not a png")
            self.assertFalse(icon_is_current(config, output, []))
            self.assertFalse(validate_icon(config, output))

    def test_missing_assets_and_frames_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            missing = root / "missing"
            self.assertEqual(icon_sources(missing), [])
            self.assertEqual(collect_frames(config, missing, Logger(quiet=True)), [])

    def test_missing_output_returns_none_without_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            assets = root / "Assets" / "steam-42"
            assets.mkdir(parents=True)
            result = extract_icon(config, "42", assets, Logger(quiet=True))
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
