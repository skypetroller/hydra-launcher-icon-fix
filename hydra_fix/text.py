"""Text normalization helpers shared by discovery and desktop generation."""
from __future__ import annotations

import re
import unicodedata


def title_case(name: str) -> str:
    """Turn a launched executable name into a readable game title."""
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = name.replace(" - Shipping", "").replace("-Win64", "").replace("WinGDK", "")
    name = re.sub(r"\s+-\s+(SteamGG\.NET|SteamRIP\.com|Gamdie\.com).*$", "", name)
    name = name.replace("_", " ")
    return re.sub(r"\s+", " ", name).strip()


def desktop_value(value: str) -> str:
    """Make a string safe for a single .desktop key=value line."""
    value = unicodedata.normalize("NFC", value)
    value = value.replace("\r", " ").replace("\n", " ").replace("\x00", "")
    return re.sub(r"\s+", " ", value).strip()


def safe_filename(name: str, *, max_length: int = 120) -> str:
    """Return a filename component that cannot escape the applications dir."""
    name = desktop_value(name)
    name = name.replace("/", "-").replace("\\", "-")
    name = re.sub(r"[\x00-\x1f\x7f]", "-", name)
    name = name.strip(" .-")
    name = re.sub(r"-{2,}", "-", name)
    if not name or name in {".", ".."}:
        name = "Hydra Game"
    if len(name) > max_length:
        name = name[:max_length].rstrip(" .-") or "Hydra Game"
    return name
