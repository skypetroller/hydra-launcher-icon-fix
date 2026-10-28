# hydra-launcher-icon-fix

Fix missing, blank, or generic taskbar icons for games installed through
[Hydra Launcher](https://github.com/hydralauncher/hydra) on Linux.

Tested on **Zorin OS 18 (GNOME)**. It should work on any Linux desktop that uses
the freedesktop icon theme and `.desktop` shortcuts, including GNOME, KDE
Plasma, Cinnamon, Xfce, and MATE.

---

## The problem

Hydra caches game artwork under
`~/.config/hydralauncher/Assets/steam-<appid>/`, but the shortcuts it creates
have two issues:

1. They reference an icon named `steam_icon_<appid>` that is never installed
   into the icon theme.
2. They set `StartupWMClass` to a value that does not match the real window
   class of a umu/Proton game, which is usually `steam_app_<appid>`.

Some Hydra shortcuts are also marked `Hidden=true`, point at a `.ico` file
directly, or contain the `#!/user/bin/env` shebang typo. The result is a
generic/blank icon in the GNOME/KDE taskbar and sometimes a shortcut that does
nothing.

## What it does

`hydra-fix`:

- Finds installed Hydra games from a **temporary snapshot** of Hydra's LevelDB
  database, falling back to `logs/umu.log` when the database cannot be read.
- Extracts the largest usable frame from Hydra's cached `.ico`, `.png`,
  `.webp`, `.jpg`, or `.gif` artwork into
  `~/.local/share/icons/hicolor/256x256/apps/steam_icon_<appid>.png`. Square
  icon artwork is preferred over larger hero banners and library art.
- Creates a visible application-menu shortcut for each game with the correct
  icon name and `StartupWMClass=steam_app_<appid>`.
- Repairs existing Hydra shortcuts on the Desktop and in the application menu:
  broken shebang, `.ico` icon paths, missing/incorrect window class, hidden
  entries, and missing `Type`/`Name` fields.
- Removes stale and duplicate Hydra-managed shortcuts when the game was deleted
  from Hydra or its executable no longer exists.
- Optionally watches Hydra's data directories and re-runs automatically when a
  game is installed, launched, moved, or updated.

### What it deliberately leaves alone

- **Unrelated shortcuts and launchers are never modified.** If a game already
  has a non-Hydra `.desktop` file with the same name, the fixer writes a
  `hydra-<appid>.desktop` file instead of overwriting it.
- Games in Hydra's database that have **no Hydra artwork and no existing
  Hydra-managed shortcut** are skipped. This avoids creating blank entries for
  games that were merely scanned from a Steam library.
- Symlinks are never followed or overwritten.
- Your Ghostty, terminal, browser, or other custom launchers are untouched.

## Requirements

| Component | Required for | Notes |
| --- | --- | --- |
| Python 3.9+ | everything | Preinstalled on most distributions. |
| ImageMagick (`magick` or `convert` + `identify`) | icon extraction | Not needed for `--fix-desktop-only`. |
| `inotifywait` (`inotify-tools`) | watcher service | Not needed for one-shot runs. |
| `flock` (`util-linux`) | watcher service | Usually preinstalled. |
| systemd user session | watcher service | Not needed for one-shot runs. |
| `update-desktop-database` (`desktop-file-utils`) | menu refresh | Recommended. |
| `gtk-update-icon-cache` | icon cache refresh | Recommended. |

Install the dependencies for your distribution:

```sh
# Debian, Ubuntu, Zorin OS, Linux Mint
sudo apt install python3 imagemagick inotify-tools util-linux desktop-file-utils

# Fedora
sudo dnf install python3 ImageMagick inotify-tools util-linux desktop-file-utils

# Arch Linux, Manjaro
sudo pacman -S python imagemagick inotify-tools util-linux desktop-file-utils

# openSUSE
sudo zypper install python3 ImageMagick inotify-tools util-linux desktop-file-utils
```

`gtk-update-icon-cache` is usually provided by the GTK package. If it is
missing, the fixer still writes icons; it only skips the cache refresh.

## Install

Run the installer as your **normal desktop user**, not with `sudo`. It only
writes inside your home directory.

```sh
git clone https://github.com/skypetroller/hydra-launcher-icon-fix.git
cd hydra-launcher-icon-fix
./install.sh
```

The installer:

1. Checks required commands and locates Hydra.
2. Runs a pre-flight check against Hydra's real data directories.
3. Installs the Python package to
   `~/.local/share/hydra-launcher-icon-fix/`.
4. Installs `hydra-fix` and `hydra-watch` into `~/.local/bin/`.
5. Installs, enables, and starts `hydra-watch.service` as a **systemd user**
   service.
6. Persists any custom `HYDRA_BIN`/`HYDRA_CONFIG_DIR` paths in a systemd
   drop-in so the watcher uses the same paths.

If Hydra has never been started, start it once so it creates its `Assets`,
database, and log directories, then run `./install.sh` again.

### Installer options

```sh
./install.sh --dry-run     # show what would be installed
./install.sh --no-service  # install without enabling the watcher
./install.sh --help
```

Make sure `~/.local/bin` is on your `PATH`. Most distributions add it
automatically when the directory exists. If `hydra-fix` is not found:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
```

### Manual installation

If you prefer not to use the installer:

```sh
install -d ~/.local/share/hydra-launcher-icon-fix \
          ~/.local/bin \
          ~/.config/systemd/user

cp -a hydra_fix ~/.local/share/hydra-launcher-icon-fix/
install -m 0755 hydra-fix   ~/.local/bin/hydra-fix
install -m 0755 hydra-watch ~/.local/bin/hydra-watch
install -m 0644 hydra-watch.service ~/.config/systemd/user/hydra-watch.service

systemctl --user daemon-reload
systemctl --user enable --now hydra-watch.service
```

You can also install the Python package with pip, which provides the same
`hydra-fix` command:

```sh
python3 -m pip install --user .
```

## Usage

```sh
hydra-fix                          # fix icons and shortcuts, prune stale entries
hydra-fix --dry-run --verbose      # show exactly what would change
hydra-fix --check                  # diagnose paths and dependencies
hydra-fix --fix-desktop-only       # shortcuts only; ImageMagick not required
hydra-fix --repair-icons-only      # icons only; no shortcut changes
hydra-fix --only 413150            # one game (repeatable; disables pruning)
hydra-fix --force                  # regenerate icons even if they are current
hydra-fix --no-prune               # keep stale/duplicate Hydra shortcuts
hydra-fix --no-cache-update        # skip menu/icon cache refresh commands
hydra-fix --log-file ~/hydra-fix.log
```

### Command-line reference

| Option | Description |
| --- | --- |
| `-n`, `--dry-run` | Report actions without writing files or deleting anything. |
| `--check` | Validate dependencies, paths, Hydra's binary, and watcher tools. |
| `--fix-desktop-only` | Repair and clean shortcuts without extracting icons. |
| `--repair-icons-only` | Extract icons without changing desktop entries. |
| `--only APPID` | Limit the run to one Hydra app ID. Repeat for several games. |
| `--no-prune` | Keep stale, hidden, and duplicate Hydra shortcuts. |
| `--force` | Re-extract icons even when the cached PNG is up to date. |
| `--no-cache-update` | Do not run `update-desktop-database` or `gtk-update-icon-cache`. |
| `--hydra-bin PATH` | Hydra launcher binary. |
| `--config-dir PATH` | Hydra config directory. |
| `--assets-dir PATH` | Hydra asset directory. |
| `--desktop-dir PATH` | Desktop folder to repair. |
| `-v`, `--verbose` | Show debug details, including skipped records and file paths. |
| `-q`, `--quiet` | Only show warnings and errors. |
| `--log-file PATH` | Append timestamped diagnostics to a file. |
| `--version` | Print the version. |

`--only` disables pruning so a targeted repair cannot remove unrelated games.
A normal run prunes only entries that are identifiable as Hydra-managed
(`hydralauncher://run`) and provably stale.

### Typical workflow

```sh
# After installing or updating a game in Hydra
hydra-fix

# If something looks wrong
hydra-fix --dry-run --verbose
hydra-fix --check
```

## Automatic watcher

`install.sh` enables `hydra-watch.service`, a systemd user service that:

- runs once at startup,
- watches `Assets/`, the Hydra database, `logs/`, and your Desktop folder,
- debounces bursts of filesystem events,
- reconnects with a short delay if `inotifywait` exits (for example when Hydra
  recreates its database directory),
- logs the file path that triggered each run,
- uses `flock` so overlapping runs cannot race.

Commands:

```sh
systemctl --user status hydra-watch.service
journalctl --user -u hydra-watch.service -f
systemctl --user restart hydra-watch.service
systemctl --user stop hydra-watch.service
```

Watcher tuning:

```sh
# In ~/.config/hydra-launcher-icon-fix/env
HYDRA_WATCH_DEBOUNCE=5      # seconds to absorb a burst of changes
HYDRA_WATCH_VERBOSE=1       # pass --verbose to each fixer run
```

## Configuration

All paths can be set with environment variables or CLI options. Relative paths
are resolved against your home directory.

| Variable | Default | CLI equivalent |
| --- | --- | --- |
| `HYDRA_BIN` | `/opt/Hydra/hydralauncher` or `hydralauncher` on `PATH` | `--hydra-bin` |
| `HYDRA_CONFIG_DIR` | `${XDG_CONFIG_HOME:-~/.config}/hydralauncher` | `--config-dir` |
| `HYDRA_ASSETS_DIR` | `<config-dir>/Assets` | `--assets-dir` |
| `HYDRA_DB_PATH` | `<config-dir>/hydra-db` | — |
| `HYDRA_UMU_LOG` | `<config-dir>/logs/umu.log` | — |
| `HYDRA_ICON_DIR` | `${XDG_DATA_HOME:-~/.local/share}/icons/hicolor/256x256/apps` | — |
| `HYDRA_APPLICATIONS_DIR` | `${XDG_DATA_HOME:-~/.local/share}/applications` | — |
| `HYDRA_DESKTOP_DIR` | XDG Desktop folder, usually `~/Desktop` | `--desktop-dir` |
| `XDG_CONFIG_HOME` | `~/.config` | — |
| `XDG_DATA_HOME` | `~/.local/share` | — |

Watcher-only variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HYDRA_WATCH_DEBOUNCE` | `3` | Seconds to absorb event bursts. |
| `HYDRA_WATCH_VERBOSE` | `0` | Set to `1` to pass `--verbose`. |
| `HYDRA_LOG_DIR` | `<config-dir>/logs` | Additional directory to watch. |
| `HYDRA_FIX_BIN` | `~/.local/bin/hydra-fix` | Fixer executable used by the watcher. |
| `HYDRA_FIX_PACKAGE_DIR` | `~/.local/share/hydra-launcher-icon-fix` | Installed package location. |

### Custom Hydra layouts

For a portable Hydra build or a non-standard install location:

```sh
HYDRA_BIN=/path/to/hydralauncher \
HYDRA_CONFIG_DIR=/path/to/hydra-data \
hydra-fix --dry-run --verbose
```

To make the watcher use the same paths, create
`~/.config/hydra-launcher-icon-fix/env`:

```sh
HYDRA_BIN=/path/to/hydralauncher
HYDRA_CONFIG_DIR=/path/to/hydra-data
```

Then restart the service:

```sh
systemctl --user restart hydra-watch.service
```

For a non-default Desktop folder:

```sh
HYDRA_DESKTOP_DIR="$HOME/My Desktop" hydra-fix
```

## How the discovery works

1. If available, Hydra's LevelDB is copied to a temporary directory and read
   through Hydra's own bundled Electron/LevelDB modules. The live database is
   never opened directly, so Hydra can keep running.
2. If the database cannot be read, `logs/umu.log` is parsed for launched
   executables.
3. A game counts as installed only when its executable still exists on disk.
4. Hydra artwork is mapped from `Assets/steam-<appid>/`.
5. Only games with artwork or an existing Hydra-managed shortcut are processed.

The database reader is optional. A Hydra update may change its internal
database or Electron packaging; in that case the fixer logs a warning and uses
the launch log until the reader is updated.

## Update

```sh
cd hydra-launcher-icon-fix
git pull --ff-only
./install.sh
```

The installer replaces the previously installed package, backs up a changed
service file, and restarts the watcher so the new code is loaded immediately.

## Troubleshooting

Start with:

```sh
hydra-fix --check
hydra-fix --dry-run --verbose
journalctl --user -u hydra-watch.service -n 80 --no-pager
```

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Icon is still generic in the taskbar | Desktop/icon cache is stale | `hydra-fix --force`, then log out and back in. On X11 you can also press `Alt+F2`, run `r`, and press Enter. |
| Icon is generic but the menu icon is correct | Window class did not match | Check `StartupWMClass` in the shortcut (normally `steam_app_<appid>`). Report a game whose window class differs. |
| Game is missing from the app menu | No Hydra artwork and no existing Hydra shortcut | Launch the game once in Hydra so it downloads artwork, or run `hydra-fix --only <appid>`. |
| Shortcut does nothing | Hydra binary path is wrong or moved | `hydra-fix --check`; set `HYDRA_BIN` or `--hydra-bin`. |
| Duplicate game entries | Old Hydra shortcuts with different names | Run `hydra-fix` without `--no-prune`; duplicates managed by Hydra are removed. |
| Desktop shortcut is not repaired | Desktop folder is elsewhere | Set `HYDRA_DESKTOP_DIR` or pass `--desktop-dir`. |
| `Hydra database could not be read` | Hydra changed its LevelDB/Electron packaging | The fixer falls back to `umu.log`. Run with `--verbose` and include the message in a bug report. |
| `Cannot find module 'abstract-level'` | Hydra's bundled modules are missing or moved | Reinstall Hydra, ensure `HYDRA_BIN` points at the real launcher, and run `hydra-fix --check`. |
| `ImageMagick ... not found` | ImageMagick is not installed | Install it, or use `--fix-desktop-only`. |
| Watcher is inactive | Missing `inotifywait`/`flock`, or no systemd user session | `systemctl --user status hydra-watch.service`; install the missing tools and restart it. |
| `Permission denied` | Ran with `sudo` or files are owned by another user | Run as your desktop user and fix ownership of files in your home directory. |
| Changes only appear after logging in again | GNOME Shell/Wayland caches application data | Log out and back in. `update-desktop-database` and `gtk-update-icon-cache` handle most cases. |

When reporting a bug, include:

- your distribution and desktop version,
- `hydra-fix --version`,
- the output of `hydra-fix --check`,
- the output of `hydra-fix --dry-run --verbose`,
- your Hydra version and how it was installed.

## Uninstall

```sh
./uninstall.sh --dry-run   # preview
./uninstall.sh
```

The uninstaller stops and removes the watcher service, the two commands, and the
installed Python package. Generated game shortcuts and icons are intentionally
left in place.

Manual removal:

```sh
systemctl --user disable --now hydra-watch.service
rm -f ~/.config/systemd/user/hydra-watch.service
rm -rf ~/.config/systemd/user/hydra-watch.service.d
rm -f ~/.local/bin/hydra-fix ~/.local/bin/hydra-watch
rm -rf ~/.local/share/hydra-launcher-icon-fix
systemctl --user daemon-reload
```

To remove generated shortcuts and icons too, delete entries containing
`hydralauncher://run` or `X-Hydra-Fix=true` from
`~/.local/share/applications/`, and remove
`~/.local/share/icons/hicolor/256x256/apps/steam_icon_*.png`. Review the files
before deleting so you do not remove entries created by something else.

## Development

The implementation is a small Python package:

```text
hydra_fix/
  cli.py           argument parsing and command dispatch
  config.py        paths, commands, curated names
  discovery.py     LevelDB snapshot reader, umu.log parser, install detection
  icons.py         ImageMagick probing and extraction
  desktop.py       .desktop parsing, validation, generation, repair
  cleanup.py       stale and duplicate shortcut removal
  runner.py        orchestration for full and partial runs
  dependencies.py  pre-flight checks and diagnostics
  models.py        typed records and run options
  log.py           leveled console/file logger
  text.py          filename and desktop-value sanitizers
hydra-fix          launcher for a source checkout or installed copy
hydra-watch        debounced inotify watcher
install.sh         installer
uninstall.sh       uninstaller
```

Run the test suite:

```sh
python3 -m unittest discover -s tests -v
```

Static checks used by the project:

```sh
python3 -m compileall -q hydra_fix
bash -n hydra-watch install.sh uninstall.sh
systemd-analyze verify hydra-watch.service
```

Build a wheel:

```sh
python3 -m pip install --user build
python3 -m build
```

## Notes and limitations

- This is a Linux-only tool. It relies on freedesktop `.desktop` entries and
  XDG icon themes.
- Game display names come from Hydra's database. Curated overrides live in
  `KNOWN_NAMES` in `hydra_fix/config.py`; unknown games fall back to the
  database title, an existing shortcut name, or the executable name.
- Hydra's internals can change. The database reader is best-effort and always
  falls back to the launch log.
- The watcher is per-user. On multi-user systems, each user who runs Hydra
  should install and enable it in their own session.

## License

MIT. See [LICENSE](LICENSE).
