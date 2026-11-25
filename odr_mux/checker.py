"""Configuration checker. Every issue is a dict:

    {severity: error|warning|info, code, message, ref: {...}, fix: optional fix id}
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import cu as cumod
from .encoders import Args, codec_of, tool_of, audio_outputs
from .infofile import parse_int, split_uri
from .project import Project, AUDIO_TYPES
from .secrets import has_secret
from .textfix import check_label, looks_mojibake


def _issue(sev, code, msg, fix=None, **ref):
    d = {'severity': sev, 'code': code, 'message': msg, 'ref': ref}
    if fix:
        d['fix'] = fix
    return d


def check(project: Project, check_fs: bool = False, manager_port: int | None = None, cu_warn_free: int = 0):
    out = []
    mux = project.mux

    # ---------------------------------------------------------------- capacity
    used = project.cu_used()
    if used > cumod.TOTAL_CU:
        out.append(_issue('error', 'cu-over', f'The mux needs {used} CU but only {cumod.TOTAL_CU} are available '
                          f'({used - cumod.TOTAL_CU} CU over). odr-dabmux will refuse to start.'))
    elif cumod.TOTAL_CU - used <= cu_warn_free:
        out.append(_issue('info', 'cu-full', f'{cumod.TOTAL_CU - used} CU free of {cumod.TOTAL_CU}.'))

    # ---------------------------------------------------------------- ensemble
    ens = project.sec('ensemble')
    if ens is None:
        out.append(_issue('error', 'no-ensemble', 'The mux has no ensemble section.'))
    else:
        for sev, msg in check_label(ens.get('label', ''), ens.get('shortlabel'), 'Ensemble'):
            out.append(_issue(sev, 'label', msg, fix='repair-labels' if 'garbled' in msg else None, section='ensemble'))
        eid = parse_int(ens.get('id'))
        if eid is None or not 0 <= eid <= 0xFFFF:
            out.append(_issue('error', 'eid', 'Ensemble id must be a 16-bit hex value like 0x2EA1.', section='ensemble'))

    # ---------------------------------------------------------------- services
    sids = Counter()
    for s in project.services():
        sid = s.get('id')
        if sid:
            sids[parse_int(sid)] += 1
        for sev, msg in check_label(s.get('label', ''), s.get('shortlabel'), f'Service {s.key}'):
            out.append(_issue(sev, 'label', msg, fix='repair-labels' if 'garbled' in msg else None, service=s.key))
        pty = parse_int(s.get('pty'))
        if pty is not None and not 0 <= pty <= 31:
            out.append(_issue('error', 'pty', f'Service {s.key}: PTY {pty} is out of range 0..31', service=s.key))
        if sid is None:
            out.append(_issue('error', 'sid', f'Service {s.key} has no id', service=s.key))
    for sid, n in sids.items():
        if n > 1 and sid is not None:
            out.append(_issue('error', 'sid-dup', f'Service id 0x{sid:04X} is used {n} times.'))
    for uid in project.orphan_services():
        out.append(_issue('warning', 'service-orphan', f'Service {uid} has no component, so it is not broadcast.', service=uid))

    # ---------------------------------------------------------------- components
    for c in project.components():
        if c.get('service') and project.service(c.get('service')) is None:
            out.append(_issue('error', 'comp-ref', f'Component {c.key} points at unknown service {c.get("service")}', component=c.key))
        if c.get('subchannel') and project.subchannel(c.get('subchannel')) is None:
            out.append(_issue('error', 'comp-ref', f'Component {c.key} points at unknown subchannel {c.get("subchannel")}', component=c.key))
        if c.get('label') is not None:
            for sev, msg in check_label(c.get('label', ''), c.get('shortlabel'), f'Component {c.key}'):
                out.append(_issue(sev, 'label', msg, component=c.key))
        sc = project.subchannel(c.get('subchannel') or '')
        if sc is not None and (sc.get('type') in ('packet', 'enhancedpacket')):
            if c.get('address') is None:
                out.append(_issue('warning', 'packet-address', f'Packet component {c.key} has no address.', component=c.key))

    # ---------------------------------------------------------------- subchannels
    ids, ports = Counter(), Counter()
    used_subs = {c.get('subchannel') for c in project.components()}
    for sc in project.subchannels():
        stype = sc.get('type', '')
        br = parse_int(sc.get('bitrate'), 0)
        for sev, msg in cumod.validate_protection(stype, sc.get('protection-profile'), br, parse_int(sc.get('protection'), 0)):
            out.append(_issue(sev, 'protection', f'{sc.key}: {msg}', subchannel=sc.key))
        if sc.get('id') is not None:
            sid = parse_int(sc.get('id'))
            ids[sid] += 1
            if sid is None or not 0 <= sid < 64:
                out.append(_issue('error', 'subch-id', f'{sc.key}: subchannel id must be 0..63', subchannel=sc.key))
        p = project.subch_port(sc)
        if p:
            ports[p] += 1
        if sc.key not in used_subs:
            out.append(_issue('warning', 'subch-orphan', f'Subchannel {sc.key} is not used by any component (it still takes {project.subch_cu(sc)} CU).', subchannel=sc.key))
        if stype not in ('audio', 'dabplus', 'packet', 'enhancedpacket', 'data', 'dmb'):
            out.append(_issue('error', 'subch-type', f'{sc.key}: unknown type "{stype}"', subchannel=sc.key))
        if check_fs and (sc.get('inputproto') in ('file',)):
            f = sc.get('inputuri') or ''
            if f and not Path(f).exists():
                out.append(_issue('warning', 'data-file', f'{sc.key}: input file {f} does not exist (yet).', subchannel=sc.key))
            elif f and stype in ('packet', 'enhancedpacket'):
                from .datfile import inspect
                comp = next((c for c in project.components() if c.get('subchannel') == sc.key and c.get('address')), None)
                try:
                    r = inspect(f, comp.get('address') if comp else None, limit=64 * 1024)
                    for msg in r.get('problems', []):
                        out.append(_issue('warning', 'data-file', f'{sc.key}: {msg}', subchannel=sc.key))
                except OSError:
                    pass
    eff = project.effective_subch_ids()
    seen = {}
    for uid, i in eff.items():
        if i is None:
            continue
        if i in seen:
            first = seen[i]
            auto = [u for u in (first, uid) if project.subchannel(u).get('id') is None]
            why = f' ({auto[0]} has no id line; odr-dabmux gives it {i} automatically)' if auto else ''
            out.append(_issue('error', 'subch-id-dup', f'Subchannel id {i} is used by {first} and {uid}{why}. '
                              f'odr-dabmux will refuse to start ("Subchannel {i} is set more than once").',
                              fix='fix-subch-ids', subchannel=uid))
        else:
            seen[i] = uid
    for p, n in ports.items():
        if n > 1:
            out.append(_issue('error', 'port-dup', f'Input port {p} is used by {n} subchannels.'))

    # listening ports clash
    listen = Counter()
    labels = {}

    def _l(port, what):
        if port:
            listen[port] += 1
            labels.setdefault(port, []).append(what)
    for p in ports:
        _l(p, f'input {p}')
    _l(parse_int(mux.get('general.managementport')), 'management port')
    _l(parse_int(mux.get('remotecontrol.telnetport')), 'telnet remote control')
    z = mux.get('remotecontrol.zmqendpoint')
    if z:
        d = split_uri(z)
        _l(d and d['port'], 'zmq remote control')
    outs = project.sec('outputs')
    if outs is not None:
        for n in _walk(outs):
            if n.key == 'listenport':
                _l(parse_int(n.value), 'EDI tcp output')
            elif n.key == 'zmq' and n.value:
                d = split_uri(n.value.replace('zmq+', ''))
                _l(d and d['port'], 'ZMQ output')
    if manager_port:
        _l(manager_port, 'ODR Mux Manager web UI')
    for p, n in listen.items():
        if n > 1:
            out.append(_issue('error', 'port-clash', f'Port {p} is used more than once: {", ".join(labels[p])}.'))

    # ---------------------------------------------------------------- stations vs encoders
    stations = project.stations()
    for st in stations:
        if st['kind'] != 'audio' or not st['encoder']:
            continue
        enc = st['encoder']
        ref = {'station': st['id'], 'program': st['audio_program']}
        if st['type'] == 'audio' and enc['codec'] != 'mp2':
            out.append(_issue('error', 'codec-mismatch', f'{st["label"]}: subchannel is MP2 (type audio) but the encoder makes DAB+ (no --dab).', **ref))
        if st['type'] == 'dabplus' and enc['codec'] == 'mp2':
            out.append(_issue('error', 'codec-mismatch', f'{st["label"]}: subchannel is DAB+ but the encoder makes MP2 (--dab).', **ref))
        if enc['bitrate'] and enc['bitrate'] != st['bitrate']:
            out.append(_issue('error', 'bitrate-mismatch', f'{st["label"]}: encoder bitrate {enc["bitrate"]} ≠ subchannel bitrate {st["bitrate"]}.',
                              fix='sync-encoder-bitrate', **ref))
        rate = enc['rate']
        if rate:
            okr = (24000, 48000) if enc['codec'] == 'mp2' else (32000, 48000)
            if rate not in okr:
                out.append(_issue('error', 'rate', f'{st["label"]}: sample rate {rate} is not valid for {"MP2" if enc["codec"] == "mp2" else "DAB+"} ({" / ".join(map(str, okr))}).', **ref))
        if enc['codec'] == 'mp2':
            a = Args.parse(project.program(st['audio_program']).argv)
            if a.has('sbr') or a.has('ps') or a.has('aaclc'):
                out.append(_issue('warning', 'codec-opts', f'{st["label"]}: --sbr/--ps/--aaclc do nothing for MP2.', **ref))
            if rate == 48000 and st['bitrate'] not in cumod.MP2_BITRATES_48K:
                out.append(_issue('error', 'mp2-bitrate', f'{st["label"]}: {st["bitrate"]} kbps is not a valid MP2 bitrate at 48 kHz.', **ref))
        else:
            if enc.get('dabpsy') is not None or enc.get('dabmode'):
                out.append(_issue('warning', 'codec-opts', f'{st["label"]}: --dabpsy/--dabmode only apply to MP2 (--dab).', **ref))
        pad = enc['pad']
        if pad is not None and pad != 0 and not (pad == 6 or 8 <= pad <= 196):
            out.append(_issue('error', 'pad-len', f'{st["label"]}: PAD length {pad} is not allowed (6, or 8..196).', **ref))
        if enc['pad_socket'] and not st['pad_program']:
            out.append(_issue('warning', 'pad-missing', f'{st["label"]}: audio encoder expects PAD socket "{enc["pad_socket"]}" but no odr-padenc writes to it.', **ref))
        if has_secret(enc.get('input') or ''):
            out.append(_issue('info', 'secret', f'{st["label"]}: the source URL contains a key/token. It is masked in the UI.', **ref))
        if enc['silence'] is None:
            out.append(_issue('info', 'no-silence', f'{st["label"]}: no --silence timeout; a dead stream will be broadcast as silence forever.', **ref))
        for o in enc['outputs']:
            if not o['local']:
                out.append(_issue('info', 'remote-output', f'{st["label"]}: also sends to {o["host"]}:{o["port"]} (another mux).', **ref))

    # programs: orphans, log names, merged lines
    known_ports = {project.subch_port(sc) for sc in project.subchannels()}
    pad_outs = set()
    socks = set()
    for p in project.programs():
        argv = p.argv
        t = tool_of(argv)
        if t == 'audioenc':
            a = Args.parse(argv)
            if a.get('pad-socket'):
                socks.add(a.get('pad-socket'))
            loc = [o for o in audio_outputs(a) if o['local']]
            if loc and not any(o['port'] in known_ports for o in loc):
                out.append(_issue('warning', 'encoder-orphan', f'{p.program} sends to port {loc[0]["port"]} but no subchannel listens there.', program=p.program))
        if t == 'padenc':
            pad_outs.add(Args.parse(argv).get('output'))
        log = p.get('stdout_logfile')
        if log and t in ('audioenc', 'padenc') and p.program not in Path(log).name:
            out.append(_issue('warning', 'log-name', f'{p.program} logs to {Path(log).name}, which does not match its name.', fix='fix-log-names', program=p.program))
        e = p.entry('command')
        if e and e.raw:
            for line in e.raw[1:]:
                if len(re.findall(r'(?:^|\s)--?[A-Za-z]', line.strip())) > 1:
                    out.append(_issue('warning', 'merged-opts', f'{p.program}: two options share one line ("{line.strip()}"). That works, but is easy to miss when editing.', program=p.program))
    for o in pad_outs - socks:
        if o:
            out.append(_issue('warning', 'pad-orphan', f'odr-padenc output "{o}" is not read by any audio encoder.'))

    # ---------------------------------------------------------------- linking
    lk = project.sec('linking')
    lsns = Counter()
    if lk is not None:
        for ls in lk.children or []:
            lsn = parse_int(ls.get('lsn'))
            lsns[lsn] += 1
            if lsn is None or not 0 < lsn <= 0xFFF:
                out.append(_issue('error', 'lsn', f'Linkage set {ls.key}: lsn must be 0x001..0xFFF', linkset=ls.key))
            ks = ls.get('keyservice')
            ksn = project.service(ks) if ks else None
            if ks and ksn is None:
                out.append(_issue('error', 'link-key', f'Linkage set {ls.key}: key service {ks} does not exist', linkset=ls.key))
            lst = ls.child('list')
            for item in (lst.children if lst is not None and lst.children else []):
                if item.get('type') == 'dab' and ksn is not None and parse_int(item.get('id')) == parse_int(ksn.get('id')) \
                        and (item.get('ecc') is None or parse_int(item.get('ecc')) == parse_int(ksn.get('ecc') or (ens.get('ecc') if ens else None))):
                    out.append(_issue('warning', 'link-self', f'Linkage set {ls.key}: entry {item.key} links {ks} to its own SId {item.get("id")}.', linkset=ls.key))
                if item.get('type') not in ('dab', 'fm', 'drm', 'amss'):
                    out.append(_issue('error', 'link-type', f'Linkage set {ls.key}: entry {item.key} has unknown type {item.get("type")}', linkset=ls.key))
        for lsn, n in lsns.items():
            if n > 1 and lsn is not None:
                out.append(_issue('error', 'lsn-dup', f'Linkage set number 0x{lsn:03X} is used {n} times.'))

    # ---------------------------------------------------------------- announcements
    if ens is not None:
        an = ens.child('announcements')
        for cl in (an.children if an is not None and an.children else []):
            sc = cl.get('subchannel')
            if sc and project.subchannel(sc) is None:
                out.append(_issue('error', 'ann-sub', f'Announcement cluster {cl.key}: subchannel {sc} does not exist', cluster=cl.key))

    # ---------------------------------------------------------------- values odr-dabmux parses with hexparse()
    out += _hex_value_checks(project)

    order = {'error': 0, 'warning': 1, 'info': 2}
    out.sort(key=lambda i: order[i['severity']])
    return out


def _walk(n):
    for c in n.children or []:
        yield c
        yield from _walk(c)


# ------------------------------------------------------------------ fixes
def apply_fix(project: Project, fix: str):
    from .textfix import repair_mojibake
    changed = []
    if fix == 'repair-labels':
        nodes = [project.sec('ensemble')] + project.services() + project.components()
        for n in nodes:
            if n is None:
                continue
            for k in ('label', 'shortlabel'):
                v = n.get(k)
                if v and looks_mojibake(v):
                    n.set(k, repair_mojibake(v))
                    changed.append(f'{n.key}.{k}')
    elif fix == 'drop-empty':
        for n in list(_walk(project.mux.root)):
            if n.children is None and n.value is not None and n.value.strip() == '' and n.parent is not None:
                n.parent.remove(n)
                changed.append(_path(n) if n.parent else n.key)
    elif fix == 'fix-subch-ids':
        # give every subchannel without an id line its explicit (current automatic) id, then move
        # later duplicates to free ids
        eff = project.effective_subch_ids()
        for sc in project.subchannels():
            if sc.get('id') is None and eff.get(sc.key) is not None:
                sc.set('id', str(eff[sc.key]))
        used = set()
        for sc in project.subchannels():
            i = parse_int(sc.get('id'))
            if i in used:
                new = next(k for k in range(1, 64) if k not in used and k not in
                           {parse_int(x.get('id')) for x in project.subchannels()})
                sc.set('id', str(new))
                changed.append(f'{sc.key}: id {i} -> {new}')
                i = new
            used.add(i)
    elif fix == 'sync-encoder-bitrate':
        # the subchannel decides the capacity, so the encoder follows it
        for st in project.stations():
            if st['kind'] != 'audio' or not st['audio_program'] or not st['encoder']:
                continue
            if st['encoder']['bitrate'] and st['encoder']['bitrate'] != st['bitrate']:
                prog = project.program(st['audio_program'])
                a = Args.parse(prog.argv)
                a.set('bitrate', str(st['bitrate']))
                prog.argv = a.to_argv()
                changed.append(f'{st["audio_program"]}: bitrate {st["encoder"]["bitrate"]} -> {st["bitrate"]}')
    elif fix == 'fix-log-names':
        for p in project.programs():
            log = p.get('stdout_logfile')
            if log and tool_of(p.argv) in ('audioenc', 'padenc') and p.program not in Path(log).name:
                newlog = str(Path(log).with_name(p.program + '.log'))
                p.set('stdout_logfile', newlog)
                changed.append(p.program)
    return changed


# keys odr-dabmux reads with hexparse() (decimal or 0x-hex, nothing else), per section
_HEX_KEYS = {
    'ensemble': {'id', 'ecc', 'fig2_label_character_flag'},
    'services': {'id', 'ecc', 'pty', 'language'},
    'subchannels': {'id'},
    'components': {'type', 'figtype', 'address'},
    'linking': {'lsn', 'id', 'ecc'},
    'frequency_information': {'eid', 'pi_code', 'drm_id', 'amss_id'},
    'other-services': {'id'},
    'service-component-information': {'id', 'transfer_sid', 'transfer_eid'},
}
_HEX_RE = __import__('re').compile(r'^(0x[0-9a-fA-F]+|[0-9]+)$')


def _hex_value_checks(project):
    out = []
    for sec, keys in _HEX_KEYS.items():
        root = project.sec(sec) if sec != 'ensemble' else project.sec('ensemble')
        if root is None:
            continue
        nodes = [root] if sec == 'ensemble' else list(_walk(root))
        for n in nodes:
            for c in (n.children or []) if sec == 'ensemble' else [n]:
                if c.children is not None or c.key not in keys:
                    continue
                v = (c.value or '').strip()
                if not _HEX_RE.match(v):
                    where = _path(c)
                    what = 'is empty' if not v else f'is "{v}", which is not a number'
                    out.append(_issue('error', 'bad-number', f'{where} {what}. odr-dabmux will refuse to start '
                                      f'("hexparse"). Use decimal or 0x-hex, or remove the line.', fix='drop-empty'
                                      if not v else None, path=where))
    for n in _walk(project.mux.root):
        if n.children is None and n.value is not None and n.value.strip() == '' and n.key not in ('label', 'shortlabel'):
            p = _path(n)
            if not any(i['ref'].get('path') == p for i in out):
                out.append(_issue('warning', 'empty-value', f'{p} has an empty value.', fix='drop-empty', path=p))
    for svc in project.services():
        an = svc.child('announcements')
        if an is not None and an.children and not (an.get('clusters') or '').strip() \
                and any((c.value or '') == 'true' for c in an.children if c.key != 'clusters'):
            out.append(_issue('warning', 'ann-no-cluster', f'Service {svc.key} takes part in announcements but has no '
                              f'cluster list, so it will not follow any announcement.', service=svc.key))
    return out


def _path(n):
    parts = []
    while n is not None and n.key:
        parts.append(n.key)
        n = n.parent
    return '.'.join(reversed(parts))
