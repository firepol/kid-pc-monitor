#!/usr/bin/env bash
# Install the Kid PC Monitor agent on a Linux kid PC as a systemd *user* service
# so it starts with the kid's desktop session. Run as the kid's user (not root):
#
#     scripts/install_linux.sh           # install + start
#     scripts/install_linux.sh --remove  # stop + uninstall
#
# After installing, set the parent password with:
#     python3 scripts/set_password.py
#
# Note: a user service can be stopped by that user. For a tamper-resistant setup,
# adapt this to a system service running as a dedicated account. Opening the web
# port in the firewall (ufw/firewalld) is left to you as it varies by distro.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="kidmon.service"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_PATH="${UNIT_DIR}/${SERVICE_NAME}"
PYTHON="$(command -v python3)"

remove() {
  systemctl --user stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl --user disable "${SERVICE_NAME}" 2>/dev/null || true
  rm -f "${UNIT_PATH}"
  systemctl --user daemon-reload || true
  echo "Removed ${SERVICE_NAME}."
}

if [[ "${1:-}" == "--remove" ]]; then
  remove
  exit 0
fi

mkdir -p "${UNIT_DIR}"
# Bind the service to the graphical session: locking the screen needs DISPLAY /
# XDG_SESSION_ID, which only exist inside the desktop session. (An earlier
# version lingered the user manager so it ran at boot — but that starts before
# any graphical login, with no DISPLAY, so lock() silently no-ops. We do NOT
# enable linger here for exactly that reason.)
cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=Kid PC Monitor agent
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${PYTHON} ${REPO_ROOT}/agent.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}"

echo "Installed and started ${SERVICE_NAME}."
echo "Set the parent password with: python3 scripts/set_password.py"
echo "Check status: systemctl --user status ${SERVICE_NAME}"
