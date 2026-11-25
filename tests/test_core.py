import glob
import gzip
import hashlib
import shutil
import struct
from pathlib import Path

import pytest

from odr_mux import checker, cu, dataservices, ops, renumber
from odr_mux.encoders import Args, effective_codec, set_input
from odr_mux.infofile import InfoDoc
from odr_mux.project import Project
from odr_mux.secrets import mask, unmask, has_secret
from odr_mux.supervisor_conf import SupervisorFile
from odr_mux.textfix import repair_mojibake, short_label_flag

FIX = Path(__file__).parent / 'fixtures'
MPBNL = FIX / 'mpbnl'
MP2 = FIX / 'mp2'


# ------------------------------------------------------------------ parsing
@pytest.mark.parametrize('path', glob.glob(str(FIX / '*/conf.mux')))
def test_mux_roundtrip_is_lossless(path):
    t = open(path).read()
    assert InfoDoc(t).dumps() == t


@pytest.mark.parametrize('path', glob.glob(str(FIX / '*/supervisor/*.conf')))
def test_supervisor_roundtrip_is_lossless(path):
    t = open(path).read()
    assert SupervisorFile(t).dumps() == t


def test_info_edit_keeps_comments():
    d = InfoDoc.load(MPBNL / 'conf.mux')
    d.find('services.srv-01').set('label', 'New Label', quoted=True)
    out = d.dumps()
    assert 'label "New Label"' in out
    assert '; Linkage Set Number, 12-bit, must be unique within the country' in out
    assert InfoDoc(out).get('services.srv-01.label') == 'New Label'


def test_args_roundtrip():
    argv = ['/usr/local/bin/odr-audioenc', '--gst-uri=http://x/y', '--silence=60', '-e', 'tcp://127.0.0.1:9001', '--dab', '--dabpsy=2']
    assert Args.parse(argv).to_argv() == argv


def test_vlc_gstreamer_switch():
    a = Args.parse(['odr-audioenc', '--gst-uri=http://a', '--bitrate=96'])
    set_input(a, 'vlc', 'http://a')
    assert a.to_argv() == ['odr-audioenc', '--vlc-uri=http://a', '--bitrate=96']


def test_codec_auto_matches_odr_audioenc():
    assert effective_codec(Args.parse(['odr-audioenc', '--bitrate=48', '--channels=2'])) == 'hev2'
    assert effective_codec(Args.parse(['odr-audioenc', '--bitrate=64', '--channels=2'])) == 'he'
    assert effective_codec(Args.parse(['odr-audioenc', '--bitrate=128', '--channels=2'])) == 'aaclc'
    assert effective_codec(Args.parse(['odr-audioenc', '--bitrate=128', '--dab'])) == 'mp2'


# ------------------------------------------------------------------ capacity
def test_cu_tables():
    assert cu.cu_for('dabplus', 128, 'EEP_B', 4) == 60
    assert cu.cu_for('dabplus', 48, 'EEP_A', 4) == 24
    assert cu.cu_for('audio', 128, 'UEP', 3) == 96
    assert cu.cu_for('audio', 256, None, 3) == 192          # audio defaults to UEP
    assert cu.cu_for('audio', 56, 'UEP', 1) == 32 * 0 + cu.cu_for('audio', 56, 'EEP_A', 1)  # no UEP-1 at 56k -> EEP fallback


def test_project_stations_and_cu():
    p = Project.load(MPBNL)
    assert p.cu_used() == 863
    sts = p.stations()
    by = {s['subchannel_uid']: s for s in sts}
    assert by['sub-02']['feed'] == 'external'            # port 2492, no local encoder
    assert by['sub-03']['ptag'] == 'P04'                 # irregular numbering kept as is
    assert by['sub-03']['audio_program'] == 'odr-audioencoder-rrr'
    assert by['sub-spi']['kind'] == 'data'
    assert [c['uid'] for c in by['sub-06']['secondary_components']] == ['comp-06-sub']


def test_checker_finds_known_problems():
    codes = {(i['code'], i.get('ref', {}).get('program')) for i in checker.check(Project.load(MPBNL))}
    assert ('log-name', 'odr-padencoder-s21punk') in codes
    assert ('log-name', 'odr-padencoder-variant') in codes
    assert ('merged-opts', 'odr-audioencoder-energy106') in codes
    assert any(c == 'link-self' for c, _ in codes)
    assert not any(i['severity'] == 'error' for i in checker.check(Project.load(MPBNL)))


def test_short_label_rule_matches_dabmux():
    assert short_label_flag('MPB Radio 1', 'MPB Rad1')[0]
    assert not short_label_flag('Plus One', 'Plus 1')[0]


def test_mojibake_repair():
    assert repair_mojibake('RaidiÃ³ RÃ­-RÃ¡') == 'Raidió Rí-Rá'
    p = Project.load(MPBNL)
    checker.apply_fix(p, 'repair-labels')
    assert p.service('srv-03').get('label') == 'Raidió Rí-Rá'


def test_secret_masking():
    u = 'https://s.example/hi.aac?skey=SECRET123'
    assert has_secret(u) and 'SECRET123' not in mask(u)
    assert unmask(mask(u), u) == u


# ------------------------------------------------------------------ edits
def test_feed_flip_roundtrip_is_exact():
    for root in (MPBNL, MP2):
        for st in Project.load(root).stations():
            if st['feed'] != 'local':
                continue
            p = Project.load(root)
            t0 = p.texts()
            ops.set_feed(p, st['id'], 'external', {})
            assert p.station(st['id'])['feed'] == 'external'
            ops.set_feed(p, st['id'], 'local', {})
            t1 = p.texts()
            assert t0['mux'] == t1['mux'] and t0['sups'] == t1['sups'], st['label']


def test_add_mp2_station_with_psy_model():
    p = Project.load(MPBNL)
    r = ops.add_station(p, {'label': 'Test FM', 'sid': '0x24FF', 'codec': 'mp2', 'bitrate': 128,
                            'encoder': {'input': 'http://x/y.mp3', 'dabpsy': 2}})
    st = p.station(r['station'])
    assert st['type'] == 'audio' and st['protection'] == 'UEP-3' and st['cu'] == 96
    a = Args.parse(p.program(st['audio_program']).argv)
    assert a.has('dab') and a.get('dabpsy') == '2'
    assert st['ptag'] == 'P27' and st['port'] == 9027
    assert any(op['op'] == 'mkdir' for op in r['fs'])


def test_external_station_gets_no_encoders():
    p = Project.load(MPBNL)
    n = len(p.programs())
    r = ops.add_station(p, {'label': 'Remote', 'sid': '0x24FE', 'codec': 'hev2', 'bitrate': 48, 'feed': 'external',
                            'external': {'proto': 'edi', 'port': 1234}})
    assert len(p.programs()) == n
    st = p.station(r['station'])
    assert st['feed'] == 'external' and st['port'] == 1234


def test_codec_switch_changes_subchannel():
    p = Project.load(MP2)
    ops.update_station(p, '2506', {'encoder': {'codec': 'mp2', 'dabpsy': 3}})
    st = p.station('2506')
    assert st['type'] == 'audio' and st['encoder']['dabpsy'] == 3


def test_journaline_data_service():
    p = Project.load(MPBNL)
    r = dataservices.add_data_service(p, {'preset': 'journaline', 'label': 'News', 'sid': '0xE3222345',
                                          'inputuri': '/x/journaline.dat'})
    st = p.station(r['station'])
    assert st['kind'] == 'data' and st['subchannel']['inputuri'] == '/x/journaline.dat'
    assert st['component']['user-applications']['userapp'] == 'journaline'
    assert st['component']['datagroup'] == 'true'


# ------------------------------------------------------------------ renumber
def test_remove_station_closes_gap():
    p = Project.load(MP2)
    ids = [s['id'] for s in p.stations()]
    res = renumber.apply(p, ids, remove=[ids[8]], mode='renumber')  # KISS, P09
    sts = p.stations()
    assert len(sts) == 18
    kp = next(s for s in sts if s['label'] == 'KISS+')
    assert (kp['subchannel_uid'], kp['port'], kp['ptag'], kp['encoder']['stats']) == ('sub-09', 9009, 'P09', '/var/tmp/P09.stats')
    assert kp['mot_dir'].endswith('/P09')
    last = sts[-1]
    assert last['ptag'] == 'P18' and last['port'] == 9018
    moves = next(o for o in res['fs'] if o['op'] == 'move_many')['moves']
    assert moves[0] == {'from': '/home/ryan/dab/mot/P10', 'to': '/home/ryan/dab/mot/P09'}
    assert any(o['op'] == 'archive' for o in res['fs'])
    assert not [i for i in checker.check(p) if i['code'] in ('port-dup', 'subch-id-dup', 'comp-ref')]
    assert any(i['label'] == 'KISS+' for i in res['impact'])


def test_external_ports_are_pinned():
    p = Project.load(MPBNL)
    ids = [s['id'] for s in p.stations() if s['kind'] == 'audio']
    renumber.apply(p, ids, remove=[ids[0]], mode='renumber')      # remove MPB Radio 1
    ext = next(s for s in p.stations() if s['label'] == 'MPB Radio 2')
    assert ext['port'] == 2492


def test_keep_mode_only_reorders():
    p = Project.load(MP2)
    ids = [s['id'] for s in p.stations()]
    order = ids[1:] + ids[:1]
    renumber.apply(p, order)                 # default: keep numbers
    sts = p.stations()
    assert sts[0]['label'] == 'RTE 2FM' and sts[0]['subchannel_uid'] == 'sub-02'


# ------------------------------------------------------------------ apply / rollback on a real folder
def _project_copy(tmp_path, src=MP2):
    root = tmp_path / 'dab'
    shutil.copytree(src, root)
    for f in list(root.rglob('*.conf')) + [root / 'conf.mux']:
        f.write_text(f.read_text().replace('/home/ryan/dab', str(root)))
    for i in range(1, 20):
        d = root / 'mot' / f'P{i:02d}' / 'slide'
        d.mkdir(parents=True)
        (d.parent / 'INFO.dls').write_text(f'station {i}')
    return root


def test_workspace_apply_and_rollback(tmp_path):
    from odr_mux.workspace import Workspace
    root = _project_copy(tmp_path)
    cfg = {'state_dir': str(tmp_path / 'state'), 'project_root': str(root), 'mux_path': str(root / 'conf.mux'),
           'supervisor_paths': [str(root / 'supervisor' / 'odr-encoders.conf')], 'run_commands': False}
    ws = Workspace(cfg)
    before = (root / 'conf.mux').read_text()
    ids = [s['id'] for s in ws.live().stations()]
    ws.edit(lambda p: renumber.apply(p, ids, remove=[ids[8]], mode='renumber'), 'test', 'remove P09')
    assert ws.has_draft() and ws.diff()
    r = ws.apply('test')
    assert r['ok'], r
    assert (root / 'mot' / 'P09' / 'INFO.dls').read_text() == 'station 10'   # P10 moved to P09
    assert not (root / 'mot' / 'P19').exists()
    assert list((root / 'mot' / '_removed').iterdir())
    assert (root / 'conf.mux').read_text() != before
    rb = ws.rollback(r['backup'], 'test')
    assert rb['ok'], rb
    assert (root / 'conf.mux').read_text() == before
    assert (root / 'mot' / 'P09' / 'INFO.dls').read_text() == 'station 9'
    assert (root / 'mot' / 'P19' / 'INFO.dls').read_text() == 'station 19'


# ------------------------------------------------------------------ DMB + on-air
def test_dmb_outer_coder_matches_odr_dabmux():
    from odr_mux.dmb import OuterCoder
    d = (FIX / 'dmb-test.ts').read_bytes()
    d = d[:len(d) // 188 * 188]
    out = OuterCoder().feed(d)
    assert hashlib.sha256(out).hexdigest() == (FIX / 'dmb-test.expected.sha256').read_text().strip()


def _frames():
    out = {}
    with gzip.open(FIX / 'onair-frames.bin.gz', 'rb') as f:
        for _ in range(2):
            scid, n = struct.unpack('>BI', f.read(5))
            fr = []
            for _ in range(n):
                (ln,) = struct.unpack('>H', f.read(2))
                fr.append(f.read(ln))
            out[scid] = fr
    return out


def test_onair_decodes_dls_and_slides_from_real_mux_output():
    from odr_mux.onair import DabPlusExtractor, MP2Extractor
    fr = _frames()
    a, b = DabPlusExtractor(48), MP2Extractor(128)
    for x in fr[1]:
        a.frame(x)
    for x in fr[2]:
        b.frame(x)
    assert a.pad.dls.text == 'Hello from DAB+ station one'
    assert b.pad.dls.text == 'MP2 station: Raidió test'
    assert a.pad.mot.mime == 'image/jpeg' and a.pad.mot.image[:2] == b'\xff\xd8'
    assert b.pad.mot.mime == 'image/jpeg' and b.pad.mot.image[:2] == b'\xff\xd8'
    assert a.info['ps'] and a.info['sbr'] and b.info['bitrate'] == 128


def test_dmb_pacer_emits_exact_rate_and_valid_codewords():
    from odr_mux.dmb import Pacer, rs_syndromes_ok, NULL_TS
    p = Pacer(136)
    d = (FIX / 'dmb-test.ts').read_bytes()
    for i in range(0, len(d) // 188 * 188, 188):
        p.put_ts(d[i:i + 188])
    out = b''.join(p.next_frame() for _ in range(200))      # more frames than input: null stuffing
    assert len(out) == 200 * 136 * 3 and p.nulls > 0
    I, M = 12, 17
    pos = (I * M * I // 204 + 1) * 204
    good = 0
    while pos + 204 + (I - 1) * M * I < len(out):
        pkt = bytes(out[pos + i + (i % I) * M * I] for i in range(204))
        assert pkt[0] == 0x47 and rs_syndromes_ok(pkt)
        good += 1
        pos += 204
    assert good > 100


def test_default_keeps_numbers_on_removal():
    p = Project.load(MP2)
    ids = [s['id'] for s in p.stations()]
    res = renumber.apply(p, ids, remove=[ids[8]])
    kp = next(s for s in p.stations() if s['label'] == 'KISS+')
    assert (kp['subchannel_uid'], kp['port'], kp['ptag']) == ('sub-10', 9010, 'P10')
    assert not any(o['op'] == 'move_many' for o in res['fs'])
    assert any(o['op'] == 'archive' for o in res['fs'])


# ------------------------------------------------------------------ T-DMB packaging
def test_tdmb_structure():
    from odr_mux.tdmb import remux
    from odr_mux.tsinfo import inspect, is_tdmb
    src = (FIX / 'dmb-test.ts').read_bytes()
    for tv in (True, False):
        out = remux(src, tv)
        assert len(out) % 188 == 0 and all(out[i] == 0x47 for i in range(0, len(out), 188))
        info = inspect(out)
        assert is_tdmb(info), info
        types = sorted((s['stream_type'], s['es_id']) for s in info['programs'][0]['streams'])
        assert types == ([(0x12, 3), (0x12, 4), (0x13, 1), (0x13, 2)] if tv else [(0x12, 4), (0x13, 1), (0x13, 2)])


def test_tdmb_descriptors():
    from odr_mux.tdmb import descr, bifs_config, initial_od
    assert descr(0x05, b'\x00' * 200)[:3] == b'\x05\x81\x48'           # 7-bit size groups
    assert bifs_config(320, 240) == bytes.fromhex('08380a000780')       # identical to GPAC's BIFSConfig
    iod = initial_od(320, 240, True)
    assert iod[0] == 0x02 and b'\x08\x38\x0a\x00\x07\x80' in iod


@pytest.mark.skipif(shutil.which('gpac') is None or shutil.which('ffmpeg') is None, reason='needs gpac + ffmpeg')
def test_tdmb_decodes_in_gpac(tmp_path):
    import subprocess
    from odr_mux.tdmb import remux
    src = (FIX / 'dmb-test.ts').read_bytes()
    (tmp_path / 'tv.ts').write_bytes(remux(src, True))
    subprocess.run(['gpac', '-i', str(tmp_path / 'tv.ts'), '-o', str(tmp_path / 'tv.mp4')], capture_output=True, timeout=120)
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,width', '-of', 'csv=p=0',
                        str(tmp_path / 'tv.mp4')], capture_output=True, text=True)
    assert 'h264,320' in r.stdout and 'aac' in r.stdout
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(tmp_path / 'tv.mp4'), '-f', 'null', '-'], capture_output=True, text=True)
    assert r.returncode == 0 and not r.stderr.strip()
