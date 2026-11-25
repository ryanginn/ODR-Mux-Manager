"""Minimal supervisord XML-RPC client over its unix socket (or http://host:port)."""
from __future__ import annotations

import http.client
import socket
import subprocess
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


class Supervisor:
    def __init__(self, socket_path: str = '/var/run/supervisor.sock', ctl: str = 'supervisorctl',
                 conf: Optional[str] = None, timeout=5):
        self.socket_path = socket_path
        self.ctl = ctl
        self.conf = conf
        self.timeout = timeout

    def _proxy(self):
        if self.socket_path.startswith(('http://', 'https://')):
            return xmlrpc.client.ServerProxy(self.socket_path.rstrip('/') + '/RPC2')
        return xmlrpc.client.ServerProxy('http://localhost/RPC2', transport=_UnixTransport(self.socket_path, self.timeout))

    def available(self) -> bool:
        try:
            self._proxy().supervisor.getState()
            return True
        except Exception:
            return False

    def processes(self) -> dict:
        """name -> info (statename, description, start, now, pid, exitstatus)."""
        out = {}
        for p in self._proxy().supervisor.getAllProcessInfo():
            out[p['name']] = p
        return out

    def start(self, name):
        return self._proxy().supervisor.startProcess(name, True)

    def stop(self, name):
        try:
            return self._proxy().supervisor.stopProcess(name, True)
        except xmlrpc.client.Fault as f:
            if 'NOT_RUNNING' in str(f):
                return True
            raise

    def restart(self, name):
        self.stop(name)
        return self.start(name)

    def tail(self, name, length=8000):
        data, offset, overflow = self._proxy().supervisor.tailProcessStdoutLog(name, 0, length)
        return data

    def update(self) -> List[str]:
        """Equivalent of `supervisorctl reread && supervisorctl update`."""
        log = []
        try:
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
        except (OSError, xmlrpc.client.Error) as e:
            # fall back to supervisorctl (e.g. socket not readable but sudo rule present)
            cmd = [self.ctl] + (['-c', self.conf] if self.conf else [])
            for sub in ('reread', 'update'):
                r = subprocess.run(cmd + [sub], capture_output=True, text=True, timeout=60)
                log.append(f'supervisorctl {sub}: {(r.stdout + r.stderr).strip()}')
                if r.returncode != 0:
                    raise RuntimeError(f'supervisorctl {sub} failed: {(r.stdout + r.stderr).strip()} (RPC: {e})')
            return log
