"""Central configuration: paths, commands, and curated game names.

All locations can be redirected with environment variables or command-line
options. Nothing in this module touches the filesystem except for inexpensive
lookups such as ``shutil.which`` and ``xdg-user-dir``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple


# Friendly names for games whose executable names are unhelpful. Users can add
# their own entries here; unknown games fall back to Hydra's database title,
# an existing shortcut name, or the launched executable name.
KNOWN_NAMES: Mapping[str, str] = {
    "1030300": "Hollow Knight Silksong",
    "1313140": "Cult of the Lamb",
    "1623730": "Palworld",
    "1794680": "Vampire Survivors",
    "2005010": "Warhammer 40000 Boltgun",
    "2138710": "Sifu",
    "239820": "Game Dev Tycoon",
    "250900": "The Binding of Isaac: Rebirth",
    "2651280": "Marvel's Spider-Man 2",
    "2868840": "Slay the Spire 2",
    "3164500": "Schedule I",
    "3405340": "Megabonk",
    "413150": "Stardew Valley",
    "632360": "Risk of Rain 2",
}

DEFAULT_HYDRA_BIN = Path("/opt/Hydra/hydralauncher")


def _path(value: Optional[str], base: Path) -> Optional[Path]:
    if value is None or not str(value).strip():
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def _desktop_dir(home: Path, env: Mapping[str, str]) -> Path:
    override = _path(env.get("HYDRA_DESKTOP_DIR"), home)
    if override is not None:
        return override
    # Only consult the user-dirs database when we're operating on the real
    # home directory. A custom home (tests, alternate accounts) should not
    # silently produce the current user's Desktop path.
    if home == Path.home() and shutil.which("xdg-user-dir"):
        try:
            result = subprocess.run(
                ["xdg-user-dir", "DESKTOP"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            candidate = result.stdout.strip()
            if result.returncode == 0 and candidate:
                return Path(candidate)
        except (OSError, subprocess.SubprocessError):
            pass
    return home / "Desktop"


def _find_hydra_binary(
    env: Mapping[str, str], home: Path, explicit: Optional[str]
) -> Optional[Path]:
    for value in (explicit, env.get("HYDRA_BIN")):
        if value:
            return _path(value, home)
    candidates = [DEFAULT_HYDRA_BIN]
    found = shutil.which("hydralauncher")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _image_magick() -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    magick = shutil.which("magick")
    if magick:
        return (magick, "identify"), (magick,)
    identify = shutil.which("identify")
    convert = shutil.which("convert")
    return ((identify,) if identify else ()), ((convert,) if convert else ())


@dataclass(frozen=True)
class Config:
    """Resolved paths and external commands used by one run."""

    home: Path
    hydra_config_dir: Path
    assets_dir: Path
    db_path: Path
    umu_log: Path
    hydra_bin: Optional[Path]
    icon_dir: Path
    icon_theme_dir: Path
    applications_dir: Path
    desktop_dir: Path
    identify_cmd: Tuple[str, ...]
    convert_cmd: Tuple[str, ...]
    update_desktop_db_cmd: Optional[str]
    gtk_update_icon_cache_cmd: Optional[str]
    known_names: Mapping[str, str] = field(default_factory=lambda: KNOWN_NAMES)
    wm_class_overrides: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(
        cls,
        *,
        env: Optional[Mapping[str, str]] = None,
        home: Optional[str] = None,
        hydra_bin: Optional[str] = None,
        config_dir: Optional[str] = None,
        assets_dir: Optional[str] = None,
        desktop_dir: Optional[str] = None,
    ) -> "Config":
        environment = dict(os.environ if env is None else env)
        home_path = _path(home, Path.cwd()) if home else _path(
            environment.get("HOME"), Path.cwd()
        )
        if home_path is None:
            home_path = Path.home()

        xdg_config = _path(environment.get("XDG_CONFIG_HOME"), home_path)
        if xdg_config is None:
            xdg_config = home_path / ".config"
        hydra_config = _path(config_dir or environment.get("HYDRA_CONFIG_DIR"), home_path)
        if hydra_config is None:
            hydra_config = xdg_config / "hydralauncher"

        xdg_data = _path(environment.get("XDG_DATA_HOME"), home_path)
        if xdg_data is None:
            xdg_data = home_path / ".local" / "share"

        assets = _path(assets_dir or environment.get("HYDRA_ASSETS_DIR"), home_path)
        if assets is None:
            assets = hydra_config / "Assets"

        db_path = _path(environment.get("HYDRA_DB_PATH"), home_path)
        if db_path is None:
            db_path = hydra_config / "hydra-db"

        umu_log = _path(environment.get("HYDRA_UMU_LOG"), home_path)
        if umu_log is None:
            umu_log = hydra_config / "logs" / "umu.log"

        icons = _path(environment.get("HYDRA_ICON_DIR"), home_path)
        if icons is None:
            icons = xdg_data / "icons" / "hicolor" / "256x256" / "apps"

        applications = _path(environment.get("HYDRA_APPLICATIONS_DIR"), home_path)
        if applications is None:
            applications = xdg_data / "applications"

        desktop = _path(desktop_dir, home_path) or _desktop_dir(home_path, environment)

        identify_cmd, convert_cmd = _image_magick()

        return cls(
            home=home_path,
            hydra_config_dir=hydra_config,
            assets_dir=assets,
            db_path=db_path,
            umu_log=umu_log,
            hydra_bin=_find_hydra_binary(environment, home_path, hydra_bin),
            icon_dir=icons,
            icon_theme_dir=icons.parent.parent,
            applications_dir=applications,
            desktop_dir=desktop,
            identify_cmd=identify_cmd,
            convert_cmd=convert_cmd,
            update_desktop_db_cmd=shutil.which("update-desktop-database"),
            gtk_update_icon_cache_cmd=shutil.which("gtk-update-icon-cache"),
        )

    def startup_wm_class(self, appid: str) -> str:
        """The X11/Wayland window class used by umu/Proton games."""
        return self.wm_class_overrides.get(appid, f"steam_app_{appid}")

    def command_summary(self) -> Sequence[Tuple[str, bool]]:
        """Return (component, available) pairs for diagnostics."""
        return (
            ("ImageMagick identify", bool(self.identify_cmd)),
            ("ImageMagick convert", bool(self.convert_cmd)),
            ("update-desktop-database", bool(self.update_desktop_db_cmd)),
            ("gtk-update-icon-cache", bool(self.gtk_update_icon_cache_cmd)),
            ("Hydra launcher", bool(self.hydra_bin)),
        )
