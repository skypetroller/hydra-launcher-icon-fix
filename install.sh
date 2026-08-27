#!/usr/bin/env bash
# Install the Hydra icon fixer and its watcher service.
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
SERVICE_DIR="${HOME}/.config/systemd/user"

for command in python3 convert identify inotifywait flock systemctl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    echo "Install dependencies with: sudo apt install imagemagick inotify-tools" >&2
    exit 1
  fi
done

mkdir -p "${BIN_DIR}" "${SERVICE_DIR}"

install -m 0755 "${SCRIPT_DIR}/hydra-fix" "${BIN_DIR}/hydra-fix"
install -m 0755 "${SCRIPT_DIR}/hydra-watch" "${BIN_DIR}/hydra-watch"
install -m 0644 "${SCRIPT_DIR}/hydra-watch.service" "${SERVICE_DIR}/hydra-watch.service"

systemctl --user daemon-reload
systemctl --user enable --now hydra-watch.service

echo "Installed. Running once now..."
"${BIN_DIR}/hydra-fix"
