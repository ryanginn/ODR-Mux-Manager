"""supervisord control: XML-RPC over its unix socket, falling back to `sudo -n supervisorctl`.

The default supervisord socket is root-only (chmod 0700), so a manager running as a normal user
gets "Permission denied". The installer adds a sudoers rule that allows exactly
`supervisorctl` and `systemctl restart supervisor` without a password; this module then uses
`sudo -n supervisorctl ...` whenever the socket refuses us.
"""
from __future__ import annotations

import http.client
import re
import shutil
import socket
import subprocess
import time
import xmlrpc.client
from typing import List, Optional


class _UnixConn(http.client.HTTPConnection):
    def __init__(self, path, timeout=5):
        super().__init__('localhost', timeout=timeout)
        self._path = path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._path)
        self.sock = s


class _UnixTransport(xmlrpc.client.Transport):
    def __init__(self, path, timeout=5):
        super().__init__()
        self._path = path
        self._timeout = timeout

    def make_connection(self, host):
        return _UnixConn(self._path, self._timeout)


class SupervisorError(RuntimeError):
    pass


_STATUS = re.compile(r'^(?P<name>\S+)\s+(?P<state>[A-Z_]+)\s*(?P<desc>.*)$')
_UPTIME = re.compile(r'uptime (?:(\d+) days?, )?(\d+):(\d+):(\d+)')


def _sudo_path():
    return shutil.which('sudo') or '/usr/bin/sudo'


class Supervisor:
    def __init__(self, socket_path: str = '/var/run/supervisor.sock', ctl: str = 'supervisorctl',
                 conf: Optional[str] = None, timeout=5, use_sudo: str = 'auto',
                 restart_cmd: str = 'sudo -n systemctl restart supervisor'):
        self.socket_path = socket_path
        self.ctl = ctl
        self.conf = conf
        self.timeout = timeout
        self.use_sudo = use_sudo          # auto | always | never
        self.restart_cmd = restart_cmd

    # ------------------------------------------------------------------ transports
    def _proxy(self):
        if self.socket_path.startswith(('http://', 'https://')):
            return xmlrpc.client.ServerProxy(self.socket_path.rstrip('/') + '/RPC2')
        return xmlrpc.client.ServerProxy('http://localhost/RPC2', transport=_UnixTransport(self.socket_path, self.timeout))

    def _rpc_ok(self) -> bool:
        return self.use_sudo != 'always'

    def _ctl(self, *args, timeout=60, check=True) -> str:
        ctl = shutil.which(self.ctl) or self.ctl
        cmd = [ctl] + (['-c', self.conf] if self.conf else []) + list(args)
        if self.use_sudo != 'never':
            cmd = [_sudo_path(), '-n'] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or '') + (r.stderr or '')
        if 'a password is required' in out or 'sudo:' in out and r.returncode != 0:
            raise SupervisorError('No permission to control supervisor: the socket is root-only and sudo needs a '
                                  'password. Re-run the installer (it adds a sudoers rule for supervisorctl), or set '
                                  'chmod=0770 / chown=root:<group> under [unix_http_server] in supervisord.conf.')
        # supervisorctl status exits 3 when some programs aren't running; that's not an error for us
        if check and r.returncode not in (0, 3):
            raise SupervisorError(f'supervisorctl {" ".join(args)}: {out.strip()}')
        return r.stdout or ''

    def _call(self, rpc, cli):
        """Try XML-RPC; on permission problems (or when told to) use sudo supervisorctl."""
        if self._rpc_ok():
            try:
                return rpc()
            except PermissionError:
                if self.use_sudo == 'never':
                    raise SupervisorError(f'Permission denied on {self.socket_path}')
            except (FileNotFoundError, ConnectionRefusedError) as e:
                if self.use_sudo == 'never':
                    raise SupervisorError(f'supervisord is not reachable at {self.socket_path}: {e}')
            except OSError as e:
                if getattr(e, 'errno', None) not in (13,) or self.use_sudo == 'never':
                    raise
        return cli()

    # ------------------------------------------------------------------ API
    def available(self) -> bool:
        try:
            self.processes()
            return True
        except Exception:
            return False

    def processes(self) -> dict:
        """name -> {statename, description, start, pid}."""
        def rpc():
            return {p['name']: p for p in self._proxy().supervisor.getAllProcessInfo()}

        def cli():
            out = {}
            now = int(time.time())
            for line in self._ctl('status', timeout=20).splitlines():
                m = _STATUS.match(line.strip())
                if not m:
                    continue
                desc = m.group('desc').strip()
                start = None
                u = _UPTIME.search(desc)
                if u:
                    d, hh, mm, ss = (int(x) if x else 0 for x in u.groups())
                    start = now - (d * 86400 + hh * 3600 + mm * 60 + ss)
                pid = re.search(r'pid (\d+)', desc)
                name = m.group('name').split(':')[-1] if ':' in m.group('name') else m.group('name')
                out[name] = {'name': name, 'statename': m.group('state'), 'description': desc, 'start': start,
                             'now': now, 'pid': int(pid.group(1)) if pid else 0}
            return out
        return self._call(rpc, cli)

    def start(self, name):
        return self._call(lambda: self._proxy().supervisor.startProcess(name, True), lambda: self._ctl('start', name))

    def stop(self, name):
        def rpc():
            try:
                return self._proxy().supervisor.stopProcess(name, True)
            except xmlrpc.client.Fault as f:
                if 'NOT_RUNNING' in str(f):
                    return True
                raise
        return self._call(rpc, lambda: self._ctl('stop', name))

    def restart(self, name):
        def rpc():
            p = self._proxy()
            try:
                p.supervisor.stopProcess(name, True)
            except xmlrpc.client.Fault as f:
                if 'NOT_RUNNING' not in str(f):
                    raise
            return p.supervisor.startProcess(name, True)
        return self._call(rpc, lambda: self._ctl('restart', name))

    def tail(self, name, length=8000):
        def rpc():
            data, offset, overflow = self._proxy().supervisor.tailProcessStdoutLog(name, 0, length)
            return data
        return self._call(rpc, lambda: self._ctl('tail', f'-{int(length)}', name, timeout=20))

    def update(self) -> List[str]:
        """`supervisorctl reread && supervisorctl update`: only changed programs restart."""
        def rpc():
            log = []
            prox = self._proxy()
            added, changed, removed = prox.supervisor.reloadConfig()[0]
            for g in removed:
                try:
                    prox.supervisor.stopProcessGroup(g)
                except xmlrpc.client.Fault:
                    pass
                prox.supervisor.removeProcessGroup(g)
                log.append(f'removed {g}')
            for g in changed:
                try:
                    prox.supervisor.stopProcessGroup(g)
                except xmlrpc.client.Fault:
                    pass
                prox.supervisor.removeProcessGroup(g)
                prox.supervisor.addProcessGroup(g)
                log.append(f'restarted {g} (config changed)')
            for g in added:
                prox.supervisor.addProcessGroup(g)
                log.append(f'added {g}')
            return log

        def cli():
            log = []
            for sub in ('reread', 'update'):
                out = self._ctl(sub).strip()
                log.append(f'supervisorctl {sub}: {out or "ok"}')
            return log
        return self._call(rpc, cli)

    def restart_service(self) -> List[str]:
        """Restart the whole supervisor service (every program restarts)."""
        r = subprocess.run(self.restart_cmd, shell=True, capture_output=True, text=True, timeout=120)
        out = ((r.stdout or '') + (r.stderr or '')).strip()
        if r.returncode != 0:
            if 'password is required' in out:
                raise SupervisorError('sudo needs a password for "systemctl restart supervisor". Re-run the '
                                      'installer to add the sudoers rule, or switch Apply back to reread/update.')
            raise SupervisorError(f'{self.restart_cmd}: {out}')
        return [f'restarted the supervisor service ({self.restart_cmd})']
