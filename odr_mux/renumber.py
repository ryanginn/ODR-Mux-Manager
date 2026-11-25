"""Remove / reorder stations, optionally closing number gaps ("station 10 moves to 9").

Numbers are tied to *positions*: when the station order changes, each station takes the
numbers of the position it moves into. Each numbered attribute has its own pool, so irregular
setups (P04 feeding sub-03, port 2492 on sub-02) are handled attribute by attribute:

* uids  - srv-NN / sub-NN / comp-NN (and comp-NN-sub secondary components)
* subch - the subchannel ``id``
* port  - input port of locally fed stations (external feeds keep their port: somebody
          else's encoder sends to it)
* ptag  - the P## folder/tag used in mot/P##, stats files, DLS paths and comments
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .encoders import Args, parse_tcp, is_local, tool_of
from .infofile import Node, parse_int, with_port
from .project import Project

_PTAG_RE = r'(?<![A-Za-z0-9]){}(?![0-9])'


class RenumberError(ValueError):
    pass


def _uid_parts(uid):
    m = re.match(r'^(?P<pre>[A-Za-z_\-]*?-?)(?P<num>\d+)(?P<suf>(-sub)?)$', uid or '')
    if not m:
        return None
    return m.group('pre'), int(m.group('num')), len(m.group('num')), m.group('suf')


def plan(p: Project, order: List[str], remove: List[str] = (), mode: str = 'renumber') -> dict:
    """Compute the change plan without touching the project."""
    stations = [s for s in p.stations() if s['kind'] in ('audio', 'dmb')]
    by_id = {s['id']: s for s in stations}
    for k in list(order) + list(remove):
        if k not in by_id:
            raise RenumberError(f'unknown station {k}')
    remove = list(dict.fromkeys(remove))
    keep = [k for k in order if k not in remove]
    missing = [s['id'] for s in stations if s['id'] not in keep and s['id'] not in remove]
    keep += missing  # stations not mentioned keep their relative order at the end
    old_order = [s['id'] for s in stations]

    changes: Dict[str, List[dict]] = {k: [] for k in keep}
    assign: Dict[str, dict] = {k: {} for k in keep}

    if mode == 'renumber':
        def pool(attr_fn, participates=lambda s: True):
            vals = [(s['id'], attr_fn(s)) for s in stations]
            vals = [(k, v) for k, v in vals if v is not None and participates(by_id[k])]
            ids = {k for k, _ in vals}
            seq = [v for _, v in vals]
            new_seq = [k for k in keep if k in ids]
            return {k: seq[i] for i, k in enumerate(new_seq)}

        def num_of(uid_key):
            def f(s):
                u = s.get(uid_key)
                parts = _uid_parts(u)
                return parts[1] if parts else None
            return f

        for attr, fn, part in (
            ('srv', num_of('service_uid'), None),
            ('sub', num_of('subchannel_uid'), None),
            ('comp', num_of('component_uid'), None),
            ('subch_id', lambda s: parse_int((s['subchannel'] or {}).get('id')), None),
            ('port', lambda s: s['port'], lambda s: s['feed'] == 'local'),
            ('ptag', lambda s: int(s['ptag'][1:]) if s['ptag'] else None, lambda s: s['feed'] == 'local'),
        ):
            m = pool(fn, part or (lambda s: True))
            for k, v in m.items():
                assign[k][attr] = v

    result_stations = []
    for pos, k in enumerate(keep, 1):
        s = by_id[k]
        a = assign[k]
        ch = []

        def _c(what, old, new, note=None):
            if old != new and new is not None:
                ch.append({'what': what, 'old': old, 'new': new, **({'note': note} if note else {})})

        if 'srv' in a:
            for key, attr in (('service_uid', 'srv'), ('subchannel_uid', 'sub'), ('component_uid', 'comp')):
                parts = _uid_parts(s[key])
                if parts and attr in a:
                    _c(key.replace('_uid', ''), s[key], f'{parts[0]}{a[attr]:0{parts[2]}d}{parts[3]}')
            _c('subchannel id', parse_int((s['subchannel'] or {}).get('id')), a.get('subch_id'))
            _c('input port', s['port'], a.get('port'))
            if s['ptag'] and 'ptag' in a:
                w = len(s['ptag']) - 1
                _c('P tag', s['ptag'], f'P{a["ptag"]:0{w}d}')
        result_stations.append({'id': k, 'label': s['label'], 'old_position': old_order.index(k) + 1,
                                'new_position': pos, 'changes': ch, 'feed': s['feed']})

    removed = [{'id': k, 'label': by_id[k]['label'], 'position': old_order.index(k) + 1} for k in remove]
    return {'mode': mode, 'stations': result_stations, 'removed': removed,
            'impact': impact_report(p, by_id, result_stations, removed)}


def impact_report(p: Project, by_id, result_stations, removed) -> List[dict]:
    """What must be repointed *outside* the manager, per affected station."""
    out = []
    for r in result_stations:
        s = by_id[r['id']]
        items = []
        for c in r['changes']:
            if c['what'] == 'P tag':
                enc = s.get('encoder') or {}
                md = enc.get('mot_dir') or s.get('mot_dir')
                newmd = md.replace(c['old'], c['new']) if md else None
                if md:
                    items.append(f'MOT folder moves {md} → {newmd}: point any script that writes DLS text or '
                                 f'slides for this station at the new folder.')
                if enc.get('stats'):
                    items.append(f'Stats socket {enc["stats"]} → {enc["stats"].replace(c["old"], c["new"])}: '
                                 f'update any level meter or monitoring that reads it.')
                if enc.get('icy_text'):
                    items.append(f'ICY text file {enc["icy_text"]} moves with the folder; anything that reads it '
                                 f'must follow.')
            elif c['what'] == 'input port':
                items.append(f'Input port {c["old"]} → {c["new"]}. The local encoder is updated for you; '
                             f'firewall rules or anything else sending to port {c["old"]} must change.')
            elif c['what'] in ('service', 'subchannel', 'component'):
                items.append(f'{c["what"].title()} {c["old"]} → {c["new"]}: scripts that use odr-dabmux remote '
                             f'control or the management port by name ({c["old"]}) must use {c["new"]}.')
            elif c['what'] == 'subchannel id':
                items.append(f'Subchannel id {c["old"]} → {c["new"]}: receivers will rescan this service.')
        enc = s.get('encoder') or {}
        for o in enc.get('outputs', []):
            if not o['local'] and r['changes']:
                items.append(f'Also feeds {o["host"]}:{o["port"]} (another mux) - not changed here, check that mux.')
        if items:
            out.append({'id': r['id'], 'label': r['label'], 'items': items})
    for rm in removed:
        s = by_id[rm['id']]
        items = ['Service, subchannel and components are removed from the mux.']
        if s['audio_program']:
            items.append(f'Encoders {s["pad_program"] or ""} {s["audio_program"]} are removed from supervisor '
                         f'(stopped on Apply).'.replace('  ', ' '))
        if s.get('mot_dir'):
            items.append(f'MOT folder {s["mot_dir"]} is archived to {Path(s["mot_dir"]).parent}/_removed/.')
        if s['feed'] == 'external':
            items.append(f'Whoever sends to port {s["port"]} should stop.')
        for ls in _linksets_for(p, s['service_uid']):
            items.append(f'Linkage set {ls} uses this service as key service and is removed.')
        if s['secondary_components']:
            items.append('Secondary components on this subchannel are removed: ' +
                         ', '.join(c['uid'] for c in s['secondary_components']))
        sec_of_service = [c.key for c in p.components() if c.get('service') == s['service_uid']
                          and c.get('subchannel') != s['subchannel_uid']]
        if sec_of_service:
            items.append('Components of this service on other subchannels are removed: ' + ', '.join(sec_of_service))
        out.append({'id': rm['id'], 'label': rm['label'], 'removed': True, 'items': items})
    return out


def _linksets_for(p: Project, svc_uid):
    lk = p.sec('linking')
    if lk is None or not svc_uid:
        return []
    return [ls.key for ls in lk.children or [] if ls.get('keyservice') == svc_uid]


# ------------------------------------------------------------------ apply to project
def apply(p: Project, order: List[str], remove: List[str] = (), mode: str = 'renumber',
          archive_stamp: Optional[str] = None) -> dict:
    pl = plan(p, order, remove, mode)
    stations = {s['id']: s for s in p.stations()}
    fs: List[dict] = []
    stamp = archive_stamp or time.strftime('%Y%m%d-%H%M%S')

    # 1. removals
    for rm in pl['removed']:
        s = stations[rm['id']]
        _remove_station(p, s, fs, stamp)

    # 2. order of blocks (services/subchannels/components)
    keep_ids = [r['id'] for r in pl['stations']]
    _reorder_blocks(p, [stations[k] for k in keep_ids])

    # 3. renumber
    if mode == 'renumber':
        uid_map: Dict[str, str] = {}
        folder_moves = []
        for r in pl['stations']:
            s = stations[r['id']]
            for c in r['changes']:
                if c['what'] in ('service', 'subchannel', 'component'):
                    uid_map[c['old']] = c['new']
            # secondary components named after the subchannel number (comp-06-sub)
            subc = next((c for c in r['changes'] if c['what'] == 'subchannel'), None)
            if subc:
                o = _uid_parts(subc['old'])
                n = _uid_parts(subc['new'])
                for sc in s['secondary_components']:
                    pp = _uid_parts(sc['uid'])
                    if pp and o and pp[1] == o[1]:
                        uid_map[sc['uid']] = f'{pp[0]}{n[1]:0{pp[2]}d}{pp[3]}'
        _rename_uids(p, uid_map)
        for r in pl['stations']:
            s = stations[r['id']]
            for c in r['changes']:
                if c['what'] == 'subchannel id':
                    p.subchannel(uid_map.get(s['subchannel_uid'], s['subchannel_uid'])).set('id', str(c['new']))
                elif c['what'] == 'input port':
                    sc = p.subchannel(uid_map.get(s['subchannel_uid'], s['subchannel_uid']))
                    sc.set('inputuri', with_port(sc.get('inputuri'), c['new']), quoted=True)
                    if s['audio_program']:
                        prog = p.program(s['audio_program'])
                        a = Args.parse(prog.argv)
                        for opt in ('edi', 'output'):
                            vals = []
                            for v in a.get_all(opt):
                                h, port = parse_tcp(v)
                                vals.append(with_port(v, c['new']) if is_local(h) and port == c['old'] else v)
                            if vals:
                                a.set_all(opt, vals)
                        prog.argv = a.to_argv()
                elif c['what'] == 'P tag':
                    for name in (s['audio_program'], s['pad_program']):
                        if name:
                            _retag_program(p.program(name), c['old'], c['new'])
                    md = s.get('mot_dir')
                    if md:
                        newmd = re.sub(_PTAG_RE.format(re.escape(c['old'])), c['new'], md)
                        if newmd != md:
                            folder_moves.append((md, newmd))
        if folder_moves:
            fs.append({'op': 'move_many', 'moves': [{'from': a, 'to': b} for a, b in folder_moves]})
    pl['fs'] = fs
    return pl


def _retag_program(sec, old, new):
    rx = re.compile(_PTAG_RE.format(re.escape(old)))
    argv = sec.argv
    new_argv = [rx.sub(new, x) for x in argv]
    if new_argv != argv:
        sec.argv = new_argv
    if sec.comment_tag and rx.search(sec.comment_tag):
        sec.comment_tag = rx.sub(new, sec.comment_tag)
    for k in ('stdout_logfile', 'stderr_logfile'):
        v = sec.get(k)
        if v and rx.search(v):
            sec.set(k, rx.sub(new, v))


def _rename_uids(p: Project, m: Dict[str, str]):
    if not m:
        return
    for secname in ('services', 'subchannels', 'components'):
        sec = p.sec(secname)
        for n in (sec.children if sec is not None and sec.children else []):
            if n.key in m:
                n.rename(m[n.key])
    for c in p.components():
        for k in ('service', 'subchannel'):
            v = c.get(k)
            if v in m:
                c.set(k, m[v])
    lk = p.sec('linking')
    for ls in (lk.children if lk is not None and lk.children else []):
        if ls.get('keyservice') in m:
            ls.set('keyservice', m[ls.get('keyservice')])
    ens = p.sec('ensemble')
    an = ens.child('announcements') if ens is not None else None
    for cl in (an.children if an is not None and an.children else []):
        if cl.get('subchannel') in m:
            cl.set('subchannel', m[cl.get('subchannel')])


def _reorder_blocks(p: Project, stations: List[dict]):
    def reorder(secname, keys_in_order):
        sec = p.sec(secname)
        if sec is None or not sec.children:
            return
        wanted = [k for k in keys_in_order if sec.child(k) is not None]
        slots = [i for i, c in enumerate(sec.children) if c.key in set(wanted)]
        nodes = {c.key: c for c in sec.children}
        for i, k in zip(slots, wanted):
            sec.children[i] = nodes[k]
    reorder('services', [s['service_uid'] for s in stations if s['service_uid']])
    reorder('subchannels', [s['subchannel_uid'] for s in stations])
    comp_keys = []
    for s in stations:
        if s['component_uid']:
            comp_keys.append(s['component_uid'])
        comp_keys += [c['uid'] for c in s['secondary_components']]
    reorder('components', comp_keys)


def _remove_station(p: Project, s: dict, fs: List[dict], stamp: str):
    svc_uid, sc_uid = s['service_uid'], s['subchannel_uid']
    comps = p.sec('components')
    for c in list(comps.children if comps is not None and comps.children else []):
        if c.get('subchannel') == sc_uid or (svc_uid and c.get('service') == svc_uid):
            comps.remove(c)
    if p.sec('subchannels') is not None:
        p.sec('subchannels').remove(sc_uid)
    if svc_uid and p.sec('services') is not None:
        p.sec('services').remove(svc_uid)
    lk = p.sec('linking')
    for ls in list(lk.children if lk is not None and lk.children else []):
        if ls.get('keyservice') == svc_uid:
            lk.remove(ls)
    ens = p.sec('ensemble')
    an = ens.child('announcements') if ens is not None else None
    for cl in list(an.children if an is not None and an.children else []):
        if cl.get('subchannel') == sc_uid:
            an.remove(cl)
    for name in (s['pad_program'], s['audio_program'], s.get('dmb_program')):
        if name:
            sec = p.program(name)
            if sec is not None:
                sec.file.remove_section(sec)
            fs.append({'op': 'stop_program', 'name': name})
    p.parked.pop(s['id'], None)
    md = s.get('mot_dir')
    if md:
        fs.append({'op': 'archive', 'path': md, 'to': str(Path(md).parent / '_removed' / f'{Path(md).name}-{stamp}')})
