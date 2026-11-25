"""Edit operations on a Project (ensemble, stations, encoders, feed switching, new stations).

Every function mutates the project in place and returns a list of *filesystem operations*
that Apply must perform (mkdir / write file / rename folder ...).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from . import cu as cumod
from .encoders import (Args, set_codec, set_input, tool_of, effective_codec, parse_tcp, is_local)
from .infofile import Node, parse_int, with_port, split_uri
from .project import Project, slug, station_key
from .secrets import unmask
from .supervisor_conf import Section, SupervisorFile


class OpError(ValueError):
    pass


# ------------------------------------------------------------------ helpers
def _set(node: Node, key: str, value, quoted: Optional[bool] = None):
    if value is None or value == '':
        node.remove(key)
    else:
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        node.set(key, value, quoted=quoted)


_SERVICE_FIELDS = ['id', 'ecc', 'label', 'shortlabel', 'pty', 'pty-sd', 'language', 'country', 'radiodns',
                   'clusters', 'other-services']
_QUOTED = {'label', 'shortlabel', 'inputuri', 'radiodns'}


def update_fields(node: Node, data: dict, allowed: List[str]):
    for k, v in data.items():
        if k not in allowed:
            continue
        if isinstance(v, (dict, list)):
            continue
        _set(node, k, v, quoted=True if k in _QUOTED else None)


def set_ensemble(p: Project, data: dict):
    ens = p.sec('ensemble', create=True)
    update_fields(ens, data, ['id', 'ecc', 'label', 'shortlabel', 'local-time-offset', 'international-table',
                              'reconfig-counter', 'alarm-flag'])
    return []


def _station_or_fail(p: Project, key) -> dict:
    st = p.station(key)
    if st is None:
        raise OpError(f'unknown station {key}')
    return st


def update_station(p: Project, key, data: dict):
    """data: {service:{...}, subchannel:{...}, component:{...}, encoder:{...}, pad:{...}}"""
    st = _station_or_fail(p, key)
    fs = []
    if data.get('service') and st['service_uid']:
        svc = p.service(st['service_uid'])
        update_fields(svc, data['service'], _SERVICE_FIELDS)
        if 'announcements' in data['service']:
            set_service_announcements(svc, data['service']['announcements'])
    sc = p.subchannel(st['subchannel_uid'])
    if data.get('subchannel'):
        d = dict(data['subchannel'])
        if 'type' in d and d['type'] != sc.get('type'):
            # switching MP2 <-> DAB+ also switches the protection profile default
            _switch_subch_type(sc, d['type'])
        update_fields(sc, d, ['type', 'bitrate', 'id', 'protection', 'protection-profile', 'inputproto',
                              'inputuri', 'buffer-management', 'buffer', 'prebuffering', 'tist-delay',
                              'nonblock', 'zmq-buffer', 'zmq-prebuffering'])
    if data.get('component') and st['component_uid']:
        comp = p.component(st['component_uid'])
        c = data['component']
        update_fields(comp, c, ['type', 'figtype', 'address', 'datagroup', 'label', 'shortlabel'])
        if 'user_apps' in c:
            set_user_apps(comp, c['user_apps'])
    if data.get('encoder') or data.get('pad'):
        if st['feed'] != 'local' or not st['audio_program']:
            raise OpError('this station is not fed by a local encoder')
        fs += update_encoder(p, st, data.get('encoder') or {}, data.get('pad') or {})
    # keep encoder bitrate in sync with the subchannel
    st2 = p.station(key)
    if st2 and st2['audio_program'] and data.get('subchannel', {}).get('bitrate'):
        prog = p.program(st2['audio_program'])
        a = Args.parse(prog.argv)
        a.set('bitrate', str(data['subchannel']['bitrate']))
        prog.argv = a.to_argv()
    return fs


def _switch_subch_type(sc: Node, new_type: str):
    br = parse_int(sc.get('bitrate'), 0)
    lvl = parse_int(sc.get('protection'), 3)
    if new_type == 'audio':
        # MP2: UEP if the level exists at this bitrate
        lv = lvl if (br, lvl) in cumod.UEP_TABLE else 3
        if (br, lv) in cumod.UEP_TABLE:
            sc.set('protection-profile', 'UEP')
            sc.set('protection', str(lv))
        else:
            sc.set('protection-profile', 'EEP_A')
    elif new_type == 'dabplus':
        if sc.get('protection-profile') == 'UEP' or sc.get('protection-profile') is None:
            sc.set('protection-profile', 'EEP_B' if br % 32 == 0 else 'EEP_A')
            if lvl > 4:
                sc.set('protection', '4')


ANNOUNCEMENT_TYPES = ['Alarm', 'Traffic', 'Travel', 'Warning', 'News', 'Weather', 'Event', 'Special',
                      'ProgrammeInfo', 'Sports', 'Finance']


def set_service_announcements(svc: Node, ann: dict):
    """ann: {"types": ["Traffic", ...], "clusters": "1,2"}  -> services.srv.announcements{Traffic true; clusters "1,2"}"""
    if not ann or (not ann.get('types') and not ann.get('clusters')):
        svc.remove('announcements')
        return
    a = svc.block('announcements')
    for t in ANNOUNCEMENT_TYPES:
        if t in (ann.get('types') or []):
            a.set(t, 'true')
        else:
            a.remove(t)
    if ann.get('clusters'):
        a.set('clusters', str(ann['clusters']), quoted=True)
    else:
        a.remove('clusters')


def set_user_apps(comp: Node, apps: List[str]):
    comp.remove('user-applications')
    if apps:
        ua = comp.block('user-applications')
        for a in apps:
            ua.append(Node('userapp', a)).quoted = True


def update_encoder(p: Project, st: dict, enc: dict, pad: dict):
    prog = p.program(st['audio_program'])
    a = Args.parse(prog.argv)
    old_input = (st['encoder'] or {}).get('input')
    if 'input_kind' in enc or 'input' in enc:
        kind = enc.get('input_kind') or st['encoder']['input_kind'] or 'gstreamer'
        val = unmask(enc.get('input', old_input), old_input)
        set_input(a, kind, val)
    if 'codec' in enc:
        set_codec(a, enc['codec'])
        sc = p.subchannel(st['subchannel_uid'])
        want = 'audio' if enc['codec'] == 'mp2' else 'dabplus'
        if sc.get('type') != want:
            _switch_subch_type(sc, want)
            sc.set('type', want)
    simple = {'bitrate': 'bitrate', 'rate': 'rate', 'channels': 'channels', 'dabmode': 'dabmode',
              'dabpsy': 'dabpsy', 'pad': 'pad', 'silence': 'silence', 'bandwidth': 'bandwidth',
              'audio_gain': 'audio-gain', 'icy_text': 'write-icy-text', 'stats': 'stats',
              'vlc_cache': 'vlc-cache', 'identifier': 'identifier'}
    for k, opt in simple.items():
        if k in enc:
            v = enc[k]
            a.set(opt, None if v in (None, '') else str(v))
    flags = {'drift_comp': 'drift-comp', 'icy_dlplus': 'write-icy-text-dl-plus'}
    for k, opt in flags.items():
        if k in enc:
            a.set(opt, bool(enc[k]))
    if 'afterburner' in enc:
        a.set('no-afterburner', not enc['afterburner'])
    if 'remote_outputs' in enc:
        # keep local outputs, replace the remote (other-mux) ones
        keep_edi = [v for v in a.get_all('edi') if is_local(parse_tcp(v)[0])]
        keep_zmq = [v for v in a.get_all('output') if is_local(parse_tcp(v)[0])]
        r_edi = [o['uri'] for o in enc['remote_outputs'] if o.get('kind') == 'edi' and o.get('uri')]
        r_zmq = [o['uri'] for o in enc['remote_outputs'] if o.get('kind') != 'edi' and o.get('uri')]
        a.set_all('edi', keep_edi + r_edi)
        a.set_all('output', keep_zmq + r_zmq)
    if 'bitrate' in enc and enc['bitrate']:
        p.subchannel(st['subchannel_uid']).set('bitrate', str(enc['bitrate']))
    prog.argv = a.to_argv()

    if pad and st['pad_program']:
        pp = p.program(st['pad_program'])
        pa = Args.parse(pp.argv)
        pmap = {'slide_dir': 'dir', 'sleep': 'sleep', 'label': 'label', 'label_ins': 'label-ins',
                'charset': 'charset', 'item_state': 'item-state', 'max_slide_size': 'max-slide-size',
                'xpad_interval': 'xpad-interval'}
        for k, opt in pmap.items():
            if k in pad:
                v = pad[k]
                pa.set(opt, None if v in (None, '') else str(v))
        for k, opt in {'raw_slides': 'raw-slides', 'erase': 'erase', 'raw_dls': 'raw-dls',
                       'remove_dls': 'remove-dls'}.items():
            if k in pad:
                pa.set(opt, bool(pad[k]))
        if 'dls_files' in pad:
            pa.set_all('dls', [x for x in pad['dls_files'] if x])
        pp.argv = pa.to_argv()
    return []


# ------------------------------------------------------------------ numbering helpers
def _num_suffix(uid):
    m = re.match(r'^(.*?)(\d+)$', uid or '')
    return (m.group(1), int(m.group(2)), len(m.group(2))) if m else (None, None, None)


def next_uid(existing: List[str], prefix: str, num: Optional[int] = None) -> str:
    nums = []
    width = 2
    for u in existing:
        pre, n, w = _num_suffix(u)
        if pre == prefix and n is not None:
            nums.append(n)
            width = max(width, w)
    if num is None:
        num = (max(nums) + 1) if nums else 1
    uid = f'{prefix}{num:0{width}d}'
    while uid in existing:
        num += 1
        uid = f'{prefix}{num:0{width}d}'
    return uid


def free_subch_id(p: Project) -> int:
    used = {parse_int(sc.get('id')) for sc in p.subchannels()}
    for i in range(64):
        if i not in used:
            return i
    raise OpError('no free subchannel id (0..63 all used)')


def port_pattern(p: Project):
    """(offset) such that port == offset + Pnumber for most local stations, or None."""
    from collections import Counter
    c = Counter()
    for st in p.stations():
        if st['port'] and st['ptag']:
            c[st['port'] - int(st['ptag'][1:])] += 1
    if not c:
        return None
    off, n = c.most_common(1)[0]
    return off if n >= 2 else None


def next_ptag(p: Project) -> str:
    nums = [int(s['ptag'][1:]) for s in p.stations() if s['ptag']]
    # also count parked stations' tags and P folders listed in parked data
    for v in p.parked.values():
        if v.get('ptag'):
            nums.append(int(v['ptag'][1:]))
    n = (max(nums) + 1) if nums else 1
    return f'P{n:02d}'


def next_port(p: Project, ptag: Optional[str] = None) -> int:
    used = {p.subch_port(sc) for sc in p.subchannels()} - {None}
    off = port_pattern(p)
    if off is not None and ptag:
        cand = off + int(ptag[1:])
        if cand not in used:
            return cand
    cand = max([x for x in used if 9000 <= x < 10000] or [9000]) + 1
    while cand in used:
        cand += 1
    return cand


def mot_root(p: Project) -> Path:
    for st in p.stations():
        if st['mot_dir']:
            return Path(st['mot_dir']).parent
    return p.root / 'mot'


# ------------------------------------------------------------------ supervisor templates
def encoder_file(p: Project) -> SupervisorFile:
    best, n = None, -1
    for f in p.sups.values():
        k = sum(1 for s in f.programs() if tool_of(s.argv) in ('audioenc', 'padenc'))
        if k > n:
            best, n = f, k
    if best is None:
        path = str(p.root / 'supervisor' / 'odr-encoders.conf')
        best = SupervisorFile('', path)
        p.sups[path] = best
        p.sup_paths.append(path)
    return best


def _template_entries(p: Project, tool: str, name: str) -> dict:
    for s in p.programs():
        if tool_of(s.argv) == tool:
            out = {}
            for e in s.entries:
                if e.is_comment or e.key == 'command':
                    continue
                v = e.value
                if e.key in ('stdout_logfile', 'stderr_logfile'):
                    v = str(Path(v).with_name(name + '.log'))
                out[e.key] = v
            return out
    user = p.settings.get('encoder_user')
    d = {'autostart': 'true', 'autorestart': 'true', 'priority': '10', 'redirect_stderr': 'true',
         'stdout_logfile': f'/var/log/supervisor/{name}.log', 'stdout_logfile_maxbytes': '2097152',
         'stdout_logfile_backups': '2'}
    if user:
        d['user'] = user
        d['group'] = user
    return d


def _bin(p: Project, tool: str) -> str:
    for s in p.programs():
        if tool_of(s.argv) == tool:
            return s.argv[0]
    return f'/usr/local/bin/odr-{tool}'


def create_encoders(p: Project, st_label: str, ptag: str, port: int, enc: dict, pad: dict,
                    after: Optional[Section] = None):
    """Create an odr-padenc + odr-audioenc pair. Returns (audio_section, pad_section, fs_ops)."""
    base = enc.get('name') or slug(st_label)
    names = {s.program for s in p.programs()}
    n = base
    i = 2
    while f'odr-audioencoder-{n}' in names or f'odr-padencoder-{n}' in names:
        n = f'{base}{i}'
        i += 1
    mot = mot_root(p) / ptag
    f = encoder_file(p)
    fs = [{'op': 'mkdir', 'path': str(mot / 'slide')},
          {'op': 'touch', 'path': str(mot / 'INFO.dls')}]
    pad_sec = None
    padlen = enc.get('pad', 34 if (enc.get('bitrate') or 64) >= 64 else 17)
    if padlen:
        pa = Args('padenc', _bin(p, 'padenc'))
        pa.set('dir', pad.get('slide_dir') or str(mot / 'slide'))
        pa.set('sleep', str(pad.get('sleep') or 20))
        pa.set_all('dls', pad.get('dls_files') or [str(mot / 'INFO.dls')])
        pa.set('output', n)
        pa.set('label', str(pad.get('label', 12)))
        pa.set('label-ins', str(pad.get('label_ins', 1200)))
        pname = f'odr-padencoder-{n}'
        pad_sec = f.add_program(pname, _template_entries(p, 'padenc', pname), tag=ptag, after=after,
                                argv=pa.to_argv())
        after = pad_sec
    a = Args('audioenc', _bin(p, 'audioenc'))
    set_input(a, enc.get('input_kind') or 'gstreamer', enc.get('input') or '')
    a.set('drift-comp', enc.get('drift_comp', True))
    a.set('silence', str(enc.get('silence', 60)))
    a.set('bitrate', str(enc.get('bitrate') or 64))
    a.set('rate', str(enc.get('rate') or (48000 if enc.get('codec') == 'mp2' else 48000)))
    a.set('channels', str(enc.get('channels') or 2))
    set_codec(a, enc.get('codec') or 'auto')
    if enc.get('codec') == 'mp2':
        if enc.get('dabmode'):
            a.set('dabmode', enc['dabmode'])
        if enc.get('dabpsy') is not None:
            a.set('dabpsy', str(enc['dabpsy']))
    if padlen:
        a.set('pad', str(padlen))
        a.set('pad-socket', n)
    if enc.get('icy_text'):
        a.set('write-icy-text', enc['icy_text'])
    a.set_all('edi', [f'tcp://127.0.0.1:{port}'])
    stats_dir = p.settings.get('stats_dir', '/var/tmp')
    a.set('stats', f'{stats_dir}/{ptag}.stats')
    aname = f'odr-audioencoder-{n}'
    entries = _template_entries(p, 'audioenc', aname)
    a_sec = f.add_program(aname, entries, tag=ptag, after=after, argv=a.to_argv())
    return a_sec, pad_sec, fs


# ------------------------------------------------------------------ add / feed
def add_station(p: Project, data: dict):
    """data: {label, shortlabel, sid, ecc?, pty?, language?, codec, bitrate, protection?, profile?,
              feed: local|external, external: {proto, port, uri}, encoder: {...}, pad: {...}}"""
    label = data.get('label') or 'New station'
    sid = data.get('sid')
    if not sid:
        raise OpError('a service id (SId) is required')
    if p.station(station_key(Node('x', None, [Node('id', sid)]), None)):
        raise OpError(f'service id {sid} is already used')
    svcs = p.sec('services', create=True)
    subs = p.sec('subchannels', create=True)
    comps = p.sec('components', create=True)
    codec = data.get('codec') or 'hev2'
    stype = 'audio' if codec == 'mp2' else 'dabplus'
    bitrate = int(data.get('bitrate') or (128 if codec == 'mp2' else 64))
    ptag = next_ptag(p)
    num = int(ptag[1:])
    suid = next_uid([s.key for s in p.services()], 'srv-', num if f'srv-{num:02d}' not in svcs.keys() else None)
    num = _num_suffix(suid)[1]
    scuid = next_uid([s.key for s in p.subchannels()], 'sub-', num)
    cuid = next_uid([c.key for c in p.components()], 'comp-', num)

    svc = Node(suid, None, [])
    svc.append(Node('id', sid))
    if data.get('ecc'):
        svc.append(Node('ecc', data['ecc']))
    lab = Node('label', label)
    lab.quoted = True
    svc.append(lab)
    sl = data.get('shortlabel') or label[:8]
    sln = Node('shortlabel', sl)
    sln.quoted = True
    svc.append(sln)
    svc.append(Node('pty', str(data.get('pty', 0))))
    if data.get('language'):
        svc.append(Node('language', data['language']))
    # insert data services last: put before first service that is not audio (e.g. srv-spi)
    svcs.append(svc, _insert_index_before_data(p, svcs))

    sc = Node(scuid, None, [])
    sc.append(Node('type', stype))
    sc.append(Node('bitrate', str(bitrate)))
    sc.append(Node('id', str(free_subch_id(p))))
    if codec == 'mp2':
        lvl = int(data.get('protection') or 3)
        if (bitrate, lvl) in cumod.UEP_TABLE:
            sc.append(Node('protection-profile', 'UEP'))
        else:
            sc.append(Node('protection-profile', data.get('profile') or 'EEP_A'))
    else:
        lvl = int(data.get('protection') or 3)
        sc.append(Node('protection-profile', data.get('profile') or ('EEP_B' if bitrate % 32 == 0 else 'EEP_A')))
    sc.append(Node('protection', str(lvl)))
    fs = []
    feed = data.get('feed', 'local')
    ext = data.get('external') or {}
    proto = ext.get('proto', 'edi')
    port = int(ext.get('port') or next_port(p, ptag))
    sc.append(Node('inputproto', proto))
    uri = ext.get('uri') or (f'tcp://0.0.0.0:{port}' if proto in ('edi',) else f'tcp://*:{port}')
    un = Node('inputuri', uri)
    un.quoted = True
    sc.append(un)
    if proto in ('edi', 'zmq'):
        for k, v in (('buffer-management', 'prebuffering'), ('buffer', '40'), ('prebuffering', '20')):
            sc.append(Node(k, v))
    subs.append(sc, _insert_index_before_data(p, subs, kind='sub'))

    comp = Node(cuid, None, [])
    comp.append(Node('service', suid))
    comp.append(Node('subchannel', scuid))
    if data.get('slideshow', True):
        set_user_apps(comp, ['slideshow'])
    comps.append(comp, _insert_index_before_data(p, comps, kind='comp'))

    if feed == 'local':
        enc = dict(data.get('encoder') or {})
        enc.setdefault('codec', codec)
        enc['bitrate'] = bitrate
        after = _last_encoder_section(p)
        _, _, f2 = create_encoders(p, label, ptag, port, enc, data.get('pad') or {}, after=after)
        fs += f2
    return {'station': station_key(svc, sc), 'fs': fs}


def _insert_index_before_data(p: Project, parent: Node, kind='svc'):
    """Index before the first data (packet) entry so audio stations stay together."""
    data_subs = {sc.key for sc in p.subchannels() if sc.get('type') in ('packet', 'enhancedpacket', 'data')}
    data_svcs = {c.get('service') for c in p.components() if c.get('subchannel') in data_subs}
    data_comps = {c.key for c in p.components() if c.get('subchannel') in data_subs}
    keys = {'svc': data_svcs, 'sub': data_subs, 'comp': data_comps}[kind]
    for i, c in enumerate(parent.children or []):
        if c.key in keys:
            return i
    return None


def _last_encoder_section(p: Project):
    last = None
    for s in p.programs():
        if tool_of(s.argv) in ('audioenc', 'padenc'):
            last = s
    return last


def set_feed(p: Project, key, feed: str, opts: dict):
    """Switch a station between a local encoder and an external feed.

    local -> external: the encoder programs are *parked* (kept in the draft, not in
    supervisor) so switching back restores them exactly. The subchannel keeps listening on
    its port unless opts gives a new proto/port.
    external -> local: restore parked programs, or create a new encoder pair from opts.
    """
    st = _station_or_fail(p, key)
    sc = p.subchannel(st['subchannel_uid'])
    fs = []
    if feed == 'external':
        if st['feed'] != 'local':
            raise OpError('station is already fed externally')
        parked = {'programs': [], 'ptag': st['ptag'], 'port': st['port']}
        for name in (st['pad_program'], st['audio_program']):
            if not name:
                continue
            sec = p.program(name)
            tmp = SupervisorFile('')
            tmp.sections.append(sec)
            idx = sec.file.sections.index(sec)
            prev = sec.file.sections[idx - 1].name if idx > 0 else None
            parked['programs'].append({'file': sec.file.path if sec.file else None, 'text': tmp.dumps(),
                                       'name': name, 'after': prev})
            sec.file.remove_section(sec)
        p.parked[st['id']] = parked
        proto = opts.get('proto') or sc.get('inputproto') or 'edi'
        port = int(opts.get('port') or st['port'] or next_port(p))
        sc.set('inputproto', proto)
        sc.set('inputuri', opts.get('uri') or (f'tcp://0.0.0.0:{port}' if proto == 'edi' else f'tcp://*:{port}'),
               quoted=True)
        return fs
    if feed == 'local':
        if st['feed'] == 'local':
            raise OpError('station is already fed locally')
        port = st['port'] or int(opts.get('port') or next_port(p))
        if sc.get('inputproto') not in ('edi', 'zmq'):
            sc.set('inputproto', 'edi')
            sc.set('inputuri', f'tcp://0.0.0.0:{port}', quoted=True)
            for k, v in (('buffer-management', 'prebuffering'), ('buffer', '40'), ('prebuffering', '20')):
                if sc.get(k) is None:
                    sc.set(k, v)
        parked = p.parked.pop(st['id'], None)
        if parked and not opts.get('fresh'):
            after = None
            for prog in parked['programs']:
                f = p.sups.get(prog['file']) or encoder_file(p)
                tmp = SupervisorFile(prog['text'])
                first = False
                if after is None or after not in f.sections:
                    if prog.get('after') is None and 'after' in prog:
                        first = True
                    else:
                        after = next((x for x in f.sections if x.name == prog.get('after')), None) \
                            or _last_encoder_section(p)
                for sec in tmp.sections:
                    sec.file = f
                    if first:
                        idx = 0
                    else:
                        idx = f.sections.index(after) + 1 if after in f.sections else len(f.sections)
                    f.sections.insert(idx, sec)
                    after = sec
            # make sure the restored encoder points at the station's port
            st2 = p.station(key)
            if st2['feed'] != 'local' and st2['port'] != parked.get('port'):
                prog = p.program(parked['programs'][-1]['name'])
                a = Args.parse(prog.argv)
                a.set_all('edi', [f'tcp://127.0.0.1:{st2["port"]}'])
                a.set_all('output', [v for v in a.get_all('output') if not is_local(parse_tcp(v)[0])])
                prog.argv = a.to_argv()
            return fs
        ptag = (parked or {}).get('ptag') or next_ptag(p)
        enc = dict(opts.get('encoder') or {})
        enc.setdefault('codec', 'mp2' if sc.get('type') == 'audio' else 'auto')
        enc['bitrate'] = parse_int(sc.get('bitrate'), 64)
        _, _, f2 = create_encoders(p, st['label'] or 'station', ptag, port, enc, opts.get('pad') or {},
                                   after=_last_encoder_section(p))
        return f2
    raise OpError(f'unknown feed {feed}')
