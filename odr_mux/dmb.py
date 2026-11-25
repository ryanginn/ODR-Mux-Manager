"""T-DMB support (experimental).

Current odr-dabmux accepts ``type dmb`` subchannels but, since its input refactor, passes the
bytes through raw: the old DMB input that added the outer coding (Reed-Solomon (204,188) +
convolutional byte interleaver, I=12 M=17) is "unported". This module provides that outer
coder (a byte-exact port of odr-dabmux src/Dmb.cpp + Interleaver.cpp + lib/ReedSolomon) and an
encoder pipeline: ffmpeg -> MPEG-2 TS -> outer coding -> paced FIFO -> odr-dabmux
(inputproto fifo, nonblock true). The UDP input of odr-dabmux is not used: its readFrame() never
removes consumed bytes, so it repeats the first frame forever.

ffmpeg encodes (any input it can open) to a plain TS; tdmb.TDMBMux re-packs it with MPEG-4 Systems
(IOD, OD, BIFS, SL packets) as T-DMB (TS 102 428) requires.
"""
from __future__ import annotations

import collections
import os
import shlex
import stat
import threading
from pathlib import Path
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
        {'label': 'Input path', 'ok': True, 'detail':
            'non-blocking FIFO (the odr-dabmux UDP input repeats one frame forever, so it is not used)'},
        {'label': 'ffmpeg', 'ok': bool(ff), 'detail': 'found' if ff else 'not found'},
        {'label': 'H.264 encoder (DMB TV)', 'ok': bool(ff and ff.get('h264')), 'warn': not (ff and ff.get('h264')),
         'detail': 'libx264' if ff and ff.get('libx264') else ('hardware encoder' if ff and ff.get('h264') else 'missing')},
        {'label': 'HE-AAC encoder', 'ok': bool(ff and ff.get('he_aac')), 'warn': True,
         'detail': 'libfdk_aac' if ff and ff.get('he_aac') else 'only AAC-LC (ffmpeg built without libfdk_aac): works, uses more bitrate'},
        {'label': 'MPEG-4 Systems packaging (TS 102 428)', 'ok': True,
         'detail': 'IOD + OD/BIFS + SL-packetized H.264/AAC (built in, verified with GPAC)'},
        {'label': 'GPAC (optional, for checking streams)', 'ok': bool(caps['tools'].get('gpac')), 'warn': True,
         'detail': 'found' if caps['tools'].get('gpac') else 'not installed (sudo apt install gpac)'},
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
    instr.append({'title': 'Add a DMB service here', 'text': 'The manager creates the subchannel (type dmb, non-blocking FIFO input) and a supervisor program that runs ffmpeg, packs the stream as T-DMB and adds the outer coding.'})
    ready = bool(dm and ff)
    note = ('Tested through odr-dabmux: the stream taken back out of the mux output passes the RS check and decodes. '
            'T-DMB needs a lot of capacity (DMB TV ~300–550 kbps ≈ 200–400 CU) and few receivers outside Korea '
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
    if not data.get('source'):
        raise ops.OpError('Give a source ffmpeg can open (file, URL, device or test source).')
    try:
        budget(kind, bitrate, int(data.get('video_bitrate') or 320), data.get('audio_bitrate'), False,
               int(data.get('fps') or 15))
    except ValueError as e:
        raise ops.OpError(str(e))
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
                 ('inputproto', 'fifo')):
        sc.append(Node(k, v))
    # odr-dabmux's UDP input repeats the first frame forever (it never consumes its buffer), so
    # DMB goes through a non-blocking FIFO that the encoder fills at exactly the subchannel rate.
    fifo = str(Path(p.root) / 'dmb' / (ops.slug(label) + '.fifo'))
    u = Node('inputuri', fifo); u.quoted = True; sc.append(u)
    sc.append(Node('nonblock', 'true'))
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
    argv = [exe, 'dmb-encode', f'--fifo={fifo}', f'--kind={kind}', f'--bitrate={bitrate}',
            f'--source={data.get("source") or ""}']
    if data.get('input_format'):
        argv.append(f'--input-format={data["input_format"]}')
    if data.get('input_opts'):
        argv.append(f'--input-opts={data["input_opts"]}')
    if data.get('audio_bitrate'):
        argv.append(f'--audio-bitrate={int(data["audio_bitrate"])}')
    if kind == 'tv':
        argv += [f'--video-bitrate={int(data.get("video_bitrate") or 320)}', f'--size={data.get("size") or "320x240"}',
                 f'--fps={int(data.get("fps") or 15)}']
    f = ops.encoder_file(p)
    name = 'odr-dmbencoder-' + ops.slug(label)
    entries = ops._template_entries(p, 'audioenc', name)
    f.add_program(name, entries, tag='DMB', argv=argv)
    return {'station': station_key(svc, sc), 'fs': [{'op': 'mkfifo', 'path': fifo}]}


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


def budget(kind: str, bitrate: int, video_bitrate: int = 320, audio_bitrate: Optional[int] = None,
           he_aac: bool = False, fps: int = 15):
    """Split the subchannel between audio and video, after the fixed costs of T-DMB packaging.

    After RS(204,188) the TS gets bitrate*188/204. Every access unit becomes its own PES + SL packet
    (~23 bytes of headers plus on average half a TS packet of stuffing), and PAT/PMT (every 200 ms)
    and the OD/BIFS carousel (every 500 ms) take their share too. Returns (video_kbps, audio_kbps)."""
    cap = bitrate * 188 / 204
    psi = 2 * 188 * 8 * 5 / 1000                 # PAT + PMT, 5 times a second
    carousel = 2 * 188 * 8 * 2 / 1000            # OD + BIFS, twice a second
    per_au = (14 + 9 + 94) * 8 / 1000            # PES + SL header + average stuffing, in kbit
    audio_aus = 48000 / (2048 if he_aac else 1024)
    fixed = psi + carousel + audio_aus * per_au + (fps * (per_au + 0.04) if kind == 'tv' else 0)
    usable = (cap - fixed) * (184 / 188) * 0.95  # TS headers, 5 % margin for encoder rate wobble
    if usable < 24:
        raise ValueError(f'{bitrate} kbps is too small for a T-DMB {kind} service')
    if kind == 'tv':
        a = int(audio_bitrate or (48 if he_aac else 64))
        v = int(min(video_bitrate, (usable - a) * 0.9))   # x264 overshoots its target a little
        if v < 64:
            raise ValueError(f'{bitrate} kbps leaves only {v} kbps for video; use a bigger subchannel')
        return v, a
    a = int(min(audio_bitrate or 192, usable))
    return 0, a // 8 * 8


LIVE_DEVICES = {'v4l2', 'video4linux2', 'alsa', 'pulse', 'jack', 'decklink', 'x11grab', 'kmsgrab', 'fbdev',
                'avfoundation', 'dshow', 'gdigrab', 'openal', 'oss', 'sndio'}


def ffmpeg_cmd(kind: str, source: str, bitrate: int, video_bitrate: int = 320, size: str = '320x240',
               ffmpeg='ffmpeg', he_aac=False, input_format: str = '', input_opts: str = '', fps: int = 15,
               audio_bitrate: Optional[int] = None, realtime: bool = True) -> List[str]:
    """ffmpeg reads *anything it can open* (files, http/hls/rtmp/srt streams, v4l2/decklink/alsa/pulse
    devices, lavfi test sources...) and writes a plain MPEG-TS that tdmb.TDMBMux turns into T-DMB."""
    v_kbps, a_kbps = budget(kind, bitrate, video_bitrate, audio_bitrate, he_aac, fps)
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'warning']
    if input_opts:
        cmd += shlex.split(input_opts)
    if realtime and input_format not in LIVE_DEVICES:
        cmd += ['-re']                       # files, streams, test sources: real-time speed (devices pace themselves)
    if input_format:
        cmd += ['-f', input_format]
    cmd += ['-i', source]
    if kind == 'tv':
        cmd += ['-map', '0:v:0', '-map', '0:a:0?',
                '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '1.3', '-pix_fmt', 'yuv420p',
                '-vf', f'scale={size.replace("x", ":")}:force_original_aspect_ratio=decrease,'
                       f'pad={size.replace("x", ":")}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-r', str(fps), '-bf', '0', '-g', str(fps * 2), '-tune', 'zerolatency',
                '-b:v', f'{v_kbps}k', '-maxrate', f'{v_kbps}k', '-bufsize', f'{v_kbps}k']
    else:
        cmd += ['-map', '0:a:0', '-vn']
    if he_aac:
        cmd += ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he_v2' if a_kbps <= 48 else 'aac_he']
    else:
        cmd += ['-c:a', 'aac']
    cmd += ['-b:a', f'{a_kbps}k', '-ar', '48000', '-ac', '2', '-f', 'mpegts', 'pipe:1']
    return cmd


NULL_TS = b'\x47\x1f\xff\x10' + b'\xff' * 184


class Pacer:
    """Emit exactly bitrate*3 coded bytes per 24 ms frame; fill gaps with null TS packets so the
    interleaved stream is never interrupted (a gap would corrupt 12 x 17 bytes of history)."""

    MAX_QUEUE = 2000          # TS packets (~2-6 s depending on bitrate)

    def __init__(self, bitrate: int, block: bool = False):
        self.frame = bitrate * 3
        self.coder = OuterCoder()
        self.queue = collections.deque()
        self.pending = b''
        self.nulls = 0
        self.block = block
        self.cond = threading.Condition()

    def put_ts(self, data: bytes):
        with self.cond:
            if self.block:
                # back-pressure: a source faster than real time (file, test pattern) simply waits;
                # dropping packets would break PES/SL packets and the interleaver history
                while len(self.queue) >= self.MAX_QUEUE:
                    self.cond.wait(0.5)
            self.queue.append(data)

    def next_frame(self) -> bytes:
        with self.cond:
            while len(self.pending) < self.frame:
                if self.queue:
                    pkt = self.queue.popleft()
                else:
                    pkt = NULL_TS
                    self.nulls += 1
                self.pending += self.coder.feed(pkt)
            out, self.pending = self.pending[:self.frame], self.pending[self.frame:]
            self.cond.notify_all()
        return out


def encode_main(argv: List[str]):
    import argparse
    ap = argparse.ArgumentParser(prog='odr-mux-manager dmb-encode')
    ap.add_argument('--fifo', help='write to this FIFO (odr-dabmux inputproto fifo, nonblock true)')
    ap.add_argument('--udp', help='send UDP to host:port instead')
    ap.add_argument('--kind', default='radio', choices=['radio', 'tv'])
    ap.add_argument('--bitrate', type=int, required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--video-bitrate', type=int, default=320)
    ap.add_argument('--size', default='320x240')
    ap.add_argument('--fps', type=int, default=15)
    ap.add_argument('--audio-bitrate', type=int)
    ap.add_argument('--input-format', default='')
    ap.add_argument('--input-opts', default='')
    ap.add_argument('--plain-ts', action='store_true', help='skip MPEG-4 Systems (T-DMB) packaging')
    ap.add_argument('--ffmpeg', default='ffmpeg')
    a = ap.parse_args(argv)
    if not a.fifo and not a.udp:
        ap.error('--fifo or --udp is required')
    caps = capabilities.detect({})
    he = bool((caps.get('ffmpeg') or {}).get('he_aac'))
    cmd = ffmpeg_cmd(a.kind, a.source, a.bitrate, a.video_bitrate, a.size, a.ffmpeg, he,
                     a.input_format, a.input_opts, a.fps, a.audio_bitrate)
    v_kbps, a_kbps = budget(a.kind, a.bitrate, a.video_bitrate, a.audio_bitrate, he, a.fps)
    from .tdmb import TSDemux, TDMBMux
    w, h = (int(x) for x in a.size.split('x'))
    demux = None if a.plain_ts else TSDemux()
    mux = None if a.plain_ts else TDMBMux(a.kind == 'tv', w, h, v_kbps * 1000, a_kbps * 1000)
    print('running: ' + ' '.join(shlex.quote(x) for x in cmd), file=sys.stderr)
    if a.fifo:
        if not os.path.exists(a.fifo):
            os.makedirs(os.path.dirname(a.fifo), exist_ok=True)
            os.mkfifo(a.fifo, 0o664)
        sink_fd = os.open(a.fifo, os.O_WRONLY)
        send = lambda b: os.write(sink_fd, b)
    else:
        h, _, port = a.udp.rpartition(':')
        dest = (h or '127.0.0.1', int(port))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send = lambda b: sock.sendto(b, dest)
    pacer = Pacer(a.bitrate, block=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    done = threading.Event()

    def reader():
        buf = b''
        while True:
            data = proc.stdout.read(188 * 8)
            if not data:
                break
            if demux is not None:
                for item in demux.feed(data):
                    for pkt in mux.add(*item):
                        pacer.put_ts(pkt)
                continue
            buf += data
            n = len(buf) // 188 * 188
            for i in range(0, n, 188):
                pacer.put_ts(buf[i:i + 188])
            buf = buf[n:]
        done.set()
    threading.Thread(target=reader, daemon=True).start()
    t0 = time.monotonic()
    k = 0
    try:
        for _ in range(4):          # small head start so odr-dabmux never runs dry
            send(pacer.next_frame())
        while not (done.is_set() and not pacer.queue):
            k += 1
            delay = t0 + k * 0.024 - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            send(pacer.next_frame())
            if k % 2500 == 0:
                print(f'dmb: {k} frames, {pacer.nulls} null packets inserted', file=sys.stderr)
    finally:
        proc.kill()
    return proc.wait()
