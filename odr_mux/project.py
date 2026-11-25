"""The mux project: a .mux file plus supervisor encoder configs, and the station view joining them.

A *station* is an audio subchannel together with its primary service/component and, when the
station is fed locally, its odr-audioenc / odr-padenc supervisor programs (matched by port).
Stations fed from elsewhere (an EDI/ZMQ input that no local encoder sends to) are "external":
we never invent encoders for them.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import cu as cumod
from .encoders import (Args, audio_outputs, codec_of, effective_codec, input_of, parse_tcp, is_local, tool_of)
from .infofile import InfoDoc, Node, parse_int, parse_bool, split_uri
from .supervisor_conf import Section, SupervisorFile

AUDIO_TYPES = ('audio', 'dabplus')
DATA_TYPES = ('packet', 'enhancedpacket', 'data', 'dmb')

_PTAG = re.compile(r'(?<![A-Za-z0-9])P(\d{1,3})(?![0-9])')
_NUMSUFFIX = re.compile(r'^(?P<prefix>.*?)(?P<num>\d+)(?P<suffix>(?:-sub)?)$')


def find_mux_files(root: Path) -> List[Path]:
    return sorted(Path(p) for p in glob.glob(str(root / '*.mux')))


def find_supervisor_files(root: Path) -> List[Path]:
    out = []
    for pat in ('supervisor/*.conf', 'supervisor/conf.d/*.conf', '*.supervisor.conf'):
        out += [Path(p) for p in glob.glob(str(root / pat))]
    return sorted(set(out))


class Project:
    """Holds parsed files. Use :meth:`texts` / :meth:`from_texts` to snapshot a draft."""

    def __init__(self, root, mux_path, sup_paths, mux: InfoDoc, sups: Dict[str, SupervisorFile],
                 parked: Optional[dict] = None, settings: Optional[dict] = None):
        self.root = Path(root)
        self.mux_path = Path(mux_path)
        self.sup_paths = [str(p) for p in sup_paths]
        self.mux = mux
        self.sups = sups
        self.parked = parked or {}          # sid -> {"programs": [text...], "file": path}
        self.settings = settings or {}

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, root, mux_path=None, sup_paths=None, **kw) -> 'Project':
        root = Path(root)
        if mux_path is None:
            cand = [p for p in find_mux_files(root) if p.name == 'conf.mux'] or find_mux_files(root)
            if not cand:
                raise FileNotFoundError(f'no .mux file found in {root}')
            mux_path = cand[0]
        if sup_paths is None:
            sup_paths = find_supervisor_files(root)
        mux = InfoDoc.load(mux_path)
        sups = {str(p): SupervisorFile.load(p) for p in sup_paths}
        return cls(root, mux_path, sup_paths, mux, sups, **kw)

    def texts(self) -> dict:
        return {'mux': self.mux.dumps(), 'sups': {p: f.dumps() for p, f in self.sups.items()},
                'parked': copy.deepcopy(self.parked)}

    @classmethod
    def from_texts(cls, root, mux_path, texts: dict, settings=None) -> 'Project':
        sups = {p: SupervisorFile(t, p) for p, t in texts['sups'].items()}
        return cls(root, mux_path, list(texts['sups'].keys()), InfoDoc(texts['mux']), sups,
                   parked=copy.deepcopy(texts.get('parked') or {}), settings=settings)

    # ---------------------------------------------------------------- sections
    def sec(self, name, create=False) -> Optional[Node]:
        return self.mux.section(name, create=create)

    def services(self) -> List[Node]:
        s = self.sec('services')
        return list(s.children) if s and s.children else []

    def subchannels(self) -> List[Node]:
        s = self.sec('subchannels')
        return list(s.children) if s and s.children else []

    def components(self) -> List[Node]:
        s = self.sec('components')
        return list(s.children) if s and s.children else []

    def service(self, uid) -> Optional[Node]:
        s = self.sec('services')
        return s.child(uid) if s else None

    def subchannel(self, uid) -> Optional[Node]:
        s = self.sec('subchannels')
        return s.child(uid) if s else None

    def component(self, uid) -> Optional[Node]:
        s = self.sec('components')
        return s.child(uid) if s else None

    # ---------------------------------------------------------------- programs
    def programs(self) -> List[Section]:
        out = []
        for f in self.sups.values():
            out += f.programs()
        return out

    def program(self, name) -> Optional[Section]:
        for f in self.sups.values():
            p = f.program(name)
            if p:
                return p
        return None

    def dabmux_program(self) -> Optional[Section]:
        for p in self.programs():
            if tool_of(p.argv) == 'dabmux':
                return p
        return None

    # ---------------------------------------------------------------- derived
    def subch_cu(self, sc: Node) -> int:
        return cumod.cu_for(sc.get('type', ''), parse_int(sc.get('bitrate'), 0),
                            sc.get('protection-profile'), parse_int(sc.get('protection'), 0))

    def cu_used(self) -> int:
        return sum(self.subch_cu(sc) for sc in self.subchannels())

    def subch_port(self, sc: Node):
        proto = (sc.get('inputproto') or '').lower()
        uri = sc.get('inputuri') or ''
        if proto in ('edi', 'zmq', 'udp', 'stp') or uri.startswith(('tcp://', 'udp://', 'zmq+tcp://', 'rtp://')):
            d = split_uri(uri)
            if d:
                return d['port']
        return None

    def _index(self):
        """Build lookups used by stations(): components by subchannel, encoders by port."""
        comps_by_sub: Dict[str, List[Node]] = {}
        for c in self.components():
            s = c.get('subchannel')
            if s:
                comps_by_sub.setdefault(s, []).append(c)
        audio_by_port: Dict[int, Section] = {}
        pad_by_out: Dict[str, Section] = {}
        dmb_by_port: Dict[int, Section] = {}
        for p in self.programs():
            argv = p.argv
            t = tool_of(argv)
            if t == 'audioenc':
                a = Args.parse(argv)
                for o in audio_outputs(a):
                    if o['local'] and o['port']:
                        audio_by_port.setdefault(o['port'], p)
            elif t == 'padenc':
                a = Args.parse(argv)
                out = a.get('output')
                if out:
                    pad_by_out.setdefault(out, p)
            elif t == 'manager' and 'dmb-encode' in argv:
                for i, x in enumerate(argv):
                    if x.startswith('--udp='):
                        h, _, port = x[6:].rpartition(':')
                        if port.isdigit():
                            dmb_by_port[int(port)] = p
        return comps_by_sub, audio_by_port, pad_by_out, dmb_by_port

    @staticmethod
    def _primary_component(cands: List[Node]) -> Optional[Node]:
        if not cands:
            return None
        for c in cands:
            if c.child('label') is None:
                return c
        return cands[0]

    def stations(self, include_data=True) -> List[dict]:
        comps_by_sub, audio_by_port, pad_by_out, dmb_by_port = self._index()
        svc_order = {s.key: i for i, s in enumerate(self.services())}
        stations = []
        used_services = set()
        for sc in self.subchannels():
            stype = (sc.get('type') or '').lower()
            cands = comps_by_sub.get(sc.key, [])
            prim = self._primary_component(cands)
            svc = self.service(prim.get('service')) if prim else None
            if svc is not None:
                used_services.add(svc.key)
            port = self.subch_port(sc)
            audio = audio_by_port.get(port) if port and stype in AUDIO_TYPES else None
            pad = None
            aargs = Args.parse(audio.argv) if audio else None
            if aargs is not None:
                sock = aargs.get('pad-socket')
                if sock:
                    pad = pad_by_out.get(sock)
            dmbp = dmb_by_port.get(port) if port and stype == 'dmb' else None
            st = self._station_dict(sc, svc, prim, [c for c in cands if c is not prim], audio, pad, aargs, dmbp)
            st['order'] = svc_order.get(svc.key, 10_000 + len(stations)) if svc is not None else 10_000 + len(stations)
            if not include_data and st['kind'] != 'audio':
                continue
            stations.append(st)
        stations.sort(key=lambda s: s['order'])
        for i, s in enumerate(stations):
            s['position'] = i + 1
        return stations

    def station(self, key) -> Optional[dict]:
        for s in self.stations():
            if s['id'] == key or s['subchannel_uid'] == key or s['service_uid'] == key:
                return s
        return None

    def orphan_services(self) -> List[str]:
        used = {c.get('service') for c in self.components()}
        return [s.key for s in self.services() if s.key not in used]

    def _station_dict(self, sc, svc, prim, secondary, audio, pad, aargs, dmbp) -> dict:
        stype = (sc.get('type') or '').lower()
        bitrate = parse_int(sc.get('bitrate'), 0)
        level = parse_int(sc.get('protection'), 0)
        profile = sc.get('protection-profile')
        kind = 'audio' if stype in AUDIO_TYPES else 'dmb' if stype == 'dmb' else 'data'
        port = self.subch_port(sc)
        d = {
            'id': station_key(svc, sc),
            'kind': kind,
            'service': self._node_fields(svc) if svc is not None else None,
            'service_uid': svc.key if svc is not None else None,
            'component_uid': prim.key if prim is not None else None,
            'component': self._node_fields(prim) if prim is not None else None,
            'subchannel_uid': sc.key,
            'subchannel': self._node_fields(sc),
            'secondary_components': [{'uid': c.key, **self._node_fields(c)} for c in secondary],
            'type': stype,
            'bitrate': bitrate,
            'protection': cumod.protection_label(stype, profile, bitrate, level),
            'cu': self.subch_cu(sc),
            'inputproto': sc.get('inputproto'),
            'inputuri': sc.get('inputuri'),
            'port': port,
            'label': svc.get('label') if svc is not None else (prim.get('label') if prim is not None else sc.key),
            'shortlabel': svc.get('shortlabel') if svc is not None else None,
            'feed': 'local' if (audio is not None or dmbp is not None) else ('file' if (sc.get('inputproto') or '') in ('file', 'fifo') else 'external'),
            'audio_program': audio.program if audio else None,
            'pad_program': pad.program if pad else None,
            'dmb_program': dmbp.program if dmbp else None,
            'encoder': None,
            'mot_dir': None,
            'ptag': None,
            'codec': None,
        }
        if stype == 'audio':
            d['codec'] = 'mp2'
        elif stype == 'dabplus':
            d['codec'] = 'dabplus'
        if aargs is not None:
            enc = self.encoder_summary(aargs, Args.parse(pad.argv) if pad else None)
            d['encoder'] = enc
            d['codec'] = enc['codec']
            d['mot_dir'] = enc.get('mot_dir')
        d['ptag'] = self._ptag(d, audio, pad)
        if d['feed'] == 'external' and d['id'] in self.parked:
            d['parked'] = True
        return d

    def _ptag(self, d, audio, pad):
        texts = []
        if pad is not None:
            texts += pad.argv
            if pad.comment_tag:
                texts.append(pad.comment_tag)
        if audio is not None:
            texts += audio.argv
            if audio.comment_tag:
                texts.append(audio.comment_tag)
        for t in texts:
            m = _PTAG.search(t)
            if m:
                return 'P' + m.group(1)
        return None

    @staticmethod
    def _node_fields(n: Optional[Node]) -> dict:
        if n is None:
            return {}
        return n.to_dict() if n.children is not None else {}

    def encoder_summary(self, a: Args, p: Optional[Args]) -> dict:
        kind, opt, uri = input_of(a)
        d = {
            'input_kind': kind, 'input_opt': opt, 'input': uri,
            'codec': effective_codec(a),
            'codec_auto': codec_of(a) == 'auto',
            'bitrate': parse_int(a.get('bitrate')),
            'rate': parse_int(a.get('rate')),
            'channels': parse_int(a.get('channels')),
            'dabmode': a.get('dabmode'),
            'dabpsy': parse_int(a.get('dabpsy')),
            'pad': parse_int(a.get('pad')),
            'pad_socket': a.get('pad-socket'),
            'silence': parse_int(a.get('silence')),
            'drift_comp': a.has('drift-comp'),
            'afterburner': not a.has('no-afterburner'),
            'bandwidth': parse_int(a.get('bandwidth')),
            'audio_gain': a.get('audio-gain'),
            'icy_text': a.get('write-icy-text'),
            'icy_dlplus': a.has('write-icy-text-dl-plus'),
            'stats': a.get('stats'),
            'outputs': audio_outputs(a),
            'identifier': a.get('identifier'),
            'vlc_cache': a.get('vlc-cache'),
        }
        if p is not None:
            dls = p.get_all('dls')
            d.update({
                'slide_dir': p.get('dir'),
                'sleep': parse_int(p.get('sleep')),
                'dls_files': dls,
                'label': p.get('label'),
                'label_ins': p.get('label-ins'),
                'raw_slides': p.has('raw-slides'),
                'erase': p.has('erase'),
                'charset': p.get('charset'),
                'item_state': p.get('item-state'),
            })
            md = None
            sd = p.get('dir')
            if sd:
                sp = Path(sd.rstrip('/'))
                md = str(sp.parent if sp.name in ('slide', 'slides', 'sls') else sp)
            elif dls:
                md = str(Path(dls[0]).parent)
            d['mot_dir'] = md
        return d

    # ---------------------------------------------------------------- ensemble
    def ensemble(self) -> dict:
        e = self.sec('ensemble')
        return self._node_fields(e)

    def summary(self) -> dict:
        sts = self.stations()
        used = self.cu_used()
        return {
            'mux_path': str(self.mux_path),
            'supervisor_files': list(self.sups.keys()),
            'ensemble': self.ensemble(),
            'cu_used': used,
            'cu_total': cumod.TOTAL_CU,
            'cu_free': cumod.TOTAL_CU - used,
            'stations': sts,
            'orphan_services': self.orphan_services(),
            'dabmux_program': (self.dabmux_program().program if self.dabmux_program() else None),
        }


# -------------------------------------------------------------------- tree <-> json merge
def merge_json(node: Node, data: dict, remove_missing=True):
    """Apply a JSON dict to a block node, keeping comments/order of nodes that stay.

    Values: str/int/bool -> leaf; dict -> block; list -> repeated keys (of leaves or blocks).
    ``_value`` inside a dict sets the block's own value.
    """
    if node.children is None:
        node.children = []
    if '_value' in data:
        node.value = None if data['_value'] is None else str(data['_value'])
    seen = set()
    for key, val in data.items():
        if key == '_value':
            continue
        seen.add(key)
        existing = [c for c in node.children if c.key == key]
        vals = val if isinstance(val, list) else [val]
        for i, v in enumerate(vals):
            if i < len(existing):
                n = existing[i]
            else:
                n = Node(key, None, None)
                node.append(n)
            if isinstance(v, dict):
                if n.children is None:
                    n.children = []
                    n.value = None
                merge_json(n, v, remove_missing)
            elif v is None:
                node.remove(n)
            else:
                sv = _to_str(v)
                if n.children is not None:
                    n.children = None
                n.value = sv
        for extra in existing[len(vals):]:
            node.remove(extra)
    if remove_missing:
        for c in list(node.children):
            if c.key not in seen and c.key != '#include':
                node.remove(c)


def _to_str(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return str(v)


def station_key(svc: Optional[Node], sc: Optional[Node]) -> str:
    """Stable station identity: the service id (SId) survives renumbering; fall back to the
    subchannel uid for subchannels without a service."""
    if svc is not None:
        v = parse_int(svc.get('id'))
        if v is not None:
            return f'{v:04X}' if v <= 0xFFFF else f'{v:08X}'
    return 'sub:' + (sc.key if sc is not None else '?')


def slug(label: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '', (label or '').lower())
    return s or 'station'
