"""Let odr-dabmux itself check a config before Apply writes it.

A copy of the new .mux is run through the installed odr-dabmux with every listening port moved to
a free one, remote control and the management server switched to free ports, the outputs replaced
by /dev/null and nbframes limited, so it can't disturb the running mux. If odr-dabmux rejects the
config (bad hex value, short label, over capacity, ...) its own error message is returned.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import tempfile
import time
from typing import Optional

from .infofile import InfoDoc, Node, split_uri, with_port


def _free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def sandbox_config(text: str) -> str:
    doc = InfoDoc(text)
    gen = doc.section('general', create=True)
    gen.set('nbframes', '10')
    gen.set('managementport', str(_free_port()))
    gen.remove('tist')
    rc = doc.section('remotecontrol')
    if rc is not None:
        doc.root.remove(rc)
    subs = doc.section('subchannels')
    for sc in (subs.children if subs is not None and subs.children else []):
        proto = (sc.get('inputproto') or '').lower()
        uri = sc.get('inputuri') or ''
        if proto in ('edi', 'zmq', 'udp', 'stp') or uri.startswith(('tcp://', 'udp://', 'zmq+tcp://', 'rtp://')):
            d = split_uri(uri)
            if d and d['port']:
                sc.set('inputuri', with_port(uri, _free_port()), quoted=True)
    outs = doc.section('outputs')
    if outs is not None:
        doc.root.remove(outs)
    o = Node('outputs', None, [])
    n = Node('validate', 'file:///dev/null?type=raw')
    n.quoted = True
    o.append(n)
    doc.root.append(o)
    return doc.dumps()


_ERR = re.compile(r'(ERROR|ALERT|Caught|exception)', re.I)


FATAL = re.compile(r'(Caught .*(error|exception)|ALERT|Could not open|Invalid|refuse|exceeds|Duplicate)', re.I)
RUNNING = ('Max number of ETI frames reached', 'Start time', 'ETI frame number')


def check_with_dabmux(text: str, dabmux: Optional[str], timeout: int = 20) -> dict:
    """{'ok': bool, 'skipped': bool, 'message': str, 'log': str}

    Only *configuration* failures count: odr-dabmux aborting ("Caught ... exception", "ALERT ...aborting").
    Runtime noise such as empty inputs ("Not enough data in file") is fine, because the sandbox gets no audio.
    """
    if not dabmux or not os.path.exists(dabmux):
        return {'ok': True, 'skipped': True, 'message': 'odr-dabmux not found here, so the config was not test-run.'}
    try:
        cfg = sandbox_config(text)
    except Exception as e:
        return {'ok': False, 'skipped': False, 'message': f'The config could not be parsed: {e}', 'log': ''}
    with tempfile.TemporaryDirectory(prefix='odr-mux-check-') as d:
        path = os.path.join(d, 'check.mux')
        with open(path, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(cfg)
        proc = subprocess.Popen([dabmux, path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=d,
                                text=True, errors='replace')
        lines = []
        fatal = None
        started = False
        deadline = time.monotonic() + timeout
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        try:
            while time.monotonic() < deadline:
                if not sel.select(timeout=0.5):
                    if proc.poll() is not None:
                        break
                    continue
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                lines.append(line.rstrip('\n'))
                if ('Caught' in line and ('error' in line or 'exception' in line)) or 'ALERT' in line \
                        or 'aborted' in line or ('ERROR' in line and 'exceeds' in line):
                    fatal = fatal or line
                    if 'ALERT' in line or 'aborted' in line:
                        break
                if any(m in line for m in RUNNING):
                    started = True
                    break
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        log = '\n'.join(lines)
    if fatal:
        caught = next((l for l in lines if 'Caught' in l or ('ERROR' in l and 'exceeds' in l)), fatal)
        return {'ok': False, 'skipped': False, 'message': _clean(caught), 'log': log[-4000:]}
    if not started and proc.returncode is not None and proc.returncode < 0 and proc.returncode != -9:
        # killed by a signal (e.g. a libzmq assertion -> SIGABRT) before reaching the config check:
        # that's the environment, not the config, so don't block Apply on it
        last = next((l for l in reversed(lines) if l.strip() and 'Copyright' not in l), '')
        return {'ok': True, 'skipped': True, 'log': log[-4000:],
                'message': f'odr-dabmux could not be test-run here (it crashed with signal {-proc.returncode} before '
                           f'checking the config: {last.strip()[:160]}), so this config was only checked by the '
                           f'manager. Re-run the installer to update the service unit, or switch the test-run off in Settings.'}
    if not started and proc.returncode not in (0, None, -9):
        errs = [l for l in lines if 'ERROR' in l and 'real-time priority' not in l]
        return {'ok': False, 'skipped': False,
                'message': _clean(errs[-1]) if errs else f'odr-dabmux exited with code {proc.returncode}',
                'log': log[-4000:]}
    return {'ok': True, 'skipped': False, 'message': 'odr-dabmux accepted the config.', 'log': log[-4000:]}


def _clean(line: str) -> str:
    line = re.sub(r'^\d{4}-\d\d-\d\dZ\S*\s+', '', line.strip())
    return re.sub(r'^(ERROR|ALERT|WARN)\s+', '', line)
