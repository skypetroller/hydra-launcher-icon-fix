#!/usr/bin/env bash
# Remove the installed fixer and watcher service. Generated icons and shortcuts
# are intentionally left in place.
set -euo pipefail

SERVICE_NAME="hydra-watch.service"
BIN_DIR="${HOME}/.local/bin"
SERVICE_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
PACKAGE_DIR="${DATA_HOME}/hydra-launcher-icon-fix"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./uninstall.sh [--dry-run]

Stops and removes the watcher service, scripts, and installed Python package.
Generated game shortcuts and icons are not removed.
EOF
}

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

run() {
  if ((DRY_RUN)); then
    printf 'would run: %s\n' "$*"
  else
    "$@"
  fi
}

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  run systemctl --user disable --now "${SERVICE_NAME}" || true
fi

run rm -f "${SERVICE_DIR}/${SERVICE_NAME}" "${SERVICE_DIR}/${SERVICE_NAME}.bak"
run rm -f "${BIN_DIR}/hydra-fix" "${BIN_DIR}/hydra-watch"
run rm -rf "${PACKAGE_DIR}"

if ((DRY_RUN == 0)) && command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || true
fi

echo "Uninstalled. Generated icons and game shortcuts were left in place."
