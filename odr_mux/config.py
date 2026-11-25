"""Service configuration (/etc/odr-mux-manager/config.json) and runtime settings."""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from pathlib import Path

DEFAULT_CONFIG_PATH = os.environ.get('ODR_MUX_MANAGER_CONFIG', '/etc/odr-mux-manager/config.json')

DEFAULTS = {
    # network
    'bind': '127.0.0.1',
    'port': 8092,
    'behind_proxy': False,
    'session_hours': 12,
    # storage
    'state_dir': '/var/lib/odr-mux-manager',
    # project (set by the import wizard)
    'project_root': None,
    'mux_path': None,
    'supervisor_paths': None,
    # supervisor / dabmux control
    'supervisor_socket': '/var/run/supervisor.sock',
    'supervisorctl': 'supervisorctl',
    'supervisor_conf': None,          # passed as -c to supervisorctl when set
    'dabmux_restart': 'auto',         # auto | none | supervisor:<program> | systemd:<unit> | command:<cmd>
    'run_commands': True,             # False = write files only (dry environments, tests)
    # monitoring
    'levels_source': 'dabmux',        # dabmux | stats | both
    'dabmux_mgmt': None,              # tcp://127.0.0.1:<managementport>, default from mux file
    'onair_edi': 'auto',              # auto | off | tcp://host:port of an EDI output to decode
    'silence_db': -50,
    'silence_secs': 10,
    'check_fs': True,
    'stats_dir': '/var/tmp',
    'encoder_user': None,
    'tool_paths': {},                 # override odr-audioenc / odr-dabmux / odr-padenc / ffmpeg paths
}


def load(path=None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    cfg = dict(DEFAULTS)
    try:
        with open(path) as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    cfg['_path'] = path
    return cfg


def save(cfg: dict):
    path = cfg.get('_path') or DEFAULT_CONFIG_PATH
    data = {k: v for k, v in cfg.items() if not k.startswith('_')}
    atomic_write(path, json.dumps(data, indent=2) + '\n', mode=0o640)


def atomic_write(path, text: str, mode=None, keep_meta=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    st = None
    if keep_meta and path.exists():
        st = path.stat()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if st is not None:
            os.chmod(tmp, st.st_mode & 0o7777)
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except PermissionError:
                pass
        elif mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ network change with auto-revert
REVERT_SECONDS = 60


def pending_network_path(cfg):
    return Path(cfg['state_dir']) / 'network-pending.json'


def request_network_change(cfg, bind, port):
    """Store the new address, remember the old one, and return a confirm token."""
    token = secrets.token_urlsafe(16)
    pend = {'old': {'bind': cfg['bind'], 'port': cfg['port']}, 'new': {'bind': bind, 'port': port},
            'token': token, 'deadline': None}
    atomic_write(pending_network_path(cfg), json.dumps(pend), mode=0o600)
    cfg['bind'], cfg['port'] = bind, int(port)
    save(cfg)
    return token


def startup_pending(cfg):
    """Called at startup. Starts the revert clock if a change is unconfirmed."""
    p = pending_network_path(cfg)
    try:
        pend = json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if pend.get('deadline') and time.time() > pend['deadline']:
        # the new address was never confirmed: go back
        cfg['bind'], cfg['port'] = pend['old']['bind'], pend['old']['port']
        save(cfg)
        p.unlink(missing_ok=True)
        return {'reverted': True}
    if not pend.get('deadline'):
        pend['deadline'] = time.time() + REVERT_SECONDS
        atomic_write(p, json.dumps(pend), mode=0o600)
    return pend


def confirm_network(cfg, token) -> bool:
    p = pending_network_path(cfg)
    try:
        pend = json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return False
    if not secrets.compare_digest(str(pend.get('token')), str(token or '')):
        return False
    p.unlink(missing_ok=True)
    return True
