#!/usr/bin/env bash
# Install or upgrade the Hydra icon fixer and its user service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hydra-watch.service"
BIN_DIR="${HOME}/.local/bin"
SERVICE_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
PACKAGE_DIR="${DATA_HOME}/hydra-launcher-icon-fix"

DRY_RUN=0
NO_SERVICE=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [--dry-run] [--no-service]

  --dry-run     Show what would be installed without changing anything.
  --no-service  Install the scripts but do not enable/start the user service.
  -h, --help    Show this help.

Environment:
  HYDRA_BIN          Path to the Hydra launcher (default: auto-detect).
  HYDRA_CONFIG_DIR   Hydra config directory (default: ~/.config/hydralauncher).
  XDG_CONFIG_HOME    Base config directory for the systemd user unit.
  XDG_DATA_HOME      Base data directory for the installed Python package.
EOF
}

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-service) NO_SERVICE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }
systemd_quote() {
  local value="${1//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

missing=()
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    missing+=("$1")
  fi
}

need python3
need install
need flock
need inotifywait
if (( NO_SERVICE == 0 )); then
  need systemctl
fi
if ! command -v magick >/dev/null 2>&1; then
  need convert
  need identify
fi

optional_missing=()
for command in update-desktop-database gtk-update-icon-cache; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    optional_missing+=("${command}")
  fi
done

if ((${#missing[@]})); then
  fail "missing required command(s): ${missing[*]}
Install them with one of:
  Debian/Ubuntu/Zorin: sudo apt install imagemagick inotify-tools util-linux
  Fedora:             sudo dnf install ImageMagick inotify-tools util-linux
  Arch:               sudo pacman -S imagemagick inotify-tools util-linux"
fi

hydra_bin="${HYDRA_BIN:-}"
if [[ -z "${hydra_bin}" ]]; then
  if [[ -x /opt/Hydra/hydralauncher ]]; then
    hydra_bin="/opt/Hydra/hydralauncher"
  elif command -v hydralauncher >/dev/null 2>&1; then
    hydra_bin="$(command -v hydralauncher)"
  fi
fi
if [[ -z "${hydra_bin}" || ! -x "${hydra_bin}" ]]; then
  fail "Hydra launcher not found. Install Hydra, or set HYDRA_BIN=/path/to/hydralauncher."
fi

if ((DRY_RUN == 0)); then
  export HYDRA_BIN="${hydra_bin}"
  if ! python3 "${SCRIPT_DIR}/hydra-fix" --check; then
    fail "pre-flight check failed. Fix the errors above and run ./install.sh again."
  fi
else
  info "Would run: python3 ${SCRIPT_DIR}/hydra-fix --check"
fi

if ((${#optional_missing[@]})); then
  warn "optional cache tools not found: ${optional_missing[*]}"
  warn "install desktop-file-utils and your GTK package for automatic menu/icon refreshes."
fi

if [[ -f "${SERVICE_DIR}/${SERVICE_NAME}" ]]; then
  info "Existing service file: ${SERVICE_DIR}/${SERVICE_NAME}"
  if ((DRY_RUN == 0)) && systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Existing watcher is active; it will be restarted with the new version."
  fi
  if ! cmp -s "${SCRIPT_DIR}/${SERVICE_NAME}" "${SERVICE_DIR}/${SERVICE_NAME}"; then
    info "Existing service file differs and will be upgraded (backup: ${SERVICE_NAME}.bak)."
  fi
else
  info "Fresh installation."
fi

if [[ -f "${BIN_DIR}/hydra-fix" ]]; then
  info "Updating existing ${BIN_DIR}/hydra-fix."
fi
if [[ -d "${PACKAGE_DIR}" ]]; then
  info "Updating existing package in ${PACKAGE_DIR}."
fi

if ((DRY_RUN)); then
  cat <<EOF
Would install:
  ${BIN_DIR}/hydra-fix
  ${BIN_DIR}/hydra-watch
  ${PACKAGE_DIR}/hydra_fix/
  ${SERVICE_DIR}/${SERVICE_NAME}
EOF
  if ((NO_SERVICE == 0)); then
    info "Would enable and restart ${SERVICE_NAME}."
  else
    info "Would skip service setup (--no-service)."
  fi
  exit 0
fi

install -d "${BIN_DIR}" "${SERVICE_DIR}" "${PACKAGE_DIR}"
rm -rf "${PACKAGE_DIR}/hydra_fix"
cp -a "${SCRIPT_DIR}/hydra_fix" "${PACKAGE_DIR}/hydra_fix"
find "${PACKAGE_DIR}/hydra_fix" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${PACKAGE_DIR}/hydra_fix" -type f -name '*.pyc' -delete

install -m 0755 "${SCRIPT_DIR}/hydra-fix" "${BIN_DIR}/hydra-fix"
install -m 0755 "${SCRIPT_DIR}/hydra-watch" "${BIN_DIR}/hydra-watch"
if ! cmp -s "${SCRIPT_DIR}/${SERVICE_NAME}" "${SERVICE_DIR}/${SERVICE_NAME}" 2>/dev/null; then
  if [[ -f "${SERVICE_DIR}/${SERVICE_NAME}" ]]; then
    cp -p "${SERVICE_DIR}/${SERVICE_NAME}" "${SERVICE_DIR}/${SERVICE_NAME}.bak"
  fi
  install -m 0644 "${SCRIPT_DIR}/${SERVICE_NAME}" "${SERVICE_DIR}/${SERVICE_NAME}"
fi

# Persist non-default paths in a systemd drop-in so the watcher sees the same
# Hydra install and package location as this shell.
override_lines=()
if [[ "${hydra_bin}" != "/opt/Hydra/hydralauncher" ]]; then
  override_lines+=("Environment=$(systemd_quote "HYDRA_BIN=${hydra_bin}")")
fi
if [[ -n "${HYDRA_CONFIG_DIR:-}" ]]; then
  override_lines+=("Environment=$(systemd_quote "HYDRA_CONFIG_DIR=${HYDRA_CONFIG_DIR}")")
fi
if [[ "${PACKAGE_DIR}" != "${HOME}/.local/share/hydra-launcher-icon-fix" ]]; then
  override_lines+=("Environment=$(systemd_quote "HYDRA_FIX_PACKAGE_DIR=${PACKAGE_DIR}")")
fi
if ((${#override_lines[@]})); then
  override_dir="${SERVICE_DIR}/${SERVICE_NAME}.d"
  override_file="${override_dir}/override.conf"
  install -d "${override_dir}"
  if [[ -f "${override_file}" ]]; then
    cp -p "${override_file}" "${override_file}.bak"
  fi
  {
    printf '%s\n' "# Managed by hydra-launcher-icon-fix"
    printf '%s\n' "[Service]"
    printf '%s\n' "${override_lines[@]}"
  } >"${override_file}"
  info "Wrote service overrides: ${override_file}"
fi

if ((NO_SERVICE)); then
  info "Installed. Service setup skipped (--no-service)."
  info "Run once now: ${BIN_DIR}/hydra-fix"
  "${BIN_DIR}/hydra-fix"
  info "Start the watcher manually with: ${BIN_DIR}/hydra-watch"
  exit 0
fi

if ! systemctl --user show-environment >/dev/null 2>&1; then
  warn "systemd user session is not available in this shell."
  warn "Scripts are installed; run ${BIN_DIR}/hydra-watch manually, or log in to a desktop session and rerun ./install.sh."
  exit 0
fi

systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}"
systemctl --user restart "${SERVICE_NAME}"
sleep 1

if systemctl --user is-active --quiet "${SERVICE_NAME}"; then
  info "Installed. Watcher is active and enabled."
  info "Diagnostics: ${BIN_DIR}/hydra-fix --check"
  info "Logs: journalctl --user -u ${SERVICE_NAME} -f"
else
  warn "Watcher did not start."
  systemctl --user status "${SERVICE_NAME}" --no-pager --lines=20 >&2 || true
  fail "installation incomplete; inspect the service output above."
fi
