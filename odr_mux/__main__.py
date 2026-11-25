"""odr-mux-manager command line: serve the web UI, print the setup token, check a mux folder."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import time


def _setup_token(cfg, create=True):
    path = os.path.join(cfg['state_dir'], 'setup-token')
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        if not create:
            return None
    tok = secrets.token_urlsafe(18)
    os.makedirs(cfg['state_dir'], exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(tok + '\n')
    return tok


def cmd_serve(args):
    from . import config, db
    from .monitor import Monitor
    from .workspace import Workspace
    from .web import create_app
    cfg = config.load(args.config)
    if args.bind:
        cfg['bind'] = args.bind
    if args.port:
        cfg['port'] = args.port
    if args.state_dir:
        cfg['state_dir'] = args.state_dir
    os.makedirs(cfg['state_dir'], exist_ok=True)
    pend = config.startup_pending(cfg)
    if pend and pend.get('reverted'):
        print('network change was not confirmed in time: went back to the previous address', file=sys.stderr)
    elif pend:
        def watchdog():
            while time.time() < pend['deadline']:
                time.sleep(1)
                if not config.pending_network_path(cfg).exists():
                    return
            print('network change not confirmed: reverting', file=sys.stderr)
            config.startup_pending(cfg)  # deadline passed -> reverts config
            os._exit(3)
        threading.Thread(target=watchdog, daemon=True).start()
    db.init(os.path.join(cfg['state_dir'], 'manager.db'))
    if db.q1('SELECT 1 AS x FROM users LIMIT 1') is None:
        tok = _setup_token(cfg)
        host = '127.0.0.1' if cfg['bind'] in ('0.0.0.0', '::') else cfg['bind']
        print(f'First run: open http://{host}:{cfg["port"]}/?token={tok}', file=sys.stderr)
    ws = Workspace(cfg)
    mon = Monitor(ws, cfg)
    if not args.no_monitor:
        mon.start()
        try:
            from .onair import OnAir
            oa = OnAir.from_config(cfg, ws)
            if oa:
                mon.onair = oa
                oa.start()
        except Exception as e:  # on-air decoding is optional
            print(f'on-air decoder disabled: {e}', file=sys.stderr)
    app = create_app(cfg, ws, mon)
    from cheroot import wsgi
    server = wsgi.Server((cfg['bind'], int(cfg['port'])), app, numthreads=16, request_queue_size=64)
    print(f'ODR Mux Manager listening on {cfg["bind"]}:{cfg["port"]}', file=sys.stderr)
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        mon.stop()
        server.stop()


def cmd_setup_token(args):
    from . import config
    cfg = config.load(args.config)
    tok = _setup_token(cfg, create=True)
    print(tok)


def cmd_check(args):
    from .project import Project
    from .checker import check
    p = Project.load(args.folder, args.mux)
    issues = check(p)
    sts = p.stations()
    print(f'{p.mux_path}: {len(sts)} stations, {p.cu_used()}/864 CU')
    for s in sts:
        print(f"  {s['position']:>2} {s['label'] or '?':<18} {s['codec'] or '':<8} {s['bitrate']:>4}k "
              f"{s['protection']:<7} {s['cu']:>3} CU  {s['feed']:<8} {s['ptag'] or '':<4} {s['audio_program'] or ''}")
    for i in issues:
        print(f"{i['severity'].upper():8} {i['message']}")
    return 1 if any(i['severity'] == 'error' for i in issues) else 0


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    # encoder helpers run from supervisor: pass their options straight through
    if raw[:1] == ['dmb-encode']:
        from .dmb import encode_main
        return encode_main(raw[1:])
    ap = argparse.ArgumentParser(prog='odr-mux-manager')
    ap.add_argument('--config', default=None, help='config file (default /etc/odr-mux-manager/config.json)')
    sub = ap.add_subparsers(dest='cmd')
    s = sub.add_parser('serve', help='run the web UI (default)')
    s.add_argument('--bind')
    s.add_argument('--port', type=int)
    s.add_argument('--state-dir')
    s.add_argument('--no-monitor', action='store_true')
    sub.add_parser('setup-token', help='print the first-run setup token')
    c = sub.add_parser('check', help='check a mux folder and print the station list')
    c.add_argument('folder')
    c.add_argument('--mux')
    d = sub.add_parser('dmb-encode', help='(used by supervisor) T-DMB encoder: ffmpeg -> TS -> RS/interleaver -> UDP')
    d.add_argument('rest', nargs=argparse.REMAINDER)
    o = sub.add_parser('dmb-outer', help='apply DMB outer coding (RS 204,188 + interleaver) to a TS on stdin')
    o.add_argument('--udp', help='send to host:port instead of stdout')
    args = ap.parse_args(argv)
    if args.cmd in (None, 'serve'):
        if args.cmd is None:
            args = ap.parse_args(['serve'] + (argv or sys.argv[1:]))
        return cmd_serve(args)
    if args.cmd == 'setup-token':
        return cmd_setup_token(args)
    if args.cmd == 'check':
        return cmd_check(args)
    if args.cmd == 'dmb-encode':
        from .dmb import encode_main
        return encode_main(args.rest)
    if args.cmd == 'dmb-outer':
        from .dmb import outer_main
        return outer_main(args.udp)


if __name__ == '__main__':
    sys.exit(main() or 0)
