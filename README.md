# hydra-launcher-icon-fix

Fixes missing/broken taskbar and app-menu icons for games installed through
[Hydra Launcher](https://github.com/hydralauncher/hydra).

## The problem

Hydra caches a game's icon as a `.ico`/`.png` under
`~/.config/hydralauncher/Assets/steam-<appid>/`, but the `.desktop` shortcuts
it generates reference an icon name like `steam_icon_<appid>` that is never
installed into the icon theme. It also marks its application-menu entries
`Hidden=true` and sets a `StartupWMClass` that does not match the real window
class of the game (which, for umu/Proton launches, is `steam_app_<appid>`).

The result: games show a generic/blank icon in the GNOME/Zorin taskbar instead
of their real artwork.

## What it does

`hydra-fix` (Python 3):

- Extracts the largest frame of each cached `.ico`/`.png` into
  `~/.local/share/icons/hicolor/256x256/apps/steam_icon_<appid>.png`.
- Creates a visible `~/.local/share/applications/<Game>.desktop` for every
  installed game with `Icon=steam_icon_<appid>` and
  `StartupWMClass=steam_app_<appid>`.
- Repairs Hydra's Desktop shortcuts (fixes the `#!/user/...` shebang typo,
  replaces `.ico` path icons, adds the correct `StartupWMClass`).
- Removes stale `Hidden=true` entries and entries whose game executable no
  longer exists on disk.

`hydra-watch` (bash + inotifywait): watches Hydra's Assets folder, Desktop, and
launch log, and re-runs `hydra-fix` whenever a game is downloaded/launched, so
new games get the same treatment automatically.

## Requirements

- Python 3
- ImageMagick (`convert`, `identify`)
- inotify-tools (`inotifywait`)
- A systemd user session (for the watcher)

## Install

```sh
./install.sh
```

or manually:

```sh
install -m 0755 hydra-fix  ~/.local/bin/hydra-fix
install -m 0755 hydra-watch ~/.local/bin/hydra-watch
mkdir -p ~/.config/systemd/user
install -m 0644 hydra-watch.service ~/.config/systemd/user/hydra-watch.service
systemctl --user daemon-reload
systemctl --user enable --now hydra-watch.service
```

## Notes

- Game display names are curated in `KNOWN_NAMES` inside `hydra-fix`; names not
  listed there are derived from the launched executable. Add entries there for
  your own games, or set `HYDRA_BIN` if Hydra is installed somewhere other than
  `/opt/Hydra/hydralauncher`.
- The watcher runs once at startup and on every relevant filesystem event.
