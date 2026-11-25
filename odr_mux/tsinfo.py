"""Small MPEG-2 TS inspector: PAT/PMT, stream types and the MPEG-4 Systems (4on2) descriptors that
T-DMB needs (IOD 0x1D, SL 0x1E, FMC 0x1F). Used by tests and the DMB status page."""
from __future__ import annotations

STREAM_TYPES = {0x01: 'MPEG-1 video', 0x02: 'MPEG-2 video', 0x03: 'MPEG-1 audio', 0x04: 'MPEG-2 audio',
                0x0F: 'AAC (ADTS)', 0x10: 'MPEG-4 visual', 0x11: 'AAC (LATM)', 0x12: 'MPEG-4 SL in PES',
                0x13: 'MPEG-4 SL in sections', 0x1B: 'H.264'}


def _sections(ts: bytes, pid_want):
    """Yield complete PSI sections for one PID (handles sections spanning packets)."""
    buf = None
    for i in range(0, len(ts) - 187, 188):
        p = ts[i:i + 188]
        if p[0] != 0x47:
            continue
        pid = ((p[1] & 0x1F) << 8) | p[2]
        if pid != pid_want:
            continue
        pusi = p[1] & 0x40
        afc = (p[3] >> 4) & 3
        off = 4
        if afc & 2:
            off += 1 + p[4]
        if not afc & 1:
            continue
        payload = p[off:]
        if pusi:
            ptr = payload[0]
            if buf is not None:
                buf += payload[1:1 + ptr]
                yield from _split(buf)
            buf = payload[1 + ptr:]
        elif buf is not None:
            buf += payload
        if buf is not None and len(buf) >= 3:
            ln = ((buf[1] & 0x0F) << 8) | buf[2]
            if len(buf) >= 3 + ln:
                yield from _split(buf)
                buf = None


def _split(buf):
    while len(buf) >= 3 and buf[0] != 0xFF:
        ln = ((buf[1] & 0x0F) << 8) | buf[2]
        if len(buf) < 3 + ln:
            return
        yield buf[:3 + ln]
        buf = buf[3 + ln:]


def _descriptors(d: bytes):
    out = []
    i = 0
    while i + 2 <= len(d):
        tag, ln = d[i], d[i + 1]
        out.append((tag, d[i + 2:i + 2 + ln]))
        i += 2 + ln
    return out


def inspect(ts: bytes) -> dict:
    pat = next(_sections(ts, 0), None)
    if not pat:
        return {'error': 'no PAT'}
    progs = {}
    body = pat[8:-4]
    for i in range(0, len(body), 4):
        num = (body[i] << 8) | body[i + 1]
        pid = ((body[i + 2] & 0x1F) << 8) | body[i + 3]
        if num:
            progs[num] = pid
    out = {'programs': []}
    for num, pmt_pid in progs.items():
        pmt = next(_sections(ts, pmt_pid), None)
        if not pmt:
            continue
        pil = ((pmt[10] & 0x0F) << 8) | pmt[11]
        pdesc = _descriptors(pmt[12:12 + pil])
        streams = []
        i = 12 + pil
        end = len(pmt) - 4
        while i + 5 <= end:
            st = pmt[i]
            pid = ((pmt[i + 1] & 0x1F) << 8) | pmt[i + 2]
            eil = ((pmt[i + 3] & 0x0F) << 8) | pmt[i + 4]
            descs = _descriptors(pmt[i + 5:i + 5 + eil])
            es_id = next(((d[0] << 8) | d[1] for t, d in descs if t == 0x1E and len(d) >= 2), None)
            streams.append({'pid': pid, 'stream_type': st, 'type': STREAM_TYPES.get(st, hex(st)),
                            'descriptors': [hex(t) for t, _ in descs], 'es_id': es_id})
            i += 5 + eil
        iod = next((d for t, d in pdesc if t == 0x1D), None)
        out['programs'].append({'number': num, 'pmt_pid': pmt_pid, 'iod': iod.hex() if iod else None,
                                'program_descriptors': [hex(t) for t, _ in pdesc], 'streams': streams})
    return out


def is_tdmb(info: dict) -> bool:
    """IOD present and every stream SL-packetized with an ES_ID (the 4on2 structure T-DMB uses)."""
    for p in info.get('programs', []):
        if not p['iod']:
            return False
        if not p['streams'] or any(s['stream_type'] not in (0x12, 0x13) or s['es_id'] is None for s in p['streams']):
            return False
        return True
    return False
