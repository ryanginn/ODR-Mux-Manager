"""Live monitoring: audio levels, input buffer state, encoder status, DLS and slides.

Sources (all optional, each degrades gracefully):
* odr-dabmux management server (ZMQ REQ "values"): per-input peak levels, state and buffers.
  This needs no extra sockets, so it never competes with other tools.
* odr-audioenc --stats sockets (UNIX datagram): only bound when the setting asks for it and
  nothing else owns the socket.
* supervisord XML-RPC: process state of every encoder.
* The DLS text files and slide folders used by odr-padenc.
* On-air decoder (onair.py): what is really inside the mux output.
"""
from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from .project import Project

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.apng'}


def to_db(v):
    if v is None:
        return None
    if v <= 0:
        return -90.0
    return max(-90.0, 20 * math.log10(v / 32767.0))


def read_dls(path: str, limit=2048) -> Optional[dict]:
    """Return {'text', 'dlplus', 'mtime'} for an odr-padenc DLS file."""
    try:
        st = os.stat(path)
        with open(path, 'rb') as f:
            raw = f.read(limit)
    except OSError:
        return None
    text = raw.decode('utf-8', 'replace')
    dlplus = None
    if text.startswith('##### parameters {'):
        head, sep, rest = text.partition('##### }')
        if sep:
            dlplus = head
            text = rest.lstrip('\n')
    return {'text': text.strip(), 'dlplus': bool(dlplus), 'mtime': st.st_mtime}


def list_slides(d: str, limit=200):
    try:
        items = []
        with os.scandir(d) as it:
            for e in it:
                if e.is_file() and Path(e.name).suffix.lower() in IMAGE_EXT and not e.name.startswith('.'):
                    st = e.stat()
                    items.append({'name': e.name, 'size': st.st_size, 'mtime': st.st_mtime})
        items.sort(key=lambda x: x['name'])  # odr-padenc sorts slides by name
        return items[:limit]
    except OSError:
        return None


class DabmuxMgmt:
    def __init__(self, endpoint: str, timeout_ms=800):
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self._ctx = None
        self._sock = None

    def _socket(self):
        import zmq  # optional dependency
        if self._ctx is None:
            self._ctx = zmq.Context.instance()
        if self._sock is None:
            s = self._ctx.socket(zmq.REQ)
            s.setsockopt(zmq.LINGER, 0)
            s.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
            s.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
            s.connect(self.endpoint)
            self._sock = s
        return self._sock

    def request(self, cmd: str):
        try:
            s = self._socket()
            s.send_string(cmd)
            return json.loads(s.recv().decode('utf-8', 'replace'))
        except Exception:
            # a REQ socket is stuck after a timeout: recreate it next time
            if self._sock is not None:
                try:
                    self._sock.close(0)
                except Exception:
                    pass
            self._sock = None
            return None


class StatsListener:
    """Binds odr-audioenc --stats UNIX datagram sockets (only if free)."""

    def __init__(self):
        self.socks: Dict[str, socket.socket] = {}
        self.values: Dict[str, dict] = {}
        self.errors: Dict[str, str] = {}
        self.lock = threading.Lock()

    def ensure(self, paths):
        for p in paths:
            if p in self.socks or not p:
                continue
            if os.path.exists(p):
                # someone may own it: probe. ECONNREFUSED means a stale file we may replace.
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                try:
                    probe.connect(p)
                    self.errors[p] = 'in use by another program'
                    probe.close()
                    continue
                except ConnectionRefusedError:
                    os.unlink(p)
                except OSError as e:
                    self.errors[p] = str(e)
                    probe.close()
                    continue
                probe.close()
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                s.bind(p)
                os.chmod(p, 0o666)
                s.setblocking(False)
                self.socks[p] = s
                self.errors.pop(p, None)
            except OSError as e:
                self.errors[p] = str(e)

    def poll(self):
        for p, s in list(self.socks.items()):
            last = None
            while True:
                try:
                    last = s.recv(4096)
                except BlockingIOError:
                    break
                except OSError:
                    break
            if last:
                try:
                    d = json.loads(last.decode('utf-8', 'replace'))
                    with self.lock:
                        self.values[p] = {'ts': time.time(), **d}
                except ValueError:
                    pass

    def close(self):
        for p, s in self.socks.items():
            try:
                s.close()
                os.unlink(p)
            except OSError:
                pass
        self.socks.clear()


class Monitor:
    def __init__(self, workspace, cfg):
        self.ws = workspace
        self.cfg = cfg
        self.snapshot = {'ts': 0, 'stations': {}, 'dabmux': None, 'supervisor': None}
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._mgmt = None
        self._mgmt_ep = None
        self._stats = StatsListener()
        self._silence_since: Dict[str, float] = {}
        self._project_cache = (0, None)
        self.onair = None

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, name='monitor', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._stats.close()
        if self.onair:
            self.onair.stop()

    def _project(self) -> Optional[Project]:
        ts, p = self._project_cache
        if p is None or time.time() - ts > 5:
            try:
                p = self.ws.live()
            except Exception:
                p = None
            self._project_cache = (time.time(), p)
        return p

    def _endpoint(self, p: Project):
        ep = self.cfg.get('dabmux_mgmt')
        if ep:
            return ep
        port = p.mux.get('general.managementport') if p else None
        return f'tcp://127.0.0.1:{port}' if port else None

    def _run(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.collect()
            except Exception as e:  # never let the monitor die
                with self.lock:
                    self.snapshot['error'] = str(e)
            self._stop.wait(max(0.2, 1.0 - (time.time() - t0)))

    def collect(self):
        p = self._project()
        if p is None:
            return
        snap = {'ts': time.time(), 'stations': {}, 'dabmux': None, 'supervisor': None}
        # dabmux management
        ep = self._endpoint(p)
        values = None
        if ep:
            if ep != self._mgmt_ep:
                self._mgmt = DabmuxMgmt(ep)
                self._mgmt_ep = ep
            vals = self._mgmt.request('values')
            if vals is not None:
                values = vals.get('values', {})
                snap['dabmux'] = {'ok': True, 'endpoint': ep}
            else:
                snap['dabmux'] = {'ok': False, 'endpoint': ep}
        # supervisor
        procs = None
        try:
            procs = self.ws.supervisor().processes()
            snap['supervisor'] = {'ok': True}
        except Exception as e:
            snap['supervisor'] = {'ok': False, 'error': str(e)[:200]}
        # stats sockets
        stations = p.stations()
        if self.cfg.get('levels_source') in ('stats', 'both'):
            self._stats.ensure([(s.get('encoder') or {}).get('stats') for s in stations])
            self._stats.poll()
        now = time.time()
        sil_db = float(self.cfg.get('silence_db', -50))
        sil_secs = float(self.cfg.get('silence_secs', 10))
        for s in stations:
            enc = s.get('encoder') or {}
            d = {'id': s['id'], 'levels': None, 'input_state': None, 'buffer': None, 'audio': None, 'pad': None, 'dmb': None,
                 'dls': None, 'slides': None, 'alerts': []}
            v = (values or {}).get(s['subchannel_uid'])
            if isinstance(v, dict) and isinstance(v.get('inputstat'), dict):
                v = v['inputstat']
            if v:
                d['levels'] = {'l': v.get('peak_left'), 'r': v.get('peak_right'),
                               'l_slow': v.get('peak_left_slow'), 'r_slow': v.get('peak_right_slow'), 'src': 'dabmux'}
                d['input_state'] = v.get('state')
                d['buffer'] = {'min': v.get('min_fill'), 'max': v.get('max_fill'),
                               'underruns': v.get('num_underruns'), 'overruns': v.get('num_overruns')}
            sp = enc.get('stats')
            sv = self._stats.values.get(sp) if sp else None
            if sv and now - sv['ts'] < 5 and (d['levels'] is None or self.cfg.get('levels_source') == 'stats'):
                al = sv.get('audiolevels', {})
                d['levels'] = {'l': to_db(al.get('left')), 'r': to_db(al.get('right')), 'src': 'encoder'}
            if sp and sp in self._stats.errors:
                d['stats_error'] = self._stats.errors[sp]
            if procs is not None:
                for k, name in (('audio', s['audio_program']), ('pad', s['pad_program']), ('dmb', s.get('dmb_program'))):
                    if name:
                        pi = procs.get(name)
                        d[k] = {'state': pi['statename'], 'since': pi.get('start'), 'description': pi.get('description')} \
                            if pi else {'state': 'NOT LOADED'}
            # DLS / slides
            dls = (enc.get('dls_files') or [])
            if dls:
                d['dls'] = read_dls(dls[0])
            elif enc.get('icy_text'):
                d['dls'] = read_dls(enc['icy_text'])
            if enc.get('slide_dir'):
                sl = list_slides(enc['slide_dir'])
                d['slides'] = {'count': len(sl) if sl is not None else None, 'items': (sl or [])[:60],
                               'sleep': enc.get('sleep'), 'missing': sl is None}
            # alerts
            lv = d['levels']
            if lv and lv.get('l') is not None:
                loud = max(lv['l'] or -90, lv['r'] or -90)
                if loud < sil_db:
                    self._silence_since.setdefault(s['id'], now)
                    if now - self._silence_since[s['id']] >= sil_secs:
                        d['alerts'].append({'sev': 'error', 'code': 'silence',
                                            'msg': f'Silent for {int(now - self._silence_since[s["id"]])}s'})
                else:
                    self._silence_since.pop(s['id'], None)
            st = (d['input_state'] or '')
            if st.startswith('NoData'):
                d['alerts'].append({'sev': 'error', 'code': 'nodata', 'msg': 'No data reaching odr-dabmux'})
            elif st.startswith('Unstable'):
                d['alerts'].append({'sev': 'warning', 'code': 'unstable', 'msg': 'Input unstable (buffer under/overruns)'})
            for k in ('audio', 'pad', 'dmb'):
                if d[k] and d[k]['state'] not in ('RUNNING',):
                    d['alerts'].append({'sev': 'error' if k in ('audio', 'dmb') else 'warning', 'code': f'{k}-down',
                                        'msg': f'{ {"audio": "Audio", "pad": "PAD", "dmb": "DMB"}[k]} encoder {d[k]["state"].lower()}'})
            if self.onair:
                oa = self.onair.station(s['subchannel_uid'])
                if oa:
                    d['onair'] = oa
            snap['stations'][s['id']] = d
        if self.onair:
            snap['onair'] = self.onair.status()
        with self.lock:
            self.snapshot = snap

    def get(self) -> dict:
        with self.lock:
            return self.snapshot
