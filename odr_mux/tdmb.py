"""T-DMB transport stream multiplexer (ETSI TS 102 428 / MPEG-4 over MPEG-2, ISO 13818-1 Amd 7).

Takes the ordinary MPEG-2 TS that ffmpeg writes (H.264 Annex B video + AAC ADTS audio) and
re-multiplexes it the way T-DMB receivers expect:

* PMT with an IOD_descriptor (0x1D) holding the InitialObjectDescriptor, which describes the
  BIFS scene stream and the Object Descriptor (OD) stream.
* OD and BIFS access units as SL packets in ISO/IEC 14496 sections (stream_type 0x13), sent as a
  carousel so receivers can tune in at any time.
* Video and audio as SL packets in PES (stream_type 0x12, stream_id 0xFA), each PID tagged with an
  SL_descriptor (0x1E) carrying its ES_ID. Video uses AVC length-prefixed NAL units with an
  AVCDecoderConfigurationRecord; audio uses raw AAC frames with an AudioSpecificConfig.

The BIFS scenes (a Sound2D for radio; Sound2D + a Bitmap with a MovieTexture for TV) were
encoded with GPAC MP4Box from BT text and are embedded as bytes.
"""
from __future__ import annotations

import struct
import zlib
from typing import Dict, List, Optional, Tuple

# ES_IDs / OD IDs / PIDs
ES_BIFS, ES_OD, ES_VIDEO, ES_AUDIO = 1, 2, 3, 4
OD_VIDEO, OD_AUDIO = 3, 4
PID_PMT, PID_BIFS, PID_OD, PID_VIDEO, PID_AUDIO = 0x0100, 0x0101, 0x0102, 0x0103, 0x0104

# MP4Box-encoded BIFS ReplaceScene AUs (pixelMetric, nodeIDbits 1)
BIFS_TV = bytes.fromhex('c011a502605404e4cd5411403d04c0')      # Sound2D(od:4) + Shape(Bitmap, MovieTexture od:3)
BIFS_RADIO = bytes.fromhex('c011a502605404f0')                   # Sound2D(od:4)


# ------------------------------------------------------------------ bit helpers
class BitWriter:
    def __init__(self):
        self.v = 0
        self.n = 0

    def put(self, value: int, bits: int):
        self.v = (self.v << bits) | (value & ((1 << bits) - 1))
        self.n += bits

    def bytes(self) -> bytes:
        pad = (-self.n) % 8
        v = self.v << pad
        return v.to_bytes((self.n + pad) // 8, 'big') if self.n else b''


def mpeg_crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


# ------------------------------------------------------------------ MPEG-4 descriptors (ISO 14496-1)
def descr(tag: int, payload: bytes) -> bytes:
    n = len(payload)
    size = []
    size.append(n & 0x7F)
    n >>= 7
    while n:
        size.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes([tag]) + bytes(reversed(size)) + payload


def sl_config(start_end: bool, rap: bool, timestamps: bool, ts_res: int, ts_len: int) -> bytes:
    flags = (0x80 if start_end else 0) | (0x40 if start_end else 0) | (0x20 if rap else 0) | (0x04 if timestamps else 0)
    body = bytes([0, flags]) + struct.pack('>II', ts_res, 0) + bytes([ts_len, 0, 0, 0]) + b'\x00\x03'
    return descr(0x06, body)


SL_AV = dict(start_end=True, rap=True, timestamps=True, ts_res=90000, ts_len=33)
SL_SYS = dict(start_end=True, rap=True, timestamps=True, ts_res=90000, ts_len=33)


def dec_config(oti: int, stream_type: int, buffer_size: int, max_br: int, avg_br: int, dsi: bytes = b'') -> bytes:
    body = bytes([oti, (stream_type << 2) | 0x01]) + buffer_size.to_bytes(3, 'big') + struct.pack('>II', max_br, avg_br)
    if dsi:
        body += descr(0x05, dsi)
    return descr(0x04, body)


def es_descr(es_id: int, dcd: bytes, slc: bytes) -> bytes:
    return descr(0x03, struct.pack('>HB', es_id, 0) + dcd + slc)


def bifs_config(width: int, height: int) -> bytes:
    w = BitWriter()
    w.put(1, 5)          # nodeIDbits
    w.put(0, 5)          # routeIDbits
    w.put(1, 1)          # isCommandStream
    w.put(1, 1)          # pixelMetric
    w.put(1, 1)          # hasSize
    w.put(width, 16)
    w.put(height, 16)
    return w.bytes()


def initial_od(width: int, height: int, tv: bool) -> bytes:
    hdr = struct.pack('>H', (1 << 6) | 0x0F)          # ODID 1, URL 0, includeInlineProfileLevelFlag 0
    profiles = bytes([0xFF, 0xFE, 0xFF, 0xFE if tv else 0xFF, 0xFE])   # OD, scene, audio, visual, graphics
    bifs = es_descr(ES_BIFS, dec_config(0x01, 0x03, 64, 0, 0, bifs_config(width, height)), sl_config(**SL_SYS))
    od = es_descr(ES_OD, dec_config(0x01, 0x01, 256, 0, 0), sl_config(**SL_SYS))
    return descr(0x02, hdr + profiles + bifs + od)


def od_update(video_dsi: Optional[bytes], audio_dsi: Optional[bytes], video_br: int, audio_br: int) -> bytes:
    """ObjectDescriptorUpdate with one OD per elementary stream (video OD 3, audio OD 4)."""
    ods = b''
    if video_dsi is not None:
        e = es_descr(ES_VIDEO, dec_config(0x21, 0x04, 2 * video_br // 8, video_br, video_br, video_dsi), sl_config(**SL_AV))
        ods += descr(0x01, struct.pack('>H', (OD_VIDEO << 6) | 0x1F) + e)
    if audio_dsi is not None:
        e = es_descr(ES_AUDIO, dec_config(0x40, 0x05, 2 * audio_br // 8, audio_br, audio_br, audio_dsi), sl_config(**SL_AV))
        ods += descr(0x01, struct.pack('>H', (OD_AUDIO << 6) | 0x1F) + e)
    return descr(0x01, ods)   # ObjectDescriptorUpdate command


# ------------------------------------------------------------------ elementary stream conversion
def split_annexb(data: bytes) -> List[bytes]:
    out = []
    i = 0
    n = len(data)
    starts = []
    while True:
        j = data.find(b'\x00\x00\x01', i)
        if j < 0:
            break
        starts.append(j + 3)
        i = j + 3
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 3) if k + 1 < len(starts) else n
        nal = data[s:e]
        while nal.endswith(b'\x00'):
            nal = nal[:-1]
        if nal:
            out.append(nal)
    return out


def avcc(sps: bytes, pps: bytes) -> bytes:
    return bytes([1, sps[1], sps[2], sps[3], 0xFF, 0xE1]) + struct.pack('>H', len(sps)) + sps + \
        bytes([1]) + struct.pack('>H', len(pps)) + pps


def adts_frames(data: bytes):
    """Yield (audio_specific_config, raw_frame) from ADTS data."""
    i = 0
    while i + 7 <= len(data):
        if data[i] != 0xFF or (data[i + 1] & 0xF6) != 0xF0:
            i += 1
            continue
        prot_absent = data[i + 1] & 1
        profile = data[i + 2] >> 6
        fidx = (data[i + 2] >> 2) & 0x0F
        ch = ((data[i + 2] & 1) << 2) | (data[i + 3] >> 6)
        flen = ((data[i + 3] & 3) << 11) | (data[i + 4] << 3) | (data[i + 5] >> 5)
        hl = 7 if prot_absent else 9
        if flen < hl or i + flen > len(data):
            break
        asc = struct.pack('>H', ((profile + 1) << 11) | (fidx << 7) | (ch << 3))
        yield asc, data[i + hl:i + flen]
        i += flen


# ------------------------------------------------------------------ TS input (ffmpeg output)
class TSDemux:
    """Reassemble PES packets from a plain MPEG-TS; yields (kind, pts, dts, payload)."""

    def __init__(self):
        self.pmt_pid = None
        self.pids: Dict[int, str] = {}
        self.buf: Dict[int, bytearray] = {}
        self.rest = b''

    def feed(self, data: bytes):
        data = self.rest + data
        n = len(data) // 188 * 188
        self.rest = data[n:]
        for i in range(0, n, 188):
            yield from self._packet(data[i:i + 188])

    def flush(self):
        for pid in list(self.buf):
            yield from self._finish(pid)

    def _packet(self, p):
        if p[0] != 0x47:
            return
        pid = ((p[1] & 0x1F) << 8) | p[2]
        pusi = p[1] & 0x40
        afc = (p[3] >> 4) & 3
        off = 4
        if afc & 2:
            off += 1 + p[4]
        if not afc & 1 or off >= 188:
            return
        pl = p[off:]
        if pid == 0 and pusi:
            sec = pl[1 + pl[0]:]
            self.pmt_pid = ((sec[10] & 0x1F) << 8) | sec[11]
            return
        if pid == self.pmt_pid and pusi:
            sec = pl[1 + pl[0]:]
            slen = ((sec[1] & 0x0F) << 8) | sec[2]
            pil = ((sec[10] & 0x0F) << 8) | sec[11]
            j = 12 + pil
            while j + 5 <= 3 + slen - 4:
                st = sec[j]
                epid = ((sec[j + 1] & 0x1F) << 8) | sec[j + 2]
                eil = ((sec[j + 3] & 0x0F) << 8) | sec[j + 4]
                if st in (0x1B,):
                    self.pids[epid] = 'video'
                elif st in (0x0F,):
                    self.pids[epid] = 'audio'
                j += 5 + eil
            return
        kind = self.pids.get(pid)
        if not kind:
            return
        if pusi:
            yield from self._finish(pid)
            self.buf[pid] = bytearray(pl)
        elif pid in self.buf:
            self.buf[pid] += pl

    def _finish(self, pid):
        b = self.buf.pop(pid, None)
        if not b or len(b) < 9 or b[:3] != b'\x00\x00\x01':
            return
        flags = b[7]
        hl = b[8]
        pts = dts = None
        if flags & 0x80:
            pts = _read_ts(b[9:14])
            dts = pts
        if flags & 0x40:
            dts = _read_ts(b[14:19])
        yield self.pids[pid], pts, dts, bytes(b[9 + hl:])


def _read_ts(b):
    return (((b[0] >> 1) & 7) << 30) | (b[1] << 22) | ((b[2] >> 1) << 15) | (b[3] << 7) | (b[4] >> 1)


def _write_ts(prefix, v):
    return bytes([(prefix << 4) | (((v >> 30) & 7) << 1) | 1, (v >> 22) & 0xFF, (((v >> 15) & 0x7F) << 1) | 1,
                  (v >> 7) & 0xFF, ((v & 0x7F) << 1) | 1])


# ------------------------------------------------------------------ T-DMB TS output
class TDMBMux:
    def __init__(self, tv: bool, width=320, height=240, video_br=320_000, audio_br=96_000):
        self.tv = tv
        self.width, self.height = width, height
        self.video_br, self.audio_br = video_br, audio_br
        self.cc: Dict[int, int] = {}
        self.sps = self.pps = None
        self.video_dsi = None
        self.audio_dsi = None
        self.last_psi = None
        self.last_sys = None
        self.od_version = 0
        self.pcr_pid = PID_VIDEO if tv else PID_AUDIO
        self.last_pcr = None
        self.out: List[bytes] = []
        self._now = 0
        self._first_video = None

    # -------------------------------------------------- packetizing
    def _packets(self, pid: int, payload: bytes, pusi: bool, pcr: Optional[int] = None):
        first = True
        pos = 0
        while pos < len(payload) or first:
            cc = self.cc.get(pid, 0)
            self.cc[pid] = (cc + 1) & 0x0F
            af = b''
            if first and pcr is not None:
                base = pcr & ((1 << 33) - 1)
                af = bytes([0x10]) + struct.pack('>IH', base >> 1, ((base & 1) << 15) | 0x7E00)
            room = 184 - (len(af) + 1 if af else 0)
            chunk = payload[pos:pos + room]
            pos += len(chunk)
            if len(chunk) < room:
                # stuff with an adaptation field
                need = room - len(chunk)
                if af:
                    af = af + b'\xff' * need
                else:
                    af = (b'\x00' + b'\xff' * (need - 2)) if need >= 2 else b''
                    if need == 1:
                        af = b''
                        hdr_af = bytes([0])  # adaptation_field_length 0
                        pkt = bytes([0x47, (0x40 if (first and pusi) else 0) | (pid >> 8), pid & 0xFF, 0x30 | cc]) + hdr_af + chunk
                        self.out.append(pkt)
                        first = False
                        continue
            if af:
                pkt = bytes([0x47, (0x40 if (first and pusi) else 0) | (pid >> 8), pid & 0xFF, 0x30 | cc,
                             len(af)]) + af + chunk
            else:
                pkt = bytes([0x47, (0x40 if (first and pusi) else 0) | (pid >> 8), pid & 0xFF, 0x10 | cc]) + chunk
            assert len(pkt) == 188, len(pkt)
            self.out.append(pkt)
            first = False

    @staticmethod
    def _sl_header(ts: int, rap=True) -> bytes:
        w = BitWriter()
        w.put(1, 1)                     # accessUnitStartFlag
        w.put(1, 1)                     # accessUnitEndFlag
        w.put(1 if rap else 0, 1)       # randomAccessPointFlag
        w.put(1, 1)                     # decodingTimeStampFlag
        w.put(1, 1)                     # compositionTimeStampFlag
        w.put(ts & ((1 << 33) - 1), 33)
        w.put(ts & ((1 << 33) - 1), 33)
        return w.bytes()

    def _section(self, pid, table_id, ext, body, version=0):
        sl = 5 + len(body) + 4
        sec = bytes([table_id, 0xB0 | (sl >> 8), sl & 0xFF]) + struct.pack('>H', ext) + \
            bytes([0xC1 | ((version & 0x1F) << 1), 0, 0]) + body
        sec += struct.pack('>I', mpeg_crc32(sec))
        self._packets(pid, b'\x00' + sec, True)

    def _psi(self):
        self._section(0, 0x00, 1, struct.pack('>HH', 1, 0xE000 | PID_PMT))
        iod = initial_od(self.width, self.height, self.tv)
        prog_info = bytes([0x1D, 2 + len(iod), 0x10, 0x01]) + iod
        es = b''

        def entry(st, pid, es_id):
            d = bytes([0x1E, 2]) + struct.pack('>H', es_id)
            return bytes([st]) + struct.pack('>HH', 0xE000 | pid, 0xF000 | len(d)) + d
        es += entry(0x13, PID_BIFS, ES_BIFS)
        es += entry(0x13, PID_OD, ES_OD)
        if self.tv:
            es += entry(0x12, PID_VIDEO, ES_VIDEO)
        es += entry(0x12, PID_AUDIO, ES_AUDIO)
        body = struct.pack('>HH', 0xE000 | self.pcr_pid, 0xF000 | len(prog_info)) + prog_info + es
        self._section(PID_PMT, 0x02, 1, body)

    def _systems(self, t: int):
        # OD first, so the scene's od:3 / od:4 references resolve as soon as the scene arrives
        if self.tv:
            if self._first_video is None and self.video_dsi is not None:
                self._first_video = t
            # video-only sources (cameras, test patterns): don't wait for audio forever
            ready = self.video_dsi is not None and (self.audio_dsi is not None or t - self._first_video >= 180000)
        else:
            ready = self.audio_dsi is not None
        if ready:
            self._section(PID_OD, 0x05, ES_OD, self._sl_header(t) + od_update(
                self.video_dsi if self.tv else None, self.audio_dsi, self.video_br, self.audio_br), self.od_version)
            self._section(PID_BIFS, 0x04, ES_BIFS, self._sl_header(t) + (BIFS_TV if self.tv else BIFS_RADIO))

    def _sl_pes(self, pid, au: bytes, pts: int, dts: int, rap: bool):
        w = BitWriter()
        w.put(1, 1)  # accessUnitStartFlag
        w.put(1, 1)  # accessUnitEndFlag
        w.put(1 if rap else 0, 1)  # randomAccessPointFlag
        w.put(1, 1)  # decodingTimeStampFlag
        w.put(1, 1)  # compositionTimeStampFlag
        w.put(dts & ((1 << 33) - 1), 33)
        w.put(pts & ((1 << 33) - 1), 33)
        sl = w.bytes() + au
        hdr_data = _write_ts(3, pts) + _write_ts(1, dts) if dts != pts else _write_ts(2, pts)
        flags2 = 0xC0 if dts != pts else 0x80
        pes_len = 3 + len(hdr_data) + len(sl)
        pes = b'\x00\x00\x01\xFA' + struct.pack('>H', pes_len if pes_len < 65536 else 0) + \
            bytes([0x84, flags2, len(hdr_data)]) + hdr_data + sl
        pcr = None
        if pid == self.pcr_pid:
            pcr = max(0, dts - 63000)          # PCR 700 ms ahead of decoding
        self._packets(pid, pes, True, pcr)

    # -------------------------------------------------- input
    def add(self, kind: str, pts: Optional[int], dts: Optional[int], data: bytes):
        """Feed one PES payload from ffmpeg. Returns TS packets ready to send."""
        if pts is None:
            return self._take()
        t = dts if dts is not None else pts
        if self.last_psi is None or t - self.last_psi >= 18000:         # PAT/PMT every 200 ms
            self._psi()
            self.last_psi = t
        if self.last_sys is None or t - self.last_sys >= 45000:         # OD/BIFS carousel every 500 ms
            self._systems(t)
            self.last_sys = t
        self._now = t
        if kind == 'video' and self.tv:
            nals = split_annexb(data)
            rap = False
            body = b''
            for nal in nals:
                typ = nal[0] & 0x1F
                if typ == 7:
                    if self.sps != nal:
                        self.sps = nal
                        self._update_video_dsi()
                elif typ == 8:
                    if self.pps != nal:
                        self.pps = nal
                        self._update_video_dsi()
                elif typ == 9:
                    continue
                if typ == 5:
                    rap = True
                body += struct.pack('>I', len(nal)) + nal
            if body and self.video_dsi is not None:
                self._sl_pes(PID_VIDEO, body, pts, t, rap)
        elif kind == 'audio':
            k = 0
            for asc, frame in adts_frames(data):
                if self.audio_dsi != asc:
                    self.audio_dsi = asc
                    self.od_version = (self.od_version + 1) & 0x1F
                    self._systems(t)
                ts = pts + k * 1920        # 1024 samples @ 48 kHz in 90 kHz units
                self._sl_pes(PID_AUDIO, frame, ts, ts, True)
                k += 1
        return self._take()

    def _update_video_dsi(self):
        if self.sps and self.pps:
            self.video_dsi = avcc(self.sps, self.pps)
            self.od_version = (self.od_version + 1) & 0x1F
            self._systems(self._now)

    def _take(self) -> List[bytes]:
        out, self.out = self.out, []
        return out


def remux(ts: bytes, tv: bool, **kw) -> bytes:
    """Convert a whole ffmpeg TS into a T-DMB TS (used by tests and offline conversion)."""
    d = TSDemux()
    m = TDMBMux(tv, **kw)
    out = []
    for item in d.feed(ts):
        out += m.add(*item)
    for item in d.flush():
        out += m.add(*item)
    return b''.join(out)
