#!/usr/bin/env bash
# sudo ./uninstall.sh          remove the service, keep config and data (users, backups)
# sudo ./uninstall.sh --purge  remove everything (never touches your mux folder)
set -euo pipefail
APP=odr-mux-manager
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
systemctl disable --now "$APP" 2>/dev/null || true
rm -f /etc/systemd/system/$APP.service /usr/local/bin/$APP /etc/sudoers.d/$APP
systemctl daemon-reload
rm -rf /opt/$APP
if [ "${1:-}" = "--purge" ]; then
    rm -rf /etc/$APP /var/lib/$APP
    echo "Removed everything. Your mux folder was not touched."
else
    echo "Removed the service. Config (/etc/$APP) and data (/var/lib/$APP) were kept."
fi
