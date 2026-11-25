"""JSON API."""
from __future__ import annotations

import os
import re
import stat
import time
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, make_response, request, send_file

from .. import __version__, capabilities, checker, config as cfgmod, db, ops, renumber, security
from ..cu import TOTAL_CU, UEP_TABLE, MP2_BITRATES_48K, MP2_BITRATES_24K
from ..encoders import Args
from ..infofile import parse_int
from ..project import Project, merge_json, find_mux_files, find_supervisor_files
from ..secrets import mask, has_secret
from . import (ApiError, COOKIE, ROLES, allowed_stations, audit, client_ip, current_user, is_editor, is_viewer,
               json_body, require)

bp = Blueprint('api', __name__)
USERNAME_RE = re.compile(r'^[A-Za-z0-9._@-]{3,64}$')
SECTIONS = {'linking', 'frequency_information', 'other-services', 'outputs', 'general', 'remotecontrol',
            'ensemble.announcements'}


def cfg():
    return current_app.config['CFG']


def ws():
    return current_app.config['WS']


def mon():
    return current_app.config['MON']


def _str(data, key, maxlen, required=False, label=None):
    v = data.get(key, '')
    if v is None:
        v = ''
    if not isinstance(v, str):
        raise ApiError(f'{label or key} must be text.')
    v = v.strip()
    if required and not v:
        raise ApiError(f'{label or key} is required.')
    if len(v) > maxlen:
        raise ApiError(f'{label or key} is too long (max {maxlen}).')
    return v


def _need_project():
    if not ws().configured:
        raise ApiError('No mux has been imported yet. An administrator must pick the mux folder first.', 409)


def _edit(fn, summary):
    _need_project()
    try:
        res = ws().edit(fn, current_user()['username'], summary)
    except (ops.OpError, renumber.RenumberError, ValueError) as e:
        raise ApiError(str(e))
    audit('edit', summary)
    return res


# ===================================================================== auth
def _set_cookie(resp, token, hours):
    resp.set_cookie(COOKIE, token, max_age=int(hours * 3600), httponly=True, samesite='Strict',
                    secure=request.is_secure, path='/')


def _user_public(u):
    return {'id': u['id'], 'username': u['username'], 'display_name': u['display_name'], 'role': u['role'],
            'must_change_pw': bool(u['must_change_pw'])}


def setup_token_path():
    return os.path.join(cfg()['state_dir'], 'setup-token')


def users_exist():
    return db.q1('SELECT 1 AS x FROM users LIMIT 1') is not None


def mux_display_name():
    try:
        if ws().configured:
            return ws().live().mux.get('ensemble.label', '') or ''
    except Exception:
        pass
    return ''


@bp.get('/api/state')
def state():
    u = current_user()
    pend = cfgmod.startup_pending(cfg()) if False else None
    return jsonify(version=__version__, setup_required=not users_exist(),
                   user=_user_public(u) if u else None, csrf=u['csrf'] if u else None,
                   configured=ws().configured, mux_name=mux_display_name())


@bp.post('/api/setup')
def setup():
    if not security.setup_limiter.hit(client_ip()):
        raise ApiError('Too many attempts - wait 15 minutes.', 429)
    if users_exist():
        raise ApiError('Setup has already been completed.', 409)
    data = json_body()
    try:
        with open(setup_token_path()) as f:
            expected = f.read().strip()
    except OSError:
        raise ApiError('No setup token found. Run: sudo odr-mux-manager setup-token', 403)
    token = data.get('token', '')
    import hmac
    if not isinstance(token, str) or not expected or not hmac.compare_digest(token.strip(), expected):
        db.audit(None, client_ip(), 'setup.bad_token')
        raise ApiError('Setup token is incorrect.', 403)
    username = _str(data, 'username', 64, True, 'Username')
    if not USERNAME_RE.match(username):
        raise ApiError('Username may contain letters, digits and . _ @ - (3-64 characters).')
    pw = data.get('password', '')
    problem = security.password_problem(pw, username)
    if problem:
        raise ApiError(problem)
    uid = db.x('INSERT INTO users(username, display_name, pw_hash, role, created_at) VALUES (?,?,?,?,?)',
               (username, _str(data, 'display_name', 64) or username, security.hash_password(pw), 'admin', time.time()))
    try:
        os.remove(setup_token_path())
    except OSError:
        pass
    db.audit({'user_id': uid, 'username': username}, client_ip(), 'setup.admin_created', username)
    return _login_response(uid)


def _login_response(uid):
    hours = int(cfg().get('session_hours') or 12)
    token, _ = security.create_session(uid, client_ip(), request.headers.get('User-Agent'), hours)
    db.x('UPDATE users SET last_login = ?, failed_logins = 0, locked_until = 0 WHERE id = ?', (time.time(), uid))
    resp = make_response(jsonify(ok=True))
    _set_cookie(resp, token, hours)
    return resp


@bp.post('/api/login')
def login():
    if not security.login_limiter.hit(client_ip()):
        raise ApiError('Too many login attempts from your address - wait 15 minutes.', 429)
    data = json_body()
    username, password = data.get('username', ''), data.get('password', '')
    if not isinstance(username, str) or not isinstance(password, str) or len(password) > security.MAX_PASSWORD_LEN:
        raise ApiError('Invalid username or password.', 401)
    u = db.q1('SELECT * FROM users WHERE username = ?', (username.strip(),))
    if not u:
        security.dummy_verify(password)
        db.audit(None, client_ip(), 'login.failed', username[:64])
        raise ApiError('Invalid username or password.', 401)
    if u['locked_until'] > time.time():
        security.dummy_verify(password)
        raise ApiError('Account temporarily locked after repeated failures - try again later.', 429)
    if not security.verify_password(password, u['pw_hash']) or u['disabled']:
        fails = u['failed_logins'] + 1
        locked = time.time() + security.LOCKOUT_SECONDS if fails >= security.LOCKOUT_THRESHOLD else 0
        db.x('UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?', (0 if locked else fails, locked, u['id']))
        db.audit({'user_id': u['id'], 'username': u['username']}, client_ip(), 'login.failed', u['username'])
        raise ApiError('Invalid username or password.', 401)
    db.audit({'user_id': u['id'], 'username': u['username']}, client_ip(), 'login', u['username'])
    return _login_response(u['id'])


@bp.post('/api/logout')
def logout():
    if g.session_token:
        security.destroy_session(g.session_token)
    resp = make_response(jsonify(ok=True))
    resp.delete_cookie(COOKIE, path='/')
    return resp


@bp.post('/api/account/password')
@require()
def change_password():
    data = json_body()
    u = db.q1('SELECT * FROM users WHERE id = ?', (current_user()['id'],))
    if not security.verify_password(data.get('current', '') or '', u['pw_hash']):
        raise ApiError('Current password is incorrect.', 403)
    problem = security.password_problem(data.get('new', ''), u['username'])
    if problem:
        raise ApiError(problem)
    if data['new'] == data.get('current'):
        raise ApiError('New password must differ from the current one.')
    db.x('UPDATE users SET pw_hash = ?, must_change_pw = 0 WHERE id = ?', (security.hash_password(data['new']), u['id']))
    security.destroy_user_sessions(u['id'], except_token=g.session_token)
    audit('account.password_changed', u['username'])
    return jsonify(ok=True)


@bp.patch('/api/account')
@require()
def update_account():
    data = json_body()
    db.x('UPDATE users SET display_name = ? WHERE id = ?', (_str(data, 'display_name', 64), current_user()['id']))
    return jsonify(ok=True)


# ===================================================================== public views
def _station_public(s: dict, u, reveal=False) -> dict:
    """Mask secrets; strip technical detail for station-scoped users."""
    s = dict(s)
    enc = dict(s['encoder']) if s.get('encoder') else None
    if enc:
        enc['input_has_secret'] = has_secret(enc.get('input') or '')
        if not reveal:
            enc['input'] = mask(enc.get('input'))
            enc['outputs'] = [{**o, 'uri': mask(o['uri'])} for o in enc.get('outputs', [])]
        s['encoder'] = enc
    if not reveal and s.get('inputuri'):
        s['inputuri'] = mask(s['inputuri'])
    if u['role'] == 'station':
        return {k: s.get(k) for k in ('id', 'label', 'shortlabel', 'kind', 'codec', 'bitrate', 'position', 'feed',
                                      'audio_program', 'pad_program')} | {
            'encoder': {k: (enc or {}).get(k) for k in ('codec', 'sleep')} if enc else None}
    return s


def _filter(stations, u):
    allowed = allowed_stations(u)
    if allowed is None:
        return stations
    return [s for s in stations if s['id'] in allowed]


@bp.get('/api/overview')
@require()
def overview():
    """Main page data: ensemble, CU (live + draft), stations, draft state, issue counts."""
    u = current_user()
    if not ws().configured:
        return jsonify(configured=False)
    live = ws().live()
    draft = ws().draft() if ws().has_draft() else live
    sts = _filter(live.stations(), u)
    out = {'configured': True, 'ensemble': {k: live.ensemble().get(k) for k in ('label', 'shortlabel', 'id', 'ecc')},
           'cu_total': TOTAL_CU, 'cu_used': live.cu_used(), 'cu_draft': draft.cu_used(),
           'stations': [_station_public(s, u) for s in sts]}
    if is_viewer(u):
        out['cu_segments'] = [{'id': s['id'], 'label': s['label'], 'cu': s['cu'], 'kind': s['kind'],
                               'codec': s['codec'], 'protection': s['protection'], 'bitrate': s['bitrate']}
                              for s in live.stations()]
        out['cu_segments_draft'] = [{'id': s['id'], 'label': s['label'], 'cu': s['cu'], 'kind': s['kind']}
                                    for s in draft.stations()]
        out['draft'] = ws().draft_info()
        issues = checker.check(draft, check_fs=cfg().get('check_fs', True), manager_port=cfg().get('port'))
        out['issues'] = {k: sum(1 for i in issues if i['severity'] == k) for k in ('error', 'warning', 'info')}
        out['mux_path'] = str(live.mux_path)
    return jsonify(out)


@bp.get('/api/monitor')
@require()
def monitor_snapshot():
    u = current_user()
    snap = mon().get() if mon() else {'stations': {}}
    allowed = allowed_stations(u)
    st = {k: v for k, v in snap.get('stations', {}).items() if allowed is None or k in allowed}
    out = {'ts': snap.get('ts'), 'stations': st}
    if is_viewer(u):
        out['dabmux'] = snap.get('dabmux')
        out['supervisor'] = snap.get('supervisor')
        out['onair'] = snap.get('onair')
    if u['role'] == 'station':
        for v in st.values():
            v.pop('stats_error', None)
            v.pop('buffer', None)
    return jsonify(out)


def _station_live(sid):
    _need_project()
    u = current_user()
    allowed = allowed_stations(u)
    if allowed is not None and sid not in allowed:
        raise ApiError('You do not have access to this station.', 403)
    s = ws().live().station(sid)
    if not s:
        raise ApiError('Station not found.', 404)
    return s


@bp.get('/api/monitor/<sid>/slide/<path:name>')
@require()
def monitor_slide(sid, name):
    s = _station_live(sid)
    d = (s.get('encoder') or {}).get('slide_dir')
    if not d or '/' in name or name.startswith('.'):
        raise ApiError('Not found.', 404)
    p = Path(d) / name
    if not p.is_file():
        raise ApiError('Not found.', 404)
    return send_file(p, max_age=5)


@bp.get('/api/monitor/<sid>/onair-slide')
@require()
def monitor_onair_slide(sid):
    s = _station_live(sid)
    m = mon()
    if not m or not m.onair:
        raise ApiError('On-air decoding is off.', 404)
    img = m.onair.slide_image(s['subchannel_uid'])
    if not img:
        raise ApiError('No slide decoded yet.', 404)
    data, mime = img
    resp = make_response(data)
    resp.headers['Content-Type'] = mime
    return resp


@bp.get('/api/monitor/<sid>/log')
@require('viewer')
def monitor_log(sid):
    s = _station_live(sid)
    which = request.args.get('which', 'audio')
    name = s['audio_program'] if which == 'audio' else s['pad_program']
    if not name:
        raise ApiError('No such encoder.', 404)
    try:
        text = ws().supervisor().tail(name, 12000)
    except Exception as e:
        raise ApiError(f'Cannot read the log from supervisor: {e}', 502)
    return jsonify(text=mask(text))


@bp.post('/api/monitor/<sid>/restart')
@require('editor')
def monitor_restart(sid):
    s = _station_live(sid)
    which = json_body().get('which', 'audio')
    names = {'audio': [s['audio_program']], 'pad': [s['pad_program']],
             'both': [s['pad_program'], s['audio_program']]}.get(which, [])
    names = [n for n in names if n]
    if not names:
        raise ApiError('No such encoder.', 404)
    try:
        for n in names:
            ws().supervisor().restart(n)
    except Exception as e:
        raise ApiError(f'Restart failed: {e}', 502)
    audit('encoder.restart', ','.join(names))
    return jsonify(ok=True)


# ===================================================================== stations (draft)
@bp.get('/api/stations')
@require('viewer')
def list_stations():
    _need_project()
    p = ws().draft()
    reveal = current_user()['role'] == 'admin' and request.args.get('reveal') == '1'
    return jsonify(stations=[_station_public(s, current_user(), reveal) for s in p.stations()],
                   orphans=p.orphan_services(), cu_used=p.cu_used(), cu_total=TOTAL_CU,
                   draft=ws().draft_info())


@bp.get('/api/stations/<sid>')
@require('viewer')
def get_station(sid):
    _need_project()
    p = ws().draft()
    s = p.station(sid)
    if not s:
        raise ApiError('Station not found.', 404)
    reveal = current_user()['role'] == 'admin' and request.args.get('reveal') == '1'
    if reveal:
        audit('secret.reveal', sid)
    issues = [i for i in checker.check(p, manager_port=cfg().get('port'))
              if i['ref'].get('station') == sid or i['ref'].get('service') == s['service_uid']
              or i['ref'].get('subchannel') == s['subchannel_uid']
              or i['ref'].get('program') in (s['audio_program'], s['pad_program'])]
    pub = _station_public(s, current_user(), reveal)
    pub['issues'] = issues
    pub['services'] = [{'uid': x.key, 'label': x.get('label'), 'id': x.get('id')} for x in p.services()]
    return jsonify(pub)


@bp.put('/api/stations/<sid>')
@require('editor')
def put_station(sid):
    data = json_body()
    _edit(lambda p: ops.update_station(p, sid, data), f'edit station {sid}')
    return get_station(data.get('service', {}).get('id') and _norm_sid(data['service']['id']) or sid)


def _norm_sid(v):
    n = parse_int(v)
    if n is None:
        return v
    return f'{n:04X}' if n <= 0xFFFF else f'{n:08X}'


@bp.post('/api/stations')
@require('editor')
def add_station():
    data = json_body()
    res = _edit(lambda p: ops.add_station(p, data), f'add station {data.get("label")}')
    return jsonify(ok=True, station=res['station'])


@bp.post('/api/stations/<sid>/feed')
@require('editor')
def set_feed(sid):
    data = json_body()
    feed = data.get('feed')
    _edit(lambda p: ops.set_feed(p, sid, feed, data.get('opts') or {}), f'station {sid}: feed → {feed}')
    return jsonify(ok=True)


@bp.post('/api/stations/plan')
@require('editor')
def stations_plan():
    _need_project()
    data = json_body()
    try:
        pl = renumber.plan(ws().draft(), data.get('order') or [], data.get('remove') or [], data.get('mode', 'renumber'))
    except renumber.RenumberError as e:
        raise ApiError(str(e))
    return jsonify(pl)


@bp.post('/api/stations/reorder')
@require('editor')
def stations_reorder():
    data = json_body()
    rm = data.get('remove') or []
    res = _edit(lambda p: renumber.apply(p, data.get('order') or [], rm, data.get('mode', 'renumber')),
                ('remove ' + ', '.join(rm) + ' and ' if rm else '') + f'reorder ({data.get("mode", "renumber")})')
    return jsonify(ok=True, plan=res)


@bp.post('/api/stations/<sid>/components')
@require('editor')
def add_component(sid):
    """Add a secondary component: this station's subchannel shown under another service."""
    data = json_body()

    def fn(p):
        s = p.station(sid)
        if not s:
            raise ops.OpError('Station not found.')
        svc = data.get('service')
        if not p.service(svc):
            raise ops.OpError('Unknown service.')
        uid = s['component_uid'] + '-sub' if s['component_uid'] else ops.next_uid([c.key for c in p.components()], 'comp-')
        n = 2
        base = uid
        while p.component(uid):
            uid = f'{base}{n}'
            n += 1
        from ..infofile import Node
        c = Node(uid, None, [])
        lab = Node('label', data.get('label') or s['label'])
        lab.quoted = True
        c.append(lab)
        sl = Node('shortlabel', data.get('shortlabel') or (data.get('label') or s['label'])[:8])
        sl.quoted = True
        c.append(sl)
        c.append(Node('service', svc))
        c.append(Node('subchannel', s['subchannel_uid']))
        ops.set_user_apps(c, data.get('user_apps') or ['slideshow'])
        comps = p.sec('components', create=True)
        prim = p.component(s['component_uid']) if s['component_uid'] else None
        comps.append(c, comps.children.index(prim) + 1 if prim is not None else None)
        return []
    _edit(fn, f'add secondary component to {sid}')
    return jsonify(ok=True)


@bp.put('/api/components/<uid>')
@require('editor')
def put_component(uid):
    data = json_body()

    def fn(p):
        c = p.component(uid)
        if c is None:
            raise ops.OpError('Component not found.')
        ops.update_fields(c, data, ['label', 'shortlabel', 'service', 'type', 'figtype', 'address', 'datagroup'])
        if 'user_apps' in data:
            ops.set_user_apps(c, data['user_apps'])
        return []
    _edit(fn, f'edit component {uid}')
    return jsonify(ok=True)


@bp.delete('/api/components/<uid>')
@require('editor')
def delete_component(uid):
    def fn(p):
        comps = p.sec('components')
        if comps is None or comps.child(uid) is None:
            raise ops.OpError('Component not found.')
        comps.remove(uid)
        return []
    _edit(fn, f'remove component {uid}')
    return jsonify(ok=True)


# ===================================================================== ensemble & sections
@bp.get('/api/ensemble')
@require('viewer')
def get_ensemble():
    _need_project()
    p = ws().draft()
    return jsonify(p.ensemble())


@bp.put('/api/ensemble')
@require('editor')
def put_ensemble():
    data = json_body()
    _edit(lambda p: ops.set_ensemble(p, data), 'edit ensemble')
    return get_ensemble()


def _section_node(p, name, create=False):
    if name == 'ensemble.announcements':
        ens = p.sec('ensemble', create=create)
        return ens.block('announcements', create=create) if ens is not None else None
    return p.sec(name, create=create)


@bp.get('/api/section/<name>')
@require('viewer')
def get_section(name):
    _need_project()
    if name not in SECTIONS:
        raise ApiError('Unknown section.', 404)
    n = _section_node(ws().draft(), name)
    return jsonify(n.to_dict() if n is not None and n.children is not None else {})


@bp.put('/api/section/<name>')
@require('editor')
def put_section(name):
    if name not in SECTIONS:
        raise ApiError('Unknown section.', 404)
    data = json_body()

    def fn(p):
        n = _section_node(p, name, create=True)
        merge_json(n, data)
        if not n.children:
            parent = n.parent
            if parent is not None:
                parent.remove(n)
        return []
    _edit(fn, f'edit {name}')
    return get_section(name)


# ===================================================================== data services
@bp.post('/api/data-services')
@require('editor')
def add_data_service():
    data = json_body()
    from ..dataservices import add_data_service as add
    res = _edit(lambda p: add(p, data), f'add data service {data.get("label")}')
    return jsonify(ok=True, station=res['station'])


@bp.put('/api/data-services/<sid>')
@require('editor')
def put_data_service(sid):
    data = json_body()
    from ..dataservices import update_data_service as upd
    _edit(lambda p: upd(p, sid, data), f'edit data service {sid}')
    return jsonify(ok=True)


@bp.delete('/api/stations/<sid>')
@require('editor')
def delete_station(sid):
    """Remove a single station *without* renumbering others (data services, DMB)."""
    def fn(p):
        s = p.station(sid)
        if not s:
            raise ops.OpError('Station not found.')
        fs = []
        renumber._remove_station(p, s, fs, time.strftime('%Y%m%d-%H%M%S'))
        return fs
    _edit(fn, f'remove {sid}')
    return jsonify(ok=True)


# ===================================================================== checks
@bp.get('/api/checks')
@require('viewer')
def get_checks():
    _need_project()
    return jsonify(issues=checker.check(ws().draft(), check_fs=cfg().get('check_fs', True), manager_port=cfg().get('port')))


@bp.post('/api/checks/fix')
@require('editor')
def fix_checks():
    fix = json_body().get('fix')
    if fix not in ('repair-labels', 'fix-log-names'):
        raise ApiError('Unknown fix.')
    changed = []

    def fn(p):
        changed.extend(checker.apply_fix(p, fix))
        return []
    _edit(fn, f'fix: {fix}')
    return jsonify(ok=True, changed=changed)


# ===================================================================== draft / apply / backups
@bp.get('/api/draft')
@require('viewer')
def get_draft():
    _need_project()
    info = ws().draft_info()
    info['diff'] = ws().diff() if info['pending'] else []
    return jsonify(info)


@bp.post('/api/draft/discard')
@require('editor')
def discard_draft():
    ws().discard()
    audit('draft.discard')
    return jsonify(ok=True)


@bp.post('/api/apply')
@require('editor')
def apply():
    _need_project()
    p = ws().draft()
    errors = [i for i in checker.check(p, manager_port=cfg().get('port')) if i['severity'] == 'error']
    if errors and not json_body().get('force'):
        return jsonify(ok=False, blocked=True, errors=errors,
                       message=f'{len(errors)} error(s) would stop odr-dabmux or an encoder. Fix them or apply anyway.'), 409
    res = ws().apply(current_user()['username'])
    db.x('INSERT INTO applies(ts, username, backup, status, message, log) VALUES (?,?,?,?,?,?)',
         (time.time(), current_user()['username'], res.get('backup', ''), 'ok' if res['ok'] else 'error',
          res.get('message', ''), __import__('json').dumps(res.get('log', []))))
    audit('apply', res.get('backup', ''), {'ok': res['ok'], 'message': res.get('message')})
    if mon():
        mon()._project_cache = (0, None)
    return jsonify(res), (200 if res['ok'] else 500)


@bp.get('/api/backups')
@require('viewer')
def list_backups():
    _need_project()
    return jsonify(backups=ws().backups()[:100],
                   applies=db.q('SELECT * FROM applies ORDER BY id DESC LIMIT 50'))


@bp.get('/api/backups/<bid>/diff')
@require('viewer')
def backup_diff(bid):
    import difflib
    import json as _json
    bdir = Path(ws().backup_dir) / bid
    if '/' in bid or not (bdir / 'manifest.json').exists():
        raise ApiError('Not found.', 404)
    man = _json.loads((bdir / 'manifest.json').read_text())
    out = []
    for path, info in man['files'].items():
        old = (bdir / info['backup']).read_text(errors='surrogateescape') if info.get('backup') else ''
        try:
            cur = Path(path).read_text(errors='surrogateescape')
        except OSError:
            cur = ''
        if old != cur:
            out.append({'path': path, 'diff': mask(''.join(difflib.unified_diff(
                cur.splitlines(True), old.splitlines(True), f'{path} (now)', f'{path} (backup {bid})')))})
    return jsonify(files=out, fs=man.get('fs', []))


@bp.post('/api/backups/<bid>/rollback')
@require('editor')
def rollback(bid):
    try:
        res = ws().rollback(bid, current_user()['username'])
    except FileNotFoundError:
        raise ApiError('Backup not found.', 404)
    audit('rollback', bid, {'ok': res['ok']})
    return jsonify(res), (200 if res['ok'] else 500)


@bp.get('/api/raw')
@require('viewer')
def raw_files():
    _need_project()
    which = request.args.get('which', 'draft')
    p = ws().draft() if which == 'draft' else ws().live()
    t = p.texts()
    reveal = current_user()['role'] == 'admin' and request.args.get('reveal') == '1'
    m = (lambda x: x) if reveal else mask
    return jsonify(mux={'path': str(p.mux_path), 'text': m(t['mux'])},
                   supervisor=[{'path': k, 'text': m(v)} for k, v in t['sups'].items()])


# ===================================================================== capabilities / reference
@bp.get('/api/capabilities')
@require('viewer')
def caps():
    c = capabilities.detect(cfg(), max_age=0 if request.args.get('refresh') else 300)
    return jsonify(c)


@bp.get('/api/reference')
@require()
def reference():
    return jsonify(uep=[{'bitrate': r, 'level': l, 'cu': c} for (r, l), c in sorted(UEP_TABLE.items())],
                   mp2_48k=MP2_BITRATES_48K, mp2_24k=MP2_BITRATES_24K, total_cu=TOTAL_CU,
                   announcements=ops.ANNOUNCEMENT_TYPES)


# ===================================================================== import
@bp.get('/api/fs')
@require('admin')
def fs_list():
    path = request.args.get('path') or '/'
    if not os.path.isabs(path) or '\x00' in path:
        raise ApiError('Path must be absolute.')
    path = os.path.realpath(path)
    if not os.path.isdir(path):
        raise ApiError('Not a directory.', 404)
    exts = tuple('.' + e.strip().lower() for e in (request.args.get('files', '')).split(',') if e.strip())
    entries = []
    try:
        with os.scandir(path) as it:
            for e in it:
                if e.name.startswith('.') and request.args.get('hidden') != '1':
                    continue
                try:
                    st = e.stat(follow_symlinks=True)
                except OSError:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    entries.append({'name': e.name, 'dir': True})
                elif exts and stat.S_ISREG(st.st_mode) and e.name.lower().endswith(exts):
                    entries.append({'name': e.name, 'dir': False, 'size': st.st_size, 'mtime': st.st_mtime})
                if len(entries) >= 2000:
                    break
    except PermissionError:
        raise ApiError('Permission denied for the service user.', 403)
    entries.sort(key=lambda x: (not x['dir'], x['name'].lower()))
    return jsonify(path=path, parent=os.path.dirname(path) if path != '/' else None,
                   writable=os.access(path, os.W_OK), entries=entries)


@bp.post('/api/import/scan')
@require('admin')
def import_scan():
    data = json_body()
    root = os.path.realpath(_str(data, 'root', 1024, True, 'Folder'))
    if not os.path.isdir(root):
        raise ApiError('Folder not found.', 404)
    muxes = [str(p) for p in find_mux_files(Path(root))]
    sups = [str(p) for p in find_supervisor_files(Path(root))]
    mux = data.get('mux_path') or next((m for m in muxes if m.endswith('/conf.mux')), muxes[0] if muxes else None)
    preview = None
    if mux:
        try:
            p = Project.load(root, mux, data.get('supervisor_paths') if data.get('supervisor_paths') is not None else sups)
            sts = p.stations()
            preview = {'ensemble': p.ensemble().get('label'), 'stations': len(sts),
                       'local': sum(1 for s in sts if s['feed'] == 'local'),
                       'external': sum(1 for s in sts if s['feed'] == 'external'),
                       'data': sum(1 for s in sts if s['kind'] != 'audio'),
                       'programs': len(p.programs()), 'cu': p.cu_used(),
                       'list': [{'label': s['label'], 'feed': s['feed'], 'codec': s['codec'], 'bitrate': s['bitrate'],
                                 'ptag': s['ptag'], 'audio_program': s['audio_program']} for s in sts],
                       'issues': checker.check(p)[:40]}
        except Exception as e:
            preview = {'error': f'Could not read the files: {e}'}
    others = sorted(set(str(p) for p in Path(root).glob('*.conf')) | set(str(p) for p in Path(root).glob('**/*.conf')
                                                                        if 'supervisor' in str(p)))[:50]
    return jsonify(root=root, mux_files=muxes, supervisor_files=sups, other_conf=others, mux_path=mux, preview=preview)


@bp.post('/api/import')
@require('admin')
def do_import():
    data = json_body()
    root = os.path.realpath(_str(data, 'root', 1024, True, 'Folder'))
    mux = os.path.realpath(_str(data, 'mux_path', 1024, True, 'Mux file'))
    sups = [os.path.realpath(s) for s in (data.get('supervisor_paths') or []) if isinstance(s, str)]
    if not os.path.isfile(mux):
        raise ApiError('Mux file not found.')
    for s in sups:
        if not os.path.isfile(s):
            raise ApiError(f'{s} not found.')
    try:
        Project.load(root, mux, sups)
    except Exception as e:
        raise ApiError(f'Could not read the files: {e}')
    if ws().has_draft():
        ws().discard()
    c = cfg()
    c.update(project_root=root, mux_path=mux, supervisor_paths=sups)
    cfgmod.save(c)
    if mon():
        mon()._project_cache = (0, None)
    audit('import', root, {'mux': mux, 'supervisor': sups})
    return jsonify(ok=True)


# ===================================================================== users
def _user_row(u):
    st = [r['station'] for r in db.q('SELECT station FROM user_stations WHERE user_id = ?', (u['id'],))]
    return {'id': u['id'], 'username': u['username'], 'display_name': u['display_name'], 'role': u['role'],
            'disabled': bool(u['disabled']), 'must_change_pw': bool(u['must_change_pw']), 'stations': st,
            'last_login': u['last_login'], 'created_at': u['created_at']}


@bp.get('/api/users')
@require('admin')
def list_users():
    return jsonify(users=[_user_row(u) for u in db.q('SELECT * FROM users ORDER BY username')])


def _set_user_stations(uid, stations):
    db.x('DELETE FROM user_stations WHERE user_id = ?', (uid,))
    for s in stations or []:
        if isinstance(s, str) and len(s) <= 16:
            db.x('INSERT OR IGNORE INTO user_stations(user_id, station) VALUES (?,?)', (uid, s))


@bp.post('/api/users')
@require('admin')
def create_user():
    data = json_body()
    username = _str(data, 'username', 64, True, 'Username')
    if not USERNAME_RE.match(username):
        raise ApiError('Username may contain letters, digits and . _ @ - (3-64 characters).')
    role = data.get('role', 'viewer')
    if role not in ROLES:
        raise ApiError('Unknown role.')
    pw = data.get('password') or ''
    problem = security.password_problem(pw, username)
    if problem:
        raise ApiError(problem)
    if db.q1('SELECT id FROM users WHERE username = ?', (username,)):
        raise ApiError('That username is taken.')
    uid = db.x('INSERT INTO users(username, display_name, pw_hash, role, must_change_pw, created_at) VALUES (?,?,?,?,?,?)',
               (username, _str(data, 'display_name', 64) or username, security.hash_password(pw), role,
                1 if data.get('must_change_pw', True) else 0, time.time()))
    _set_user_stations(uid, data.get('stations'))
    audit('user.create', username, {'role': role})
    return jsonify(_user_row(db.q1('SELECT * FROM users WHERE id = ?', (uid,))))


@bp.put('/api/users/<int:uid>')
@require('admin')
def update_user(uid):
    data = json_body()
    u = db.q1('SELECT * FROM users WHERE id = ?', (uid,))
    if not u:
        raise ApiError('User not found.', 404)
    role = data.get('role', u['role'])
    if role not in ROLES:
        raise ApiError('Unknown role.')
    if u['role'] == 'admin' and role != 'admin' and db.q1("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND disabled=0")['n'] <= 1:
        raise ApiError('You cannot remove the last administrator.')
    disabled = 1 if data.get('disabled', bool(u['disabled'])) else 0
    if uid == current_user()['id'] and (disabled or role != 'admin'):
        raise ApiError('You cannot disable or demote yourself.')
    db.x('UPDATE users SET display_name = ?, role = ?, disabled = ? WHERE id = ?',
         (_str(data, 'display_name', 64) or u['display_name'], role, disabled, uid))
    if data.get('password'):
        problem = security.password_problem(data['password'], u['username'])
        if problem:
            raise ApiError(problem)
        db.x('UPDATE users SET pw_hash = ?, must_change_pw = 1 WHERE id = ?', (security.hash_password(data['password']), uid))
        security.destroy_user_sessions(uid)
    if disabled:
        security.destroy_user_sessions(uid)
    if 'stations' in data:
        _set_user_stations(uid, data['stations'])
    audit('user.update', u['username'], {'role': role, 'disabled': bool(disabled)})
    return jsonify(_user_row(db.q1('SELECT * FROM users WHERE id = ?', (uid,))))


@bp.delete('/api/users/<int:uid>')
@require('admin')
def delete_user(uid):
    if uid == current_user()['id']:
        raise ApiError('You cannot delete yourself.')
    u = db.q1('SELECT * FROM users WHERE id = ?', (uid,))
    if not u:
        raise ApiError('User not found.', 404)
    if u['role'] == 'admin' and db.q1("SELECT COUNT(*) AS n FROM users WHERE role='admin'")['n'] <= 1:
        raise ApiError('You cannot delete the last administrator.')
    db.x('DELETE FROM users WHERE id = ?', (uid,))
    audit('user.delete', u['username'])
    return jsonify(ok=True)


@bp.get('/api/audit')
@require('admin')
def audit_log():
    off = max(0, int(request.args.get('offset', 0)))
    return jsonify(rows=db.q('SELECT * FROM audit ORDER BY id DESC LIMIT 100 OFFSET ?', (off,)))


# ===================================================================== settings / network
SETTING_KEYS = {'supervisor_socket': str, 'supervisorctl': str, 'supervisor_conf': str, 'dabmux_restart': str,
                'run_commands': bool, 'levels_source': str, 'dabmux_mgmt': str, 'onair_edi': str,
                'silence_db': float, 'silence_secs': float, 'check_fs': bool, 'stats_dir': str,
                'encoder_user': str, 'session_hours': int, 'behind_proxy': bool, 'tool_paths': dict}


@bp.get('/api/settings')
@require('admin')
def get_settings():
    c = cfg()
    return jsonify({k: c.get(k) for k in SETTING_KEYS} | {'bind': c['bind'], 'port': c['port'],
                                                         'project_root': c.get('project_root'),
                                                         'mux_path': c.get('mux_path'),
                                                         'supervisor_paths': c.get('supervisor_paths')})


@bp.put('/api/settings')
@require('admin')
def put_settings():
    data = json_body()
    c = cfg()
    for k, typ in SETTING_KEYS.items():
        if k not in data:
            continue
        v = data[k]
        if v is None or v == '':
            c[k] = None if typ in (str, dict) else c.get(k)
            continue
        try:
            c[k] = typ(v) if typ is not dict else ({kk: str(vv) for kk, vv in v.items() if vv} if isinstance(v, dict) else {})
        except (TypeError, ValueError):
            raise ApiError(f'Invalid value for {k}.')
    if c.get('levels_source') not in ('dabmux', 'stats', 'both'):
        raise ApiError('levels_source must be dabmux, stats or both.')
    if c.get('dabmux_restart') and not re.match(r'^(auto|none|supervisor:\S+|systemd:\S+|command:.+)$', c['dabmux_restart']):
        raise ApiError('dabmux restart must be auto, none, supervisor:<program>, systemd:<unit> or command:<cmd>.')
    cfgmod.save(c)
    capabilities.invalidate()
    audit('settings.update', '', {k: data[k] for k in data if k in SETTING_KEYS and k != 'tool_paths'})
    return get_settings()


@bp.put('/api/network')
@require('admin')
def put_network():
    data = json_body()
    bind = data.get('bind')
    if bind not in ('127.0.0.1', '0.0.0.0', '::', '::1'):
        raise ApiError('Listen address must be 127.0.0.1 (this machine only) or 0.0.0.0 (all interfaces).')
    try:
        port = int(data.get('port'))
    except (TypeError, ValueError):
        raise ApiError('Port must be a number.')
    if not 1024 <= port <= 65535:
        raise ApiError('Port must be between 1024 and 65535.')
    if ws().configured:
        p = ws().live()
        clash = [i for i in checker.check(p, manager_port=port) if i['code'] == 'port-clash' and str(port) in i['message']]
        if clash:
            raise ApiError(clash[0]['message'])
    token = cfgmod.request_network_change(cfg(), bind, port)
    audit('network.change', f'{bind}:{port}')
    # restart in a moment so this response gets out first; systemd brings us back
    import threading
    threading.Timer(1.0, lambda: os._exit(3)).start()
    return jsonify(ok=True, token=token, revert_seconds=cfgmod.REVERT_SECONDS)


@bp.post('/api/network/confirm')
@require('admin')
def confirm_network():
    ok = cfgmod.confirm_network(cfg(), json_body().get('token'))
    if not ok:
        raise ApiError('Nothing to confirm (it may already have been reverted).', 409)
    audit('network.confirm', f'{cfg()["bind"]}:{cfg()["port"]}')
    return jsonify(ok=True)


@bp.get('/api/network/pending')
@require('admin')
def network_pending():
    import json as _json
    try:
        pend = _json.loads(cfgmod.pending_network_path(cfg()).read_text())
        return jsonify(pending=True, deadline=pend.get('deadline'), new=pend.get('new'), old=pend.get('old'))
    except (FileNotFoundError, ValueError):
        return jsonify(pending=False)


# ===================================================================== DMB
@bp.get('/api/dmb')
@require('viewer')
def dmb_status():
    from .. import dmb
    return jsonify(dmb.support(cfg()))


@bp.post('/api/dmb')
@require('editor')
def dmb_add():
    from .. import dmb
    data = json_body()
    res = _edit(lambda p: dmb.add_dmb_service(p, data, cfg()), f'add DMB service {data.get("label")}')
    return jsonify(ok=True, station=res['station'])
