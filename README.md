# hydra-launcher-icon-fix

Fixes missing/broken taskbar and app-menu icons for games installed through
[Hydra Launcher](https://github.com/hydralauncher/hydra) for Linux.

## The problem

Hydra caches a game's icon as a `.ico`/`.png` under
`~/.config/hydralauncher/Assets/steam-<appid>/`, but the `.desktop` shortcuts
it generates reference an icon name like `steam_icon_<appid>` that is never
installed into the icon theme. It also marks its application-menu entries
`Hidden=true` and sets a `StartupWMClass` that does not match the real window
class of the game (which, for umu/Proton launches, is `steam_app_<appid>`).

The result: games show a generic/blank icon in the GNOME taskbar instead
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
- Reads Hydra's current game records from a temporary copy of its LevelDB
  database when Hydra's bundled Electron runtime is available. This lets the
  fixer recognize a newly downloaded game before its first launch. It falls
  back to Hydra's `umu.log` when the database cannot be read.

`hydra-watch` (bash + inotifywait): watches Hydra's Assets folder, Desktop,
launch log, and database, and re-runs `hydra-fix` when a game is downloaded,
launched, or its shortcut/icon changes. Old icon-cache folders alone are not
treated as installed games.

## Requirements

- Python 3
- ImageMagick (`convert`, `identify`)
- inotify-tools (`inotifywait`)
- `flock` (usually provided by util-linux)
- A systemd user session (for the watcher)

The fixer uses Hydra's bundled Electron/LevelDB modules when available; this is
optional and does not add a separate runtime dependency.

Install dependencies on Debian/Ubuntu:

```sh
sudo apt install -y imagemagick inotify-tools
```

## Install

Run the installer as your normal desktop user, not with `sudo`. It installs a
systemd **user** service and writes only to your home directory.

```sh
git clone https://github.com/skypetroller/hydra-launcher-icon-fix.git
cd hydra-launcher-icon-fix
./install.sh
```

The installer copies `hydra-fix` and `hydra-watch` into `~/.local/bin`, installs
`hydra-watch.service` as a systemd **user** unit, and enables + starts it.

Hydra should have been started at least once before installation so its
`Assets`, database, and log directories exist. If they do not exist yet, start
Hydra, then run `./install.sh` again.

Or install manually:

```sh
mkdir -p ~/.local/bin ~/.config/systemd/user
install -m 0755 hydra-fix  ~/.local/bin/hydra-fix
install -m 0755 hydra-watch ~/.local/bin/hydra-watch
install -m 0644 hydra-watch.service ~/.config/systemd/user/hydra-watch.service
systemctl --user daemon-reload
systemctl --user enable hydra-watch.service
systemctl --user restart hydra-watch.service
```

Make sure `~/.local/bin` is on your `PATH` (most distros add it automatically if
the directory exists). If not, add `export PATH="$HOME/.local/bin:$PATH"` to your
`~/.profile`.

Check the watcher with:

```sh
systemctl --user status hydra-watch.service
journalctl --user -u hydra-watch.service -f
```

If Hydra is installed somewhere other than `/opt/Hydra/hydralauncher`, set the
binary path for the user service:

```sh
systemctl --user edit hydra-watch.service
```

Add:

```ini
[Service]
Environment=HYDRA_BIN=/path/to/hydralauncher
```

Then restart the service:

```sh
systemctl --user restart hydra-watch.service
```

## Update

Pull the latest version and reinstall it. The installer explicitly restarts an
already-running service, so updated scripts are loaded immediately:

```sh
cd hydra-launcher-icon-fix
git pull --ff-only
./install.sh
```

## Troubleshooting

Run the fixer manually:

```sh
~/.local/bin/hydra-fix
```

Inspect the service and its recent log:

```sh
systemctl --user status hydra-watch.service
journalctl --user -u hydra-watch.service -n 50 --no-pager
```

If the service says its condition failed, make sure Hydra's
`~/.config/hydralauncher/Assets` directory exists, then restart the service.

## Uninstall

```sh
systemctl --user disable --now hydra-watch.service
rm -f ~/.config/systemd/user/hydra-watch.service
rm -f ~/.local/bin/hydra-fix ~/.local/bin/hydra-watch
systemctl --user daemon-reload
```

The generated game shortcuts and cached icons are left in place by uninstall so
the command does not remove user-created launchers. Remove unwanted entries
from `~/.local/share/applications` and `~/.local/share/icons/hicolor` manually.

## Test

Run the local tests with:

```sh
python3 -m unittest discover -s tests -v
```

## Notes

- Game display names are curated in `KNOWN_NAMES` inside `hydra-fix`; names not
  listed there come from Hydra's database or launched executable. Add entries
  there for your own games, or set `HYDRA_BIN` if Hydra is installed somewhere
  other than `/opt/Hydra/hydralauncher`.
- The watcher runs once at startup and on every relevant filesystem event. Run
  `~/.local/bin/hydra-fix` manually after moving a game to a new location before
  launching it again.
