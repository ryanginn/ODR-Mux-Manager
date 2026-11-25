#!/usr/bin/env bash
# ODR Mux Manager installer.
#   sudo ./install.sh                 interactive
#   sudo ./install.sh --yes           accept defaults
#   sudo ./install.sh --port 8092 --bind 0.0.0.0 --user ryan
#   sudo ./install.sh --with-ffmpeg   also build a private ffmpeg (libx264 + libfdk_aac) for DMB
set -euo pipefail

APP=odr-mux-manager
PREFIX=/opt/$APP
CONF_DIR=/etc/$APP
CONF=$CONF_DIR/config.json
DATA=/var/lib/$APP
UNIT=/etc/systemd/system/$APP.service
SRC="$(cd "$(dirname "$0")" && pwd)"

PORT=8092
BIND=127.0.0.1
RUN_USER="${SUDO_USER:-}"
ASSUME_YES=0
WITH_FFMPEG=""

die() { echo "error: $*" >&2; exit 1; }
warn() { echo "warning: $*" >&2; }

while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --bind) BIND="$2"; shift 2 ;;
        --user) RUN_USER="$2"; shift 2 ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        --with-ffmpeg) WITH_FFMPEG=1; shift ;;
        --no-ffmpeg) WITH_FFMPEG=0; shift ;;
        -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
        *) die "unknown option $1" ;;
    esac
done

[ "$(id -u)" -eq 0 ] || die "run as root (sudo ./install.sh)"
command -v systemctl >/dev/null || die "systemd is required"

ask() { # ask "question" default -> echo answer
    local q="$1" def="$2" a=""
    if [ "$ASSUME_YES" -eq 1 ] || [ ! -t 0 ]; then echo "$def"; return; fi
    read -r -p "  $q [$def]: " a </dev/tty || true
    echo "${a:-$def}"
}

echo "ODR Mux Manager installer"
echo
echo "  The web UI can listen on this machine only (127.0.0.1: use an SSH tunnel or a reverse"
echo "  proxy) or on all interfaces (0.0.0.0). Admins can change this later in Settings."
BIND=$(ask "Listen address (127.0.0.1 or 0.0.0.0)" "$BIND")
case "$BIND" in 127.0.0.1|0.0.0.0) ;; *) die "listen address must be 127.0.0.1 or 0.0.0.0" ;; esac
PORT=$(ask "Port (the SPI generator uses 8090)" "$PORT")
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || die "port must be 1024-65535"
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT\$"; then
    if ! systemctl is-active --quiet "$APP"; then die "port $PORT is already in use"; fi
fi
echo "  The service user must be able to edit your mux folder (conf.mux, supervisor/, mot/)."
RUN_USER=$(ask "Run as user" "${RUN_USER:-odr}")
echo "  After Apply the manager can either reload only the changed encoders (supervisorctl reread/update)"
echo "  or restart the whole supervisor service (sudo systemctl restart supervisor; every station restarts)."
RELOAD=$(ask "Restart the whole supervisor service on Apply? (y/n)" "y")
case "$RELOAD" in y|Y|yes) RELOAD=restart ;; *) RELOAD=update ;; esac
if [ -z "$WITH_FFMPEG" ]; then
    if [ -x "$PREFIX/ffmpeg/bin/ffmpeg" ]; then WITH_FFMPEG=keep
    else
        echo "  DMB radio/TV sounds better with HE-AAC, which needs an ffmpeg built with libfdk_aac."
        echo "  The installer can build one into $PREFIX/ffmpeg (not on the system PATH; ~10 minutes)."
        a=$(ask "Build a private ffmpeg for DMB? (y/n)" "n")
        case "$a" in y|Y|yes) WITH_FFMPEG=1 ;; *) WITH_FFMPEG=0 ;; esac
    fi
fi
id "$RUN_USER" >/dev/null 2>&1 || die "user $RUN_USER does not exist"
RUN_GROUP=$(id -gn "$RUN_USER")

if command -v apt-get >/dev/null; then
    apt-get install -y -qq python3 python3-venv python3-pip python3-zmq >/dev/null || warn "apt-get failed; continuing"
else
    warn "Not a Debian/Ubuntu system - make sure python3 (>= 3.9) with venv is installed."
fi

mkdir -p "$PREFIX" "$CONF_DIR" "$DATA"
rm -rf "$PREFIX/src"
cp -a "$SRC" "$PREFIX/src"
rm -rf "$PREFIX/src/.git" "$PREFIX/src/tests/fixtures"
if [ ! -x "$PREFIX/venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$PREFIX/venv"
fi
"$PREFIX/venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
"$PREFIX/venv/bin/pip" install -q "$PREFIX/src" || die "pip install failed"
chmod -R u=rwX,go=rX "$PREFIX/venv" "$PREFIX/src"

# private ffmpeg for DMB (kept out of the system PATH)
FFMPEG_BIN=""
if [ "$WITH_FFMPEG" = 1 ]; then
    bash "$SRC/packaging/build-ffmpeg.sh" "$PREFIX/ffmpeg" || warn "ffmpeg build failed; DMB will use the system ffmpeg (AAC-LC)"
fi
[ -x "$PREFIX/ffmpeg/bin/ffmpeg" ] && FFMPEG_BIN="$PREFIX/ffmpeg/bin/ffmpeg"

# command line wrapper (DMB encoder programs run it from supervisor too)
cat > /usr/local/bin/$APP <<WRAP
#!/bin/sh
export ODR_MUX_MANAGER_CONFIG=$CONF
exec $PREFIX/venv/bin/$APP "\$@"
WRAP
chmod 755 /usr/local/bin/$APP

# config: keep an existing one, only update the address
python3 - "$CONF" "$BIND" "$PORT" "$DATA" "$FFMPEG_BIN" "$RELOAD" <<'PY'
import json, sys, os
path, bind, port, data, ffmpeg, reload_mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6]
cfg = {}
if os.path.exists(path):
    cfg = json.load(open(path))
cfg.update(bind=bind, port=port)
cfg.setdefault('state_dir', data)
cfg.setdefault('manager_exe', '/usr/local/bin/odr-mux-manager')
if ffmpeg:
    cfg.setdefault('tool_paths', {})['ffmpeg'] = ffmpeg
cfg['supervisor_reload'] = reload_mode
cfg.setdefault('supervisor_sudo', 'auto')
cfg.setdefault('supervisor_restart_cmd', 'sudo -n systemctl restart supervisor')
json.dump(cfg, open(path, 'w'), indent=2)
PY
chown -R "$RUN_USER:$RUN_GROUP" "$CONF_DIR" "$DATA"
chmod 750 "$CONF_DIR" "$DATA"
chmod 640 "$CONF"

sed -e "s/@USER@/$RUN_USER/" -e "s/@GROUP@/$RUN_GROUP/" "$SRC/packaging/$APP.service" > "$UNIT"
systemctl daemon-reload
systemctl enable "$APP" >/dev/null 2>&1
systemctl restart "$APP"

# supervisor access: the default socket is root-only, so allow exactly these commands without a password
SUDOERS=/etc/sudoers.d/$APP
CTL_BIN=$(command -v supervisorctl || echo /usr/bin/supervisorctl)
SYSTEMCTL_BIN=$(command -v systemctl || echo /usr/bin/systemctl)
TMP_SUDO=$(mktemp)
cat > "$TMP_SUDO" <<SUDO
# Written by the odr-mux-manager installer: lets the web UI read encoder state/logs, restart
# encoders and reload or restart supervisor. Nothing else.
$RUN_USER ALL=(root) NOPASSWD: $CTL_BIN *, $SYSTEMCTL_BIN restart supervisor, $SYSTEMCTL_BIN restart supervisor.service
SUDO
if visudo -cqf "$TMP_SUDO"; then
    install -m 0440 -o root -g root "$TMP_SUDO" "$SUDOERS"
    echo "  Added $SUDOERS (supervisorctl and 'systemctl restart supervisor' for $RUN_USER)."
else
    warn "could not validate the sudoers rule; the manager may not be able to control supervisor"
fi
rm -f "$TMP_SUDO"

for _ in $(seq 1 20); do
    if curl -fs -o /dev/null "http://127.0.0.1:$PORT/api/state" 2>/dev/null; then break; fi
    sleep 0.5
done
TOKEN=$(runuser -u "$RUN_USER" -- /usr/local/bin/$APP setup-token 2>/dev/null || true)
HOST=$( [ "$BIND" = 0.0.0.0 ] && (hostname -I 2>/dev/null | awk '{print $1}') || echo 127.0.0.1)
echo
echo "Installation complete."
echo
echo "  Open the web UI:"
echo "    http://${HOST:-127.0.0.1}:$PORT/?token=$TOKEN"
echo
echo "  First-run setup token: $TOKEN"
echo "  (show it again with: sudo $APP setup-token)"
echo
echo "  Service:   systemctl status $APP    ·    logs: journalctl -u $APP -f"
