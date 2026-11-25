"""Draft handling, diffs, Apply (with backups) and rollback.

The *live* project is what is on disk. Edits go to a *draft* (serialised file texts plus pending
filesystem operations) kept in the state dir, so several editors share one set of pending
changes and a restart doesn't lose them. Apply writes the draft to disk.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional

from .config import atomic_write
from .project import Project
from .secrets import mask_text
from .supervisor_rpc import Supervisor


def _hash_texts(texts: dict) -> str:
    h = hashlib.sha256()
    h.update(texts['mux'].encode('utf-8', 'surrogateescape'))
    for k in sorted(texts['sups']):
        h.update(k.encode())
        h.update(texts['sups'][k].encode('utf-8', 'surrogateescape'))
    return h.hexdigest()


class Workspace:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.state_dir = Path(cfg['state_dir'])
        self.draft_path = self.state_dir / 'draft.json'
        self.backup_dir = self.state_dir / 'backups'
        self._draft = None
        self._load_draft()

    # ---------------------------------------------------------------- config
    @property
    def configured(self) -> bool:
        return bool(self.cfg.get('project_root') and self.cfg.get('mux_path'))

    def settings(self) -> dict:
        return {'encoder_user': self.cfg.get('encoder_user'), 'stats_dir': self.cfg.get('stats_dir', '/var/tmp')}

    def live(self) -> Project:
        if not self.configured:
            raise RuntimeError('no mux folder has been imported yet')
        return Project.load(self.cfg['project_root'], self.cfg['mux_path'], self.cfg.get('supervisor_paths') or [],
                            settings=self.settings())

    def supervisor(self) -> Supervisor:
        return Supervisor(self.cfg.get('supervisor_socket', '/var/run/supervisor.sock'),
                          self.cfg.get('supervisorctl', 'supervisorctl'), self.cfg.get('supervisor_conf'),
                          use_sudo=self.cfg.get('supervisor_sudo') or 'auto',
                          restart_cmd=self.cfg.get('supervisor_restart_cmd') or 'sudo -n systemctl restart supervisor')

    # ---------------------------------------------------------------- draft
    def _load_draft(self):
        try:
            self._draft = json.loads(self.draft_path.read_text())
        except (FileNotFoundError, ValueError):
            self._draft = None

    def _save_draft(self):
        if self._draft is None:
            self.draft_path.unlink(missing_ok=True)
        else:
            atomic_write(self.draft_path, json.dumps(self._draft), mode=0o600)

    def has_draft(self) -> bool:
        return self._draft is not None

    def draft(self) -> Project:
        """The project as it will be after Apply (live + pending edits)."""
        with self.lock:
            if self._draft is None:
                return self.live()
            return Project.from_texts(self.cfg['project_root'], self.cfg['mux_path'], self._draft['texts'],
                                      settings=self.settings())

    def edit(self, fn, user: str = '', summary: str = ''):
        """Run fn(project) on the draft and store the result. fn returns fs ops (list) or a dict with 'fs'."""
        with self.lock:
            live = self.live() if self._draft is None else None
            base_texts = live.texts() if live else None
            p = live or self.draft()
            res = fn(p)
            fs = res if isinstance(res, list) else (res or {}).get('fs', []) if isinstance(res, dict) else []
            texts = p.texts()
            if self._draft is None:
                self._draft = {'base': _hash_texts(base_texts), 'texts': texts, 'fs': [], 'log': [],
                               'started': time.time()}
            self._draft['texts'] = texts
            self._draft['fs'] = self._draft.get('fs', []) + list(fs or [])
            self._draft['log'].append({'ts': time.time(), 'user': user, 'summary': summary})
            # drop the draft when it ended up identical to the live files and has no fs ops
            if not self._draft['fs'] and self._is_noop(texts):
                self._draft = None
            self._save_draft()
            return res

    def _is_noop(self, texts) -> bool:
        try:
            live = self.live().texts()
        except Exception:
            return False
        return live['mux'] == texts['mux'] and live['sups'] == texts['sups'] and not texts.get('parked')

    def discard(self):
        with self.lock:
            self._draft = None
            self._save_draft()

    def draft_info(self) -> dict:
        if self._draft is None:
            return {'pending': False}
        stale = False
        try:
            stale = _hash_texts(self.live().texts()) != self._draft['base']
        except Exception:
            pass
        return {'pending': True, 'since': self._draft.get('started'), 'log': self._draft.get('log', [])[-50:],
                'fs': self._draft.get('fs', []), 'stale': stale}

    def diff(self, mask=True) -> List[dict]:
        live = self.live().texts()
        d = self.draft().texts()
        out = []
        files = [(str(self.cfg['mux_path']), live['mux'], d['mux'])]
        for path in sorted(set(live['sups']) | set(d['sups'])):
            files.append((path, live['sups'].get(path, ''), d['sups'].get(path, '')))
        for path, a, b in files:
            if a == b:
                continue
            udiff = ''.join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), path, path, n=3))
            if mask:
                udiff = mask_text(udiff)
            out.append({'path': path, 'diff': udiff, 'new': not a})
        return out

    # ---------------------------------------------------------------- apply
    def apply(self, user: str = '', dry_run: bool = False) -> dict:
        with self.lock:
            if self._draft is None:
                return {'ok': True, 'message': 'Nothing to apply.', 'log': []}
            live = self.live()
            draft = self.draft()
            lt, dt = live.texts(), draft.texts()
            stamp = time.strftime('%Y%m%d-%H%M%S')
            bdir = self.backup_dir / stamp
            n = 1
            while bdir.exists():
                n += 1
                bdir = self.backup_dir / f'{stamp}-{n}'
            log = []
            # 1. backup
            bdir.mkdir(parents=True)
            manifest = {'ts': time.time(), 'user': user, 'files': {}, 'fs': self._draft.get('fs', []),
                        'undo': []}
            files = {str(self.cfg['mux_path']): (lt['mux'], dt['mux'])}
            for p in set(lt['sups']) | set(dt['sups']):
                files[p] = (lt['sups'].get(p), dt['sups'].get(p))
            for i, (path, (old, new)) in enumerate(sorted(files.items())):
                name = f'{i:02d}-{Path(path).name}'
                if old is not None:
                    (bdir / name).write_text(old, encoding='utf-8', errors='surrogateescape')
                manifest['files'][path] = {'backup': name if old is not None else None, 'existed': old is not None}
            os.chmod(bdir, 0o700)
            log.append(f'backup saved as {bdir.name}')
            if dry_run:
                return {'ok': True, 'backup': bdir.name, 'log': log, 'dry_run': True}
            # 2. filesystem ops (folders), recording undo steps
            try:
                for op in self._draft.get('fs', []):
                    log += run_fs_op(op, manifest['undo'])
            except Exception as e:
                undo(manifest['undo'])
                (bdir / 'manifest.json').write_text(json.dumps(manifest, indent=1))
                return {'ok': False, 'message': f'Folder changes failed and were undone: {e}', 'log': log}
            # 3. write files
            written = []
            for path, (old, new) in files.items():
                if old == new:
                    continue
                if new is None:
                    continue
                atomic_write(path, new)
                written.append(path)
                log.append(f'wrote {path}')
            (bdir / 'manifest.json').write_text(json.dumps(manifest, indent=1))
            mux_changed = lt['mux'] != dt['mux']
            sup_changed = lt['sups'] != dt['sups']
            stop_ops = [op['name'] for op in self._draft.get('fs', []) if op.get('op') == 'stop_program']
            self._draft = None
            self._save_draft()
            # 4. reload processes
            ok, msg = True, 'Applied.'
            if self.cfg.get('run_commands', True):
                try:
                    log += self.reload(sup_changed, mux_changed, live)
                except Exception as e:
                    ok, msg = False, f'Files were written, but reloading failed: {e}'
                    log.append(msg)
            else:
                log.append('command execution is disabled in settings: restart encoders/odr-dabmux yourself')
            return {'ok': ok, 'message': msg, 'backup': bdir.name, 'log': log, 'stopped': stop_ops,
                    'mux_changed': mux_changed}

    def reload(self, sup_changed: bool, mux_changed: bool, live: Optional[Project] = None) -> List[str]:
        log = []
        if self.cfg.get('supervisor_reload') == 'restart':
            # restart the whole supervisor service: every encoder (and odr-dabmux, if supervisor runs it)
            # starts fresh with the new config
            if sup_changed or mux_changed:
                log += self.supervisor().restart_service()
                p = live or self.live()
                if mux_changed and p.dabmux_program() is None:
                    log += self.restart_dabmux(p)
            return log
        if sup_changed:
            log += self.supervisor().update()
        if mux_changed:
            log += self.restart_dabmux(live)
        return log

    def restart_dabmux(self, project: Optional[Project] = None) -> List[str]:
        how = self.cfg.get('dabmux_restart', 'auto') or 'auto'
        if how == 'auto':
            p = project or self.live()
            prog = p.dabmux_program()
            if prog is None:
                return ['odr-dabmux is not run by these supervisor files: restart it yourself '
                        '(or pick how in Settings → Control).']
            how = 'supervisor:' + prog.program
        if how == 'none':
            return ['odr-dabmux restart is disabled in settings: restart it yourself.']
        kind, _, arg = how.partition(':')
        if kind == 'supervisor':
            self.supervisor().restart(arg)
            return [f'restarted {arg} (supervisor)']
        if kind == 'systemd':
            r = subprocess.run(['sudo', '-n', 'systemctl', 'restart', arg], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RuntimeError(f'systemctl restart {arg}: {(r.stderr or r.stdout).strip()}')
            return [f'restarted {arg} (systemd)']
        if kind == 'command':
            r = subprocess.run(arg, shell=True, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(f'{arg}: {(r.stderr or r.stdout).strip()}')
            return [f'ran {arg}']
        raise RuntimeError(f'unknown dabmux_restart setting {how}')

    # ---------------------------------------------------------------- backups
    def backups(self) -> List[dict]:
        out = []
        if not self.backup_dir.exists():
            return out
        for d in sorted(self.backup_dir.iterdir(), reverse=True):
            m = d / 'manifest.json'
            try:
                man = json.loads(m.read_text())
            except (FileNotFoundError, ValueError):
                continue
            out.append({'id': d.name, 'ts': man.get('ts'), 'user': man.get('user'), 'files': list(man['files']),
                        'fs': man.get('fs', []), 'rolled_back': man.get('rolled_back')})
        return out

    def rollback(self, backup_id: str, user: str = '') -> dict:
        with self.lock:
            bdir = self.backup_dir / backup_id
            if '/' in backup_id or not (bdir / 'manifest.json').exists():
                raise FileNotFoundError('no such backup')
            man = json.loads((bdir / 'manifest.json').read_text())
            log = []
            live_before = self.live().texts() if self.configured else None
            undo(man.get('undo', []), log)
            for path, info in man['files'].items():
                if info.get('existed') and info.get('backup'):
                    atomic_write(path, (bdir / info['backup']).read_text(encoding='utf-8', errors='surrogateescape'))
                    log.append(f'restored {path}')
                elif not info.get('existed') and Path(path).exists():
                    Path(path).unlink()
                    log.append(f'removed {path} (did not exist before)')
            man['rolled_back'] = {'ts': time.time(), 'user': user}
            (bdir / 'manifest.json').write_text(json.dumps(man, indent=1))
            self._draft = None
            self._save_draft()
            ok, msg = True, f'Rolled back to the state before {backup_id}.'
            if self.cfg.get('run_commands', True):
                try:
                    after = self.live().texts()
                    log += self.reload(live_before is None or after['sups'] != live_before['sups'],
                                       live_before is None or after['mux'] != live_before['mux'])
                except Exception as e:
                    ok, msg = False, f'Files restored, but reloading failed: {e}'
            return {'ok': ok, 'message': msg, 'log': log}


# -------------------------------------------------------------------- filesystem operations
def run_fs_op(op: dict, undo_log: list) -> List[str]:
    kind = op.get('op')
    log = []
    if kind == 'mkdir':
        p = Path(op['path'])
        if not p.exists():
            p.mkdir(parents=True)
            undo_log.append({'op': 'rmdir', 'path': str(p)})
            log.append(f'created {p}')
    elif kind == 'touch':
        p = Path(op['path'])
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
            undo_log.append({'op': 'rm', 'path': str(p)})
            log.append(f'created {p}')
    elif kind == 'archive':
        src = Path(op['path'])
        if src.exists():
            dst = Path(op['to'])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            undo_log.append({'op': 'move', 'from': str(dst), 'to': str(src)})
            log.append(f'archived {src} → {dst}')
        else:
            log.append(f'{src} does not exist, nothing to archive')
    elif kind == 'move_many':
        moves = [(Path(m['from']), Path(m['to'])) for m in op['moves']]
        stamp = f'.mmtmp-{int(time.time())}-{os.getpid()}'
        staged = []
        # phase 1: everything to a temporary name, so P10->P09 and P09->P08 never collide
        for src, dst in moves:
            if src.exists():
                tmp = src.with_name(src.name + stamp)
                src.rename(tmp)
                undo_log.append({'op': 'move', 'from': str(tmp), 'to': str(src)})
                staged.append((tmp, dst, src))
            else:
                log.append(f'{src} does not exist, skipped')
        for tmp, dst, src in staged:
            if dst.exists():
                raise RuntimeError(f'{dst} already exists; not overwriting it')
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(dst)
            undo_log.append({'op': 'move', 'from': str(dst), 'to': str(tmp)})
            log.append(f'moved {src} → {dst}')
    elif kind == 'mkfifo':
        p = Path(op['path'])
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            os.mkfifo(p, 0o664)
            undo_log.append({'op': 'rm', 'path': str(p)})
            log.append(f'created FIFO {p}')
    elif kind == 'stop_program':
        log.append(f'{op["name"]} will be stopped by supervisor update')
    elif kind == 'write':
        p = Path(op['path'])
        old = p.read_bytes() if p.exists() else None
        atomic_write(p, op['text'])
        undo_log.append({'op': 'restore', 'path': str(p), 'text': None if old is None else old.decode('utf-8', 'surrogateescape')})
        log.append(f'wrote {p}')
    return log


def undo(steps: list, log: Optional[list] = None):
    log = log if log is not None else []
    for st in reversed(steps):
        try:
            if st['op'] == 'move':
                if Path(st['from']).exists() and not Path(st['to']).exists():
                    Path(st['to']).parent.mkdir(parents=True, exist_ok=True)
                    Path(st['from']).rename(st['to'])
                    log.append(f'moved {st["from"]} back to {st["to"]}')
            elif st['op'] == 'rmdir':
                try:
                    Path(st['path']).rmdir()
                    log.append(f'removed {st["path"]}')
                except OSError:
                    log.append(f'kept {st["path"]} (not empty)')
            elif st['op'] == 'rm':
                p = Path(st['path'])
                if p.exists() and p.stat().st_size == 0:
                    p.unlink()
            elif st['op'] == 'restore':
                if st['text'] is None:
                    Path(st['path']).unlink(missing_ok=True)
                else:
                    atomic_write(st['path'], st['text'])
        except OSError as e:
            log.append(f'undo step {st} failed: {e}')
    return log
