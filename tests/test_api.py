import json
import shutil
import time
from pathlib import Path

import pytest

from odr_mux import config as cfgmod, db
from odr_mux.web import create_app
from odr_mux.workspace import Workspace

FIX = Path(__file__).parent / 'fixtures'
H = {'X-Requested-With': 'odr-mux'}


@pytest.fixture()
def env(tmp_path):
    root = tmp_path / 'dab'
    shutil.copytree(FIX / 'mp2', root)
    state = tmp_path / 'state'
    state.mkdir()
    cfg = dict(cfgmod.DEFAULTS)
    cfg.update(_path=str(tmp_path / 'config.json'), state_dir=str(state), project_root=str(root),
               mux_path=str(root / 'conf.mux'), supervisor_paths=[str(root / 'supervisor' / 'odr-encoders.conf')],
               run_commands=False, check_fs=False)
    db.init(str(state / 'manager.db'))
    (state / 'setup-token').write_text('tok123')
    ws = Workspace(cfg)
    app = create_app(cfg, ws, None)
    return app, cfg, root


def login(app, user, pw):
    c = app.test_client()
    r = c.post('/api/login', json={'username': user, 'password': pw}, headers=H)
    assert r.status_code == 200, r.json
    csrf = c.get('/api/state').json['csrf']
    return c, {**H, 'X-CSRF-Token': csrf}


def test_setup_roles_and_station_scoping(env):
    app, cfg, root = env
    c = app.test_client()
    assert c.get('/api/state').json['setup_required']
    r = c.post('/api/setup', json={'token': 'wrong', 'username': 'admin', 'password': 'a-long-password-1'}, headers=H)
    assert r.status_code == 403
    r = c.post('/api/setup', json={'token': 'tok123', 'username': 'admin', 'password': 'a-long-password-1'}, headers=H)
    assert r.status_code == 200
    a, ah = login(app, 'admin', 'a-long-password-1')
    # station monitor for RTE Radio 1 (SId 0x2501) only
    r = a.post('/api/users', json={'username': 'rte1', 'password': 'station-pass-123', 'role': 'station',
                                   'stations': ['2501'], 'must_change_pw': False}, headers=ah)
    assert r.status_code == 200
    a.post('/api/users', json={'username': 'viewer', 'password': 'read-only-pass-123', 'role': 'viewer',
                               'must_change_pw': False}, headers=ah)
    s, sh = login(app, 'rte1', 'station-pass-123')
    ov = s.get('/api/overview').json
    assert [x['label'] for x in ov['stations']] == ['RTE Radio 1']
    assert 'cu_segments' not in ov and 'inputuri' not in ov['stations'][0]
    for path in ('/api/stations', '/api/raw', '/api/settings', '/api/checks', '/api/monitor/2502/log'):
        assert s.get(path).status_code == 403, path
    # viewer: read-only
    v, vh = login(app, 'viewer', 'read-only-pass-123')
    assert v.get('/api/stations').status_code == 200
    assert v.put('/api/ensemble', json={'label': 'X'}, headers=vh).status_code == 403
    # csrf required for writes
    assert a.put('/api/ensemble', json={'label': 'X'}, headers=H).status_code == 403


def test_secret_is_masked_and_preserved(env):
    app, cfg, root = env
    c = app.test_client()
    c.post('/api/setup', json={'token': 'tok123', 'username': 'admin', 'password': 'a-long-password-1'}, headers=H)
    a, ah = login(app, 'admin', 'a-long-password-1')
    st = a.get('/api/stations/2511').json
    assert 'REDACTED_TEST_KEY' not in json.dumps(st) and st['encoder']['input_has_secret']
    raw = a.get('/api/raw').json
    assert 'REDACTED_TEST_KEY' not in json.dumps(raw)
    # saving the masked URL back keeps the real key
    r = a.put('/api/stations/2511', json={'encoder': {'input': st['encoder']['input'], 'silence': 30}}, headers=ah)
    assert r.status_code == 200
    assert a.post('/api/apply', json={'force': True}, headers=ah).status_code == 200
    text = (root / 'supervisor' / 'odr-encoders.conf').read_text()
    assert 'skey=REDACTED_TEST_KEY' in text and '--silence=30' in text


def test_apply_blocked_by_errors_then_forced(env):
    app, cfg, root = env
    c = app.test_client()
    c.post('/api/setup', json={'token': 'tok123', 'username': 'admin', 'password': 'a-long-password-1'}, headers=H)
    a, ah = login(app, 'admin', 'a-long-password-1')
    a.put('/api/ensemble', json={'label': 'MPBNL DAB2 test'}, headers=ah)
    r = a.post('/api/apply', json={}, headers=ah)
    assert r.status_code == 409 and r.json['blocked']        # the MP2 fixture is over capacity
    r = a.post('/api/apply', json={'force': True}, headers=ah)
    assert r.status_code == 200 and r.json['ok']
    assert 'MPBNL DAB2 test' in (root / 'conf.mux').read_text()
    assert a.get('/api/draft').json['pending'] is False
    assert a.get('/api/backups').json['backups']


def test_network_change_reverts_unless_confirmed(tmp_path):
    cfg = dict(cfgmod.DEFAULTS)
    cfg.update(_path=str(tmp_path / 'c.json'), state_dir=str(tmp_path), bind='127.0.0.1', port=8092)
    tok = cfgmod.request_network_change(cfg, '0.0.0.0', 8093)
    assert json.load(open(tmp_path / 'c.json'))['port'] == 8093
    pend = cfgmod.startup_pending(cfg)              # first start on the new address: clock starts
    assert pend['deadline'] > time.time()
    # simulate the deadline passing
    p = cfgmod.pending_network_path(cfg)
    d = json.loads(p.read_text())
    d['deadline'] = time.time() - 1
    p.write_text(json.dumps(d))
    assert cfgmod.startup_pending(cfg) == {'reverted': True}
    saved = json.load(open(tmp_path / 'c.json'))
    assert (saved['bind'], saved['port']) == ('127.0.0.1', 8092)
    # confirmed change sticks
    tok = cfgmod.request_network_change(cfg, '0.0.0.0', 8093)
    cfgmod.startup_pending(cfg)
    assert not cfgmod.confirm_network(cfg, 'wrong')
    assert cfgmod.confirm_network(cfg, tok)
    assert cfgmod.startup_pending(cfg) is None
