"""On-air decoder: reads odr-dabmux's own EDI output and extracts what is really broadcast
per subchannel: DLS text and MOT slideshow images (from DAB+ and MP2 PAD).

Because the input is the mux's digital output (no transmission errors), Reed-Solomon
correction isn't needed: DAB+ superframes are aligned with the Fire code and the audio super
frame is read directly.
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Dict, Optional

from .infofile import parse_int

FPAD_LEN = 2
XPAD_LEN = [4, 6, 8, 12, 16, 24, 32, 48]


# ------------------------------------------------------------------ CRCs
def crc16_ccitt(data: bytes, init=0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc ^ 0xFFFF


def firecode_ok(sf: bytes) -> bool:
    crc = 0
    for byte in sf[2:11]:
        for bit in range(7, -1, -1):
            b = ((crc >> 15) ^ (byte >> bit)) & 1
            crc = (crc << 1) & 0xFFFF
            if b:
                crc ^= 0x782F
    return crc == ((sf[0] << 8) | sf[1])


# ------------------------------------------------------------------ PAD decoding
class DLSDecoder:
    def __init__(self):
        self.segs: Dict[int, bytes] = {}
        self.toggle = None
        self.charset = 0
        self.text: Optional[str] = None
        self.ts = 0

    def data_group(self, dg: bytes):
        if len(dg) < 4:
            return
        if crc16_ccitt(dg[:-2]) != (dg[-2] << 8 | dg[-1]):
            return
        p0, p1 = dg[0], dg[1]
        toggle = (p0 >> 7) & 1
        first = (p0 >> 6) & 1
        last = (p0 >> 5) & 1
        cmd = (p0 >> 4) & 1
        if cmd:
            if (p0 & 0x0F) == 0x01:  # clear display
                self.text = ''
                self.segs.clear()
            return
        n = (p0 & 0x0F) + 1
        chars = dg[2:2 + n]
        if first:
            seg = 0
            self.charset = p1 >> 4
        else:
            seg = (p1 >> 4) & 0x07
        if toggle != self.toggle:
            self.segs = {}
            self.toggle = toggle
        self.segs[seg] = chars
        if last:
            if all(i in self.segs for i in range(seg + 1)):
                raw = b''.join(self.segs[i] for i in range(seg + 1))
                self.text = decode_dab_text(raw, self.charset)
                self.ts = time.time()


def decode_dab_text(raw: bytes, charset: int) -> str:
    if charset == 15:
        return raw.decode('utf-8', 'replace')
    if charset == 4:
        return raw.decode('latin-1', 'replace')
    # EBU Latin (charset 0): ASCII-compatible for the common range
    return ''.join(chr(b) if 0x20 <= b < 0x7F else EBU_LATIN.get(b, '?') for b in raw)


EBU_LATIN = {0x80: 'á', 0x81: 'à', 0x82: 'é', 0x83: 'è', 0x84: 'í', 0x85: 'ì', 0x86: 'ó', 0x87: 'ò', 0x88: 'ú', 0x89: 'ù',
             0x8A: 'Ñ', 0x8B: 'Ç', 0x8C: 'Ş', 0x8D: 'ß', 0x8E: '¡', 0x8F: 'Ĳ', 0x90: 'â', 0x91: 'ä', 0x92: 'ê', 0x93: 'ë',
             0x94: 'î', 0x95: 'ï', 0x96: 'ô', 0x97: 'ö', 0x98: 'û', 0x99: 'ü', 0x9A: 'ñ', 0x9B: 'ç', 0x9C: 'ş', 0x9D: 'ğ',
             0x9E: 'ı', 0x9F: 'ĳ', 0xC0: 'Á', 0xC1: 'À', 0xC2: 'É', 0xC3: 'È', 0xC4: 'Í', 0xC5: 'Ì', 0xC6: 'Ó', 0xC7: 'Ò',
             0xC8: 'Ú', 0xC9: 'Ù', 0xCA: 'Ř', 0xCB: 'Č', 0xCC: 'Š', 0xCD: 'Ž', 0xCE: 'Đ', 0xCF: 'Ŀ', 0xD0: 'Â', 0xD1: 'Ä',
             0xD2: 'Ê', 0xD3: 'Ë', 0xD4: 'Î', 0xD5: 'Ï', 0xD6: 'Ô', 0xD7: 'Ö', 0xD8: 'Û', 0xD9: 'Ü', 0xDA: 'ř', 0xDB: 'č',
             0xDC: 'š', 0xDD: 'ž', 0xDE: 'đ', 0xDF: 'ŀ'}


class MOTDecoder:
    """MOT slideshow in header mode (data group types 3 = header, 4 = body)."""

    def __init__(self):
        self.objects: Dict[int, dict] = {}
        self.image: Optional[bytes] = None
        self.mime = None
        self.name = None
        self.ts = 0

    def data_group(self, dg: bytes):
        if len(dg) < 4:
            return
        b0 = dg[0]
        ext, crc_flag, seg_flag, ua_flag, dgtype = b0 >> 7, (b0 >> 6) & 1, (b0 >> 5) & 1, (b0 >> 4) & 1, b0 & 0x0F
        if crc_flag:
            if crc16_ccitt(dg[:-2]) != (dg[-2] << 8 | dg[-1]):
                return
            dg = dg[:-2]
        i = 2 + (2 if ext else 0)
        last = segno = 0
        if seg_flag:
            v = struct.unpack('>H', dg[i:i + 2])[0]
            last, segno = v >> 15, v & 0x7FFF
            i += 2
        tid = None
        if ua_flag:
            li = dg[i] & 0x0F
            tid_flag = (dg[i] >> 4) & 1
            i += 1
            if tid_flag and li >= 2:
                tid = struct.unpack('>H', dg[i:i + 2])[0]
            i += li
        if tid is None or dgtype not in (3, 4):
            return
        # segmentation header
        if i + 2 > len(dg):
            return
        seg_size = struct.unpack('>H', dg[i:i + 2])[0] & 0x1FFF
        data = dg[i + 2:i + 2 + seg_size]
        o = self.objects.setdefault(tid, {'h': {}, 'b': {}, 'hl': None, 'bl': None, 't': time.time()})
        key = 'h' if dgtype == 3 else 'b'
        o[key][segno] = data
        if last:
            o[key + 'l'] = segno
        self._try(tid, o)
        if len(self.objects) > 16:
            for k in sorted(self.objects, key=lambda k: self.objects[k]['t'])[:-8]:
                self.objects.pop(k, None)

    def _try(self, tid, o):
        if o['hl'] is None or o['bl'] is None:
            return
        if any(i not in o['h'] for i in range(o['hl'] + 1)) or any(i not in o['b'] for i in range(o['bl'] + 1)):
            return
        hdr = b''.join(o['h'][i] for i in range(o['hl'] + 1))
        body = b''.join(o['b'][i] for i in range(o['bl'] + 1))
        if len(hdr) < 7:
            return
        v = int.from_bytes(hdr[:7], 'big')
        body_size = v >> 28
        ctype = (v >> 9) & 0x3F
        csub = v & 0x1FF
        if len(body) != body_size:
            return
        name = _content_name(hdr[7:])
        if ctype == 2:
            self.image = body
            self.mime = {1: 'image/jpeg', 3: 'image/png', 0: 'image/gif'}.get(csub, 'application/octet-stream')
            self.name = name
            self.ts = time.time()
        self.objects.pop(tid, None)


def _content_name(ext: bytes):
    i = 0
    while i < len(ext):
        pli = ext[i] >> 6
        pid = ext[i] & 0x3F
        i += 1
        if pli == 0:
            ln = 0
        elif pli == 1:
            ln = 1
        elif pli == 2:
            ln = 4
        else:
            if i >= len(ext):
                return None
            if ext[i] & 0x80:
                ln = ((ext[i] & 0x7F) << 8) | ext[i + 1]
                i += 2
            else:
                ln = ext[i] & 0x7F
                i += 1
        val = ext[i:i + ln]
        i += ln
        if pid == 0x0C and val:
            return val[1:].decode('latin-1', 'replace')
    return None


class PADDecoder:
    """X-PAD application demultiplexer (DLS app 2/3, MOT 12/13 with data group length app 1)."""

    def __init__(self):
        self.dls = DLSDecoder()
        self.mot = MOTDecoder()
        self.last_ci = None          # (length, apptype) of the last subfield
        self.dls_buf = b''
        self.mot_buf = b''
        self.mot_len = None

    def process(self, xpad_rev: bytes, fpad: bytes):
        """xpad_rev: the X-PAD bytes as stored (reversed order), possibly with extra leading bytes."""
        if len(fpad) < 2:
            return
        fpad_type = fpad[0] >> 6
        xpad_ind = (fpad[0] >> 4) & 3
        ci_flag = (fpad[1] >> 1) & 1
        if fpad_type != 0 or xpad_ind == 0:
            # frames without X-PAD do not end a data group that continues afterwards
            return
        xpad = xpad_rev[::-1]
        cis = []
        pos = 0
        if xpad_ind == 1:  # short X-PAD: 4 bytes
            if ci_flag:
                at = xpad[0] & 0x1F
                cis = [(3, at)]
                pos = 1
            elif self.last_ci:
                cis = [(4, _continuation(self.last_ci[1]))]
        else:  # variable size
            if ci_flag:
                while pos < 4 and pos < len(xpad):
                    ci = xpad[pos]
                    pos += 1
                    at = ci & 0x1F
                    if at == 0:
                        break
                    cis.append((XPAD_LEN[ci >> 5], at))
            elif self.last_ci:
                cis = [(self.last_ci[0], _continuation(self.last_ci[1]))]
        for ln, at in cis:
            data = xpad[pos:pos + ln]
            pos += ln
            self._subfield(at, data)
        if cis:
            # A following X-PAD without CI list continues the last application with the
            # length of this *whole* X-PAD (CI bytes included) - matches odr-padenc.
            self.last_ci = (pos, cis[-1][1])

    def _subfield(self, at, data):
        if at == 1 and len(data) >= 4:  # data group length indicator
            if crc16_ccitt(data[:2]) == (data[2] << 8 | data[3]):
                self.mot_len = ((data[0] & 0x3F) << 8) | data[1]
                self.mot_buf = b''
        elif at == 2:
            self.dls_buf = data
            self._dls_check()
        elif at == 3:
            if self.dls_buf:
                self.dls_buf += data
                self._dls_check()
        elif at == 12:
            self.mot_buf = data
            self._mot_check()
        elif at == 13:
            if self.mot_buf:
                self.mot_buf += data
                self._mot_check()

    def _dls_check(self):
        b = self.dls_buf
        if len(b) < 2:
            return
        cmd = (b[0] >> 4) & 1
        if cmd:
            n = 2 + ((b[0] & 0x0F) == 0x02 and (b[1] & 0x0F) + 1 or 0) + 2
        else:
            n = 2 + (b[0] & 0x0F) + 1 + 2
        if len(b) >= n:
            self.dls.data_group(b[:n])
            self.dls_buf = b''

    def _mot_check(self):
        if self.mot_len and len(self.mot_buf) >= self.mot_len:
            self.mot.data_group(self.mot_buf[:self.mot_len])
            self.mot_buf = b''
            self.mot_len = None


def _continuation(at):
    return {2: 3, 3: 3, 12: 13, 13: 13, 14: 15, 15: 15}.get(at, at)


# ------------------------------------------------------------------ audio framing
class DabPlusExtractor:
    def __init__(self, bitrate: int):
        self.s = bitrate // 8
        self.frame_len = bitrate * 3
        self.frames = []
        self.synced = False
        self.pad = PADDecoder()
        self.superframes = 0
        self.info = None

    def frame(self, data: bytes):
        if len(data) != self.frame_len:
            self.frame_len = len(data)
            self.s = self.frame_len // 24
            self.frames = []
            self.synced = False
        self.frames.append(data)
        if len(self.frames) > 5:
            self.frames.pop(0)
        if len(self.frames) < 5:
            return
        if not self.synced:
            if firecode_ok(self.frames[0]):
                self.synced = True
            else:
                return
        sf = b''.join(self.frames)
        if not firecode_ok(sf):
            self.synced = False
            self.frames.pop(0)
            return
        self.frames = []
        self._superframe(sf)

    def _superframe(self, sf):
        self.superframes += 1
        h = sf[2]
        dac, sbr, ch, ps = (h >> 6) & 1, (h >> 5) & 1, (h >> 4) & 1, (h >> 3) & 1
        num = {(0, 1): 2, (1, 1): 3, (0, 0): 4, (1, 0): 6}[(dac, sbr)]
        first = {2: 5, 3: 6, 4: 8, 6: 11}[num]
        starts = [first]
        bits = int.from_bytes(sf[3:first], 'big')
        nbits = (first - 3) * 8
        for i in range(num - 1):
            starts.append((bits >> (nbits - 12 * (i + 1))) & 0xFFF)
        end = 110 * self.s
        starts.append(end)
        self.info = {'rate': 48000 if dac else 32000, 'sbr': bool(sbr), 'ps': bool(ps), 'stereo': bool(ch), 'aus': num}
        for i in range(num):
            au = sf[starts[i]:starts[i + 1] - 2]
            if len(au) < 3 or (au[0] >> 5) != 4:
                continue
            n = au[1]
            st = 2
            if n == 255:
                n += au[2]
                st = 3
            dse = au[st:st + n]
            if len(dse) >= FPAD_LEN:
                self.pad.process(dse[:-FPAD_LEN], dse[-FPAD_LEN:])


MP2_BITRATES = {0: [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],   # MPEG-1 L2
                1: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}        # MPEG-2 LSF L2


class MP2Extractor:
    def __init__(self, bitrate: int):
        self.buf = b''
        self.pad = PADDecoder()
        self.frames = 0
        self.info = None

    def frame(self, data: bytes):
        self.buf += data
        while len(self.buf) >= 4:
            if not (self.buf[0] == 0xFF and (self.buf[1] & 0xF0) == 0xF0):
                k = self.buf.find(b'\xff', 1)
                self.buf = self.buf[k:] if k > 0 else b''
                continue
            mpeg1 = (self.buf[1] >> 3) & 1
            bi = self.buf[2] >> 4
            sfi = (self.buf[2] >> 2) & 3
            mode = self.buf[3] >> 6
            lsf = 0 if mpeg1 else 1
            br = MP2_BITRATES[lsf][bi] if bi < 15 else 0
            sr = (48000 if mpeg1 else 24000) if sfi == 1 else (44100 if mpeg1 else 22050) if sfi == 0 else 32000
            if not br:
                self.buf = self.buf[1:]
                continue
            flen = 144 * br * 1000 // sr // (1 if mpeg1 else 2)
            if len(self.buf) < flen:
                return
            fr, self.buf = self.buf[:flen], self.buf[flen:]
            self.frames += 1
            chans = 1 if mode == 3 else 2
            scf = 4 if (mpeg1 and br // chans >= 56) else 2
            self.info = {'rate': sr, 'bitrate': br, 'mode': ['stereo', 'joint', 'dual', 'mono'][mode]}
            self.pad.process(fr[:flen - FPAD_LEN - scf], fr[flen - FPAD_LEN:])


# ------------------------------------------------------------------ EDI
def parse_af(packet: bytes):
    """Yield (tag, value) from an AF packet."""
    if packet[:2] != b'AF':
        return
    ln = struct.unpack('>I', packet[2:6])[0]
    payload = packet[10:10 + ln]
    i = 0
    while i + 8 <= len(payload):
        name = payload[i:i + 4]
        bits = struct.unpack('>I', payload[i + 4:i + 8])[0]
        n = (bits + 7) // 8
        yield name, payload[i + 8:i + 8 + n]
        i += 8 + n


class OnAir:
    def __init__(self, host: str, port: int, project_fn):
        self.host, self.port = host, port
        self.project_fn = project_fn
        self.ex: Dict[str, object] = {}
        self.scid_map: Dict[int, tuple] = {}
        self._map_ts = 0
        self._stop = threading.Event()
        self.ok = False
        self.last = 0
        self.error = None
        self.lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg, ws):
        v = (cfg.get('onair_edi') or 'auto').strip()
        if v == 'off':
            return None
        if v == 'auto':
            if not ws.configured:
                return None
            p = ws.live()
            port = None
            outs = p.sec('outputs')
            for n in _walk(outs) if outs is not None else []:
                if n.key == 'listenport':
                    port = parse_int(n.value)
                    break
            if not port:
                return None
            host = '127.0.0.1'
        else:
            v = v.replace('tcp://', '')
            host, _, port = v.rpartition(':')
            port = int(port)
        return cls(host or '127.0.0.1', port, ws.live)

    def start(self):
        threading.Thread(target=self._run, name='onair', daemon=True).start()

    def stop(self):
        self._stop.set()

    def status(self):
        return {'ok': self.ok and time.time() - self.last < 5, 'source': f'tcp://{self.host}:{self.port}', 'error': self.error}

    def _refresh_map(self):
        if time.time() - self._map_ts < 10:
            return
        self._map_ts = time.time()
        try:
            p = self.project_fn()
        except Exception:
            return
        m = {}
        for sc in p.subchannels():
            sid = parse_int(sc.get('id'))
            if sid is not None:
                m[sid] = (sc.key, sc.get('type'), parse_int(sc.get('bitrate'), 0))
        self.scid_map = m

    def _run(self):
        while not self._stop.is_set():
            try:
                with socket.create_connection((self.host, self.port), timeout=5) as s:
                    s.settimeout(5)
                    self.error = None
                    buf = b''
                    while not self._stop.is_set():
                        chunk = s.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                        while True:
                            k = buf.find(b'AF')
                            if k < 0:
                                buf = buf[-1:]
                                break
                            if k:
                                buf = buf[k:]
                            if len(buf) < 10:
                                break
                            ln = struct.unpack('>I', buf[2:6])[0]
                            total = 10 + ln + 2
                            if ln > 1_000_000:
                                buf = buf[2:]
                                continue
                            if len(buf) < total:
                                break
                            pkt, buf = buf[:total], buf[total:]
                            self._af(pkt)
            except OSError as e:
                self.error = str(e)
                self.ok = False
            self._stop.wait(3)

    def _af(self, pkt):
        self._refresh_map()
        self.ok = True
        self.last = time.time()
        for name, val in parse_af(pkt):
            if name[:3] == b'est' and len(val) >= 3:
                scid = val[0] >> 2
                info = self.scid_map.get(scid)
                if not info:
                    continue
                uid, stype, br = info
                ex = self.ex.get(uid)
                if ex is None or getattr(ex, '_type', None) != stype:
                    if stype == 'dabplus':
                        ex = DabPlusExtractor(br)
                    elif stype == 'audio':
                        ex = MP2Extractor(br)
                    else:
                        continue
                    ex._type = stype
                    self.ex[uid] = ex
                try:
                    ex.frame(val[3:])
                except Exception:
                    pass

    def station(self, uid) -> Optional[dict]:
        ex = self.ex.get(uid)
        if ex is None or not self.ok:
            return None
        pad = ex.pad
        return {'dls': pad.dls.text, 'dls_ts': pad.dls.ts,
                'slide': {'ts': pad.mot.ts, 'name': pad.mot.name, 'mime': pad.mot.mime} if pad.mot.image else None,
                'audio': ex.info}

    def slide_image(self, uid):
        ex = self.ex.get(uid)
        if ex is None or not ex.pad.mot.image:
            return None
        return ex.pad.mot.image, ex.pad.mot.mime


def _walk(n):
    for c in n.children or []:
        yield c
        yield from _walk(c)
