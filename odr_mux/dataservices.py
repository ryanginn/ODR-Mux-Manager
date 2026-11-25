"""Packet-mode data services (SPI/EPG, Journaline, TPEG, Broadcast Website, ...).

Each one is a service + a packet/enhancedpacket subchannel that reads a ``.dat`` file written by a
generator (e.g. ODR-SPI-Generator) + a component carrying the packet address and signalling.
"""
from __future__ import annotations

from . import ops
from .infofile import Node, parse_int
from .project import Project, station_key

# DSCTy (component `type`), user application, data groups - per odr-dabmux doc/advanced.mux and
# TS 101 756. `figtype` is the deprecated single-app setting, needed for apps that have no
# `userapp` name in odr-dabmux (TPEG).
PRESETS = {
    'spi': {'label': 'SPI / EPG', 'type': 60, 'userapps': ['spi'], 'datagroup': True, 'subtype': 'enhancedpacket',
            'bitrate': 16, 'hint': 'Service & Programme Information from ODR-SPI-Generator (logos, EPG).'},
    'journaline': {'label': 'Journaline', 'type': 5, 'userapps': ['journaline'], 'datagroup': True,
                   'subtype': 'packet', 'bitrate': 8,
                   'hint': 'Journaline text news (TS 102 979). Point it at the .dat file written by your Journaline generator.'},
    'tpeg': {'label': 'TPEG', 'type': 5, 'figtype': '0x4', 'datagroup': False, 'subtype': 'packet', 'bitrate': 16,
             'hint': 'Traffic info (TPEG over TDC). odr-dabmux has no userapp name for TPEG, so figtype 0x4 is used.'},
    'website': {'label': 'Broadcast Website', 'type': 60, 'userapps': ['website'], 'datagroup': True,
                'subtype': 'packet', 'bitrate': 16, 'hint': 'MOT Broadcast Website (packet mode only).'},
    'slideshow': {'label': 'Slideshow (packet)', 'type': 60, 'userapps': ['slideshow'], 'datagroup': True,
                  'subtype': 'packet', 'bitrate': 16, 'hint': 'MOT slideshow carried as its own packet service.'},
    'custom': {'label': 'Custom', 'type': 0, 'userapps': [], 'datagroup': False, 'subtype': 'packet', 'bitrate': 8,
               'hint': 'Set DSCTy, user application and data groups yourself.'},
}


def preset_of(comp: dict) -> str:
    ua = (comp.get('user-applications') or {}).get('userapp')
    uas = ua if isinstance(ua, list) else ([ua] if ua else [])
    if 'spi' in uas:
        return 'spi'
    if 'journaline' in uas or str(comp.get('figtype', '')).lower() == '0x44a':
        return 'journaline'
    if str(comp.get('figtype', '')).lower() in ('0x4', '4'):
        return 'tpeg'
    if 'website' in uas:
        return 'website'
    if 'slideshow' in uas:
        return 'slideshow'
    return 'custom'


def used_addresses(p: Project, subch_uid: str):
    out = set()
    for c in p.components():
        if c.get('subchannel') == subch_uid and c.get('address') is not None:
            out.add(parse_int(c.get('address')))
    return out


def packet_size_for(bitrate: int):
    """Largest packet size (96/72/48/24 bytes) that divides the bytes per 24 ms frame (SPI generator rule)."""
    return next((s for s in (96, 72, 48, 24) if (bitrate * 3) % s == 0), None)


def add_data_service(p: Project, data: dict):
    kind = data.get('preset', 'custom')
    pre = PRESETS.get(kind, PRESETS['custom'])
    label = data.get('label') or pre['label']
    sid = data.get('sid')
    if not sid:
        raise ops.OpError('A service id is required. Packet data services use 8 hex digits, '
                          'usually ECC + first EId digit + a number, like 0xE3222344.')
    sidv = parse_int(sid)
    if sidv is None:
        raise ops.OpError('Service id must be hex, like 0xE3222344.')
    if any(parse_int(s.get('id')) == sidv for s in p.services()):
        raise ops.OpError(f'Service id {sid} is already used.')
    uri = data.get('inputuri') or ''
    if not uri:
        raise ops.OpError('Choose the .dat file the generator writes.')
    bitrate = int(data.get('bitrate') or pre['bitrate'])
    svcs = p.sec('services', create=True)
    subs = p.sec('subchannels', create=True)
    comps = p.sec('components', create=True)
    base = data.get('uid') or ops.slug(label)[:12] or kind
    suid = _free(f'srv-{base}', [s.key for s in p.services()])
    scuid = _free(f'sub-{base}', [s.key for s in p.subchannels()])
    cuid = _free(f'comp-{base}', [c.key for c in p.components()])

    svc = Node(suid, None, [])
    _q(svc, 'label', label)
    _q(svc, 'shortlabel', data.get('shortlabel') or label[:8])
    svc.append(Node('id', sid))
    if data.get('ecc'):
        svc.append(Node('ecc', data['ecc']))
    svcs.append(svc)

    sc = Node(scuid, None, [])
    sc.append(Node('type', data.get('subtype') or pre['subtype']))
    sc.append(Node('bitrate', str(bitrate)))
    sc.append(Node('id', str(ops.free_subch_id(p))))
    sc.append(Node('protection-profile', data.get('profile') or ('EEP_B' if bitrate % 32 == 0 else 'EEP_A')))
    sc.append(Node('protection', str(data.get('protection') or 3)))
    _q(sc, 'inputuri', uri)
    sc.append(Node('inputproto', 'file'))
    subs.append(sc)

    comp = Node(cuid, None, [])
    comp.append(Node('type', str(data.get('type', pre['type']))))
    comp.append(Node('service', suid))
    comp.append(Node('subchannel', scuid))
    apps = data.get('userapps', pre.get('userapps'))
    if pre.get('figtype') and not data.get('userapps'):
        comp.append(Node('figtype', data.get('figtype') or pre['figtype']))
    elif apps:
        ops.set_user_apps(comp, apps)
    comp.append(Node('address', str(data.get('address') or '0x1')))
    comp.append(Node('datagroup', 'true' if data.get('datagroup', pre['datagroup']) else 'false'))
    comps.append(comp)
    return {'station': station_key(svc, sc), 'fs': []}


def update_data_service(p: Project, key, data: dict):
    st = p.station(key)
    if not st or st['kind'] != 'data':
        raise ops.OpError('Data service not found.')
    if data.get('service'):
        ops.update_fields(p.service(st['service_uid']), data['service'], ['label', 'shortlabel', 'id', 'ecc', 'pty', 'language'])
    if data.get('subchannel'):
        ops.update_fields(p.subchannel(st['subchannel_uid']), data['subchannel'],
                          ['type', 'bitrate', 'protection', 'protection-profile', 'inputuri', 'inputproto', 'id'])
    if data.get('component') and st['component_uid']:
        c = p.component(st['component_uid'])
        cd = data['component']
        ops.update_fields(c, cd, ['type', 'address', 'datagroup', 'figtype'])
        if 'user_apps' in cd:
            ops.set_user_apps(c, cd['user_apps'])
            if cd['user_apps']:
                c.remove('figtype')
    return []


def _q(n: Node, k, v):
    x = Node(k, v)
    x.quoted = True
    n.append(x)


def _free(uid, existing):
    if uid not in existing:
        return uid
    i = 2
    while f'{uid}{i}' in existing:
        i += 1
    return f'{uid}{i}'


# ------------------------------------------------------------------ attach to audio stations
def attached_services(p: Project, key) -> list:
    """Audio service uids that carry this data service as an extra (secondary) component."""
    st = p.station(key)
    if not st or st['kind'] != 'data':
        raise ops.OpError('Data service not found.')
    return [c.get('service') for c in p.components()
            if c.get('subchannel') == st['subchannel_uid'] and c.key != st['component_uid'] and c.get('service')]


def set_attached(p: Project, key, service_uids: list):
    """Show a packet data service (e.g. Journaline) under these audio stations too.

    Each station gets a secondary component on the data subchannel with the same packet address,
    DSCTy, data-group mode and user application as the data service's own component, so a receiver
    tuned to the station offers the Journaline/SPI/... content. odr-dabmux gives each component its
    own SCId; several components may share the packet address.
    """
    st = p.station(key)
    if not st or st['kind'] != 'data':
        raise ops.OpError('Data service not found.')
    prim = p.component(st['component_uid']) if st['component_uid'] else None
    if prim is None:
        raise ops.OpError('The data service has no component to copy.')
    want = []
    for uid in service_uids or []:
        if not p.service(uid):
            raise ops.OpError(f'Unknown service {uid}.')
        if uid == st['service_uid']:
            continue
        if uid not in want:
            want.append(uid)
    comps = p.sec('components', create=True)
    existing = {c.get('service'): c for c in p.components()
                if c.get('subchannel') == st['subchannel_uid'] and c.key != prim.key}
    for svc, c in existing.items():
        if svc not in want:
            comps.remove(c)
    svc_node = p.service(st['service_uid']) if st['service_uid'] else None
    base = prim.key[5:] if prim.key.startswith('comp-') else prim.key
    for svc in want:
        if svc in existing:
            continue
        suffix = svc[4:] if svc.startswith('srv-') else svc
        uid = _free(f'comp-{base}-{suffix}', [c.key for c in p.components()])
        c = Node(uid, None, [])
        if svc_node is not None and svc_node.get('label'):
            _q(c, 'label', svc_node.get('label'))
            if svc_node.get('shortlabel'):
                _q(c, 'shortlabel', svc_node.get('shortlabel'))
        for k in ('type', 'figtype'):
            if prim.get(k) is not None:
                c.append(Node(k, prim.get(k)))
        c.append(Node('service', svc))
        c.append(Node('subchannel', st['subchannel_uid']))
        ua = prim.child('user-applications')
        if ua is not None and ua.children:
            ops.set_user_apps(c, [x.value for x in ua.children if x.key == 'userapp'])
        for k in ('address', 'datagroup'):
            if prim.get(k) is not None:
                c.append(Node(k, prim.get(k)))
        # secondary components must come after the service's primary component (SCIdS > 0):
        # appending at the end of the components section guarantees that
        comps.append(c)
    return []
