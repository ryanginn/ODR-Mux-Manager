"""T-DMB support (experimental).

Current odr-dabmux accepts ``type dmb`` subchannels but, since its input refactor, passes the
bytes through raw: the old DMB input that added the outer coding (Reed-Solomon (204,188) +
convolutional byte interleaver, I=12 M=17) is "unported". This module provides that outer
coder (a byte-exact port of odr-dabmux src/Dmb.cpp + Interleaver.cpp + lib/ReedSolomon) and an
encoder pipeline: ffmpeg -> MPEG-2 TS -> outer coding -> UDP -> odr-dabmux.

Limitation (see PLAN.md): full T-DMB also packs the elementary streams with MPEG-4 Systems (SL
packets, IOD/OD/BIFS) inside the TS. ffmpeg doesn't produce that, and it isn't implemented here
yet, so receivers that insist on TS 102 428 MPEG-4 SL won't decode the picture.
"""
from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import time
from typing import List, Optional

from . import capabilities

# ------------------------------------------------------------------ Reed-Solomon (204,188)
_GFPOLY = 0x11D
_NROOTS = 16
_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _GFPOLY
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gmul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _genpoly():
    # g(x) = prod_{i=0}^{15} (x - alpha^i)   (firstRoot 0, primElem 1 as in odr-dabmux)
    g = [1]
    for i in range(_NROOTS):
        root = _EXP[i]
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c                      # x * g
            ng[j + 1] ^= _gmul(c, root)     # root * g
        g = ng
    return g  # highest degree first, g[0] == 1


_GEN = _genpoly()
_GEN_LOG = [_LOG[c] if c else None for c in _GEN[1:]]


def rs_encode(msg: bytes) -> bytes:
    """Return the 16 parity bytes for a 188-byte packet (shortened RS(255,239))."""
    par = [0] * _NROOTS
    for b in msg:
        fb = b ^ par[0]
        par = par[1:] + [0]
        if fb:
            lf = _LOG[fb]
            for j in range(_NROOTS):
                gl = _GEN_LOG[j]
                if gl is not None:
                    par[j] ^= _EXP[lf + gl]
    return bytes(par)


def rs_syndromes_ok(cw: bytes) -> bool:
    """True if all 16 syndromes are zero (cw = 188 data + 16 parity)."""
    for i in range(_NROOTS):
        s = 0
        a = _EXP[i]
        for b in cw:
            s = _gmul(s, a) ^ b
        if s:
            return False
    return True


# ------------------------------------------------------------------ interleaver (I=12, M=17)
class Interleaver:
    """Port of odr-dabmux Interleaver (forward direction)."""

    def __init__(self, I=12, M=17):
        self.I, self.M, self.N = I, M, I * M
        self.mem_size = self.N * I - 1
        self.mem = bytearray(self.mem_size)
        self.j = 0
        self.index = 0

    def encode(self, data: bytes) -> bytes:
        out = bytearray(len(data))
        I, N, ms, mem = self.I, self.N, self.mem_size, self.mem
        j, idx = self.j, self.index
        for k, b in enumerate(data):
            if j:
                mem[(idx + j * N) % ms] = b
                out[k] = mem[idx]
            else:
                out[k] = b
            j += 1
            if j == I:
                j = 0
            idx += 1
            if idx == ms:
                idx = 0
        self.j, self.index = j, idx
        return bytes(out)


class OuterCoder:
    """TS packets (188 bytes) in -> RS(204,188) + interleaved bytes out."""

    def __init__(self):
        self.il = Interleaver()
        self.buf = b''

    def feed(self, data: bytes) -> bytes:
        self.buf += data
        out = []
        while len(self.buf) >= 188:
            pkt, self.buf = self.buf[:188], self.buf[188:]
            if pkt[0] != 0x47:
                # resync on the next sync byte
                k = self.buf.find(b'\x47')
                self.buf = (pkt[1:] + self.buf)
                k = self.buf.find(b'\x47')
                self.buf = self.buf[k:] if k >= 0 else b''
                continue
            out.append(self.il.encode(pkt + rs_encode(pkt)))
        return b''.join(out)


# ------------------------------------------------------------------ support / instructions
def support(cfg: dict) -> dict:
    caps = capabilities.detect(cfg)
    dm = caps.get('dabmux')
    ff = caps.get('ffmpeg')
    checks = [
        {'label': 'odr-dabmux', 'ok': bool(dm), 'detail': f'{dm["version"]}: accepts type dmb (raw)' if dm else 'not found'},
        {'label': 'DMB outer coding (RS + interleaver)', 'ok': True, 'detail':
            'done by ODR Mux Manager (odr-dabmux no longer does it)'},
        {'label': 'ffmpeg', 'ok': bool(ff), 'detail': 'found' if ff else 'not found'},
        {'label': 'H.264 encoder (DMB TV)', 'ok': bool(ff and ff.get('h264')), 'warn': not (ff and ff.get('h264')),
         'detail': 'libx264' if ff and ff.get('libx264') else ('hardware encoder' if ff and ff.get('h264') else 'missing')},
        {'label': 'HE-AAC encoder', 'ok': bool(ff and ff.get('he_aac')), 'warn': True,
         'detail': 'libfdk_aac' if ff and ff.get('he_aac') else 'only AAC-LC (ffmpeg built without libfdk_aac): works, uses more bitrate'},
        {'label': 'MPEG-4 Systems packaging (TS 102 428)', 'ok': False, 'warn': True,
         'detail': 'not implemented yet: plain H.264/AAC in MPEG-2 TS'},
    ]
    instr = []
    if not dm:
        instr.append({'title': 'Install odr-dabmux', 'text': 'Build it from source (Opendigitalradio/ODR-DabMux).',
                      'cmd': 'git clone https://github.com/Opendigitalradio/ODR-DabMux.git\ncd ODR-DabMux && ./bootstrap.sh && ./configure && make && sudo make install'})
    if not ff:
        instr.append({'title': 'Install ffmpeg', 'cmd': 'sudo apt install ffmpeg'})
    elif not ff.get('h264'):
        instr.append({'title': 'Get an ffmpeg with H.264 (libx264)', 'cmd': 'sudo apt install ffmpeg libx264-dev'})
    if ff and not ff.get('he_aac'):
        instr.append({'title': 'Optional: ffmpeg with libfdk_aac for HE-AAC',
                      'text': 'Distribution ffmpeg packages leave libfdk_aac out for licensing reasons. Build ffmpeg with --enable-libfdk-aac --enable-nonfree to get HE-AAC; until then AAC-LC is used.'})
    instr.append({'title': 'Add a DMB service here', 'text': 'The manager creates the subchannel (type dmb, UDP input) and a supervisor program that runs ffmpeg and the outer coder.'})
    ready = bool(dm and ff)
    note = ('T-DMB needs a lot of capacity (DMB TV ~300–550 kbps ≈ 200–400 CU) and few receivers outside Korea '
            'decode it. The outer coding is a byte-exact port of odr-dabmux\'s original DMB code.')
    return {'ready': ready, 'checks': checks, 'instructions': instr, 'note': note}


def add_dmb_service(p, data: dict, cfg: dict):
    from . import ops
    from .infofile import Node
    from .project import station_key
    label = data.get('label') or 'DMB'
    sid = data.get('sid')
    if not sid:
        raise ops.OpError('A service id is required.')
    kind = data.get('kind', 'radio')
    bitrate = int(data.get('bitrate') or (448 if kind == 'tv' else 128))
    if bitrate % 8:
        raise ops.OpError('Bitrate must be a multiple of 8.')
    port = int(data.get('port') or ops.next_port(p))
    svcs, subs, comps = p.sec('services', create=True), p.sec('subchannels', create=True), p.sec('components', create=True)
    base = 'dmb-' + (ops.slug(label)[:10] or 'svc')
    suid = ops.next_uid([s.key for s in p.services()], f'srv-{base}-')
    scuid = ops.next_uid([s.key for s in p.subchannels()], f'sub-{base}-')
    cuid = ops.next_uid([c.key for c in p.components()], f'comp-{base}-')
    svc = Node(suid, None, [])
    svc.append(Node('id', sid))
    lab = Node('label', label); lab.quoted = True; svc.append(lab)
    sl = Node('shortlabel', data.get('shortlabel') or label[:8]); sl.quoted = True; svc.append(sl)
    svcs.append(svc)
    sc = Node(scuid, None, [])
    for k, v in (('type', 'dmb'), ('bitrate', str(bitrate)), ('id', str(ops.free_subch_id(p))),
                 ('protection-profile', data.get('profile') or 'EEP_A'), ('protection', str(data.get('protection') or 3)),
                 ('inputproto', 'udp')):
        sc.append(Node(k, v))
    u = Node('inputuri', f'udp://0.0.0.0:{port}'); u.quoted = True; sc.append(u)
    subs.append(sc)
    comp = Node(cuid, None, [])
    comp.append(Node('type', '24'))      # DSCTy 24: MPEG-2 Transport Stream
    comp.append(Node('service', suid))
    comp.append(Node('subchannel', scuid))
    comp.append(Node('figtype', '0x9'))  # user application type 0x009: DMB
    comps.append(comp)
    # encoder program
    import sys as _sys
    exe = cfg.get('manager_exe') or 'odr-mux-manager'
    argv = [exe, 'dmb-encode', f'--udp=127.0.0.1:{port}', f'--kind={kind}', f'--bitrate={bitrate}',
            f'--source={data.get("source") or ""}']
    if kind == 'tv':
        argv += [f'--video-bitrate={int(data.get("video_bitrate") or 320)}', f'--size={data.get("size") or "320x240"}']
    f = ops.encoder_file(p)
    name = 'odr-dmbencoder-' + ops.slug(label)
    entries = ops._template_entries(p, 'audioenc', name)
    f.add_program(name, entries, tag='DMB', argv=argv)
    return {'station': station_key(svc, sc), 'fs': []}


# ------------------------------------------------------------------ CLI entry points
def outer_main(udp: Optional[str]):
    coder = OuterCoder()
    sock, dest = None, None
    if udp:
        h, _, port = udp.rpartition(':')
        dest = (h or '127.0.0.1', int(port))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    inp = sys.stdin.buffer
    out = sys.stdout.buffer
    while True:
        data = inp.read(188 * 7)
        if not data:
            break
        enc = coder.feed(data)
        if not enc:
            continue
        if sock:
            for i in range(0, len(enc), 204 * 7):
                sock.sendto(enc[i:i + 204 * 7], dest)
        else:
            out.write(enc)
            out.flush()
    return 0


def ffmpeg_cmd(kind: str, source: str, bitrate: int, video_bitrate: int = 320, size: str = '320x240',
               ffmpeg='ffmpeg', he_aac=False) -> List[str]:
    """ffmpeg producing a CBR MPEG-2 TS whose rate after RS(204,188) equals the subchannel bitrate."""
    ts_kbps = bitrate * 188 // 204
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-re', '-i', source]
    if kind == 'tv':
        a_kbps = 64 if he_aac else 96
        cmd += ['-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '1.3',
                '-s', size, '-r', '15', '-b:v', f'{video_bitrate}k', '-maxrate', f'{video_bitrate}k',
                '-bufsize', f'{video_bitrate}k', '-g', '30', '-x264-params', 'nal-hrd=cbr']
    else:
        a_kbps = min(ts_kbps - 16, 128)
        cmd += ['-map', '0:a:0', '-vn']
    if he_aac:
        cmd += ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he_v2' if a_kbps <= 64 else 'aac_he']
    else:
        cmd += ['-c:a', 'aac']
    cmd += ['-b:a', f'{a_kbps}k', '-ar', '48000', '-ac', '2',
            '-f', 'mpegts', '-muxrate', f'{ts_kbps}k', '-mpegts_flags', 'system_b', 'pipe:1']
    return cmd


def encode_main(argv: List[str]):
    import argparse
    ap = argparse.ArgumentParser(prog='odr-mux-manager dmb-encode')
    ap.add_argument('--udp', required=True)
    ap.add_argument('--kind', default='radio', choices=['radio', 'tv'])
    ap.add_argument('--bitrate', type=int, required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--video-bitrate', type=int, default=320)
    ap.add_argument('--size', default='320x240')
    ap.add_argument('--ffmpeg', default='ffmpeg')
    a = ap.parse_args(argv)
    caps = capabilities.detect({})
    he = bool((caps.get('ffmpeg') or {}).get('he_aac'))
    cmd = ffmpeg_cmd(a.kind, a.source, a.bitrate, a.video_bitrate, a.size, a.ffmpeg, he)
    print('running: ' + ' '.join(shlex.quote(x) for x in cmd), file=sys.stderr)
    h, _, port = a.udp.rpartition(':')
    dest = (h or '127.0.0.1', int(port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    coder = OuterCoder()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        while True:
            data = proc.stdout.read(188 * 7)
            if not data:
                break
            enc = coder.feed(data)
            for i in range(0, len(enc), 204 * 7):
                sock.sendto(enc[i:i + 204 * 7], dest)
    finally:
        proc.kill()
    return proc.wait()
