"""Argument models for odr-audioenc and odr-padenc (option tables taken from their getopt specs)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# name -> (short, takes_value)
AUDIOENC_OPTS: Dict[str, Tuple[Optional[str], bool]] = {
    'bitrate': ('b', True), 'bandwidth': ('B', True), 'audio-gain': ('g', True), 'vlc-gain': (None, True),
    'channels': ('c', True), 'dabmode': (None, True), 'dabpsy': (None, True), 'device': ('d', True),
    'edi': ('e', True), 'fec': (None, True), 'timestamp-delay': ('T', True), 'decode': (None, True),
    'format': ('f', True), 'gst-uri': ('G', True), 'gst-pipeline': (None, True), 'identifier': (None, True),
    'input': ('i', True), 'jack': ('j', True), 'output': ('o', True), 'pad': ('p', True),
    'pad-socket': ('P', True), 'rate': ('r', True), 'secret-key': ('k', True), 'silence': ('s', True),
    'startup-check': (None, True), 'stats': ('S', True), 'vlc-cache': ('C', True), 'vlc-uri': ('v', True),
    'vlc-opt': ('L', True), 'write-icy-text': ('w', True), 'write-icy-text-dl-plus': ('W', False),
    'aaclc': (None, False), 'dab': ('a', False), 'drift-comp': ('D', False), 'edi-verbose': (None, False),
    'fifo-silence': (None, False), 'help': ('h', False), 'level': ('l', False), 'no-afterburner': ('A', False),
    'ps': (None, False), 'restart': ('R', False), 'sbr': (None, False), 'verbosity': ('V', False),
}

PADENC_OPTS: Dict[str, Tuple[Optional[str], bool]] = {
    'charset': ('c', True), 'raw-dls': ('C', False), 'remove-dls': ('r', False), 'dir': ('d', True),
    'erase': ('e', False), 'output': ('o', True), 'dls': ('t', True), 'item-state': ('I', True),
    'sleep': ('s', True), 'max-slide-size': ('m', True), 'raw-slides': ('R', False), 'help': ('h', False),
    'label': ('l', True), 'label-ins': ('L', True), 'xpad-interval': ('X', True), 'verbose': ('v', False),
    'dump-current-slide': (None, True), 'dump-completed-slide': (None, True),
}

INPUT_KINDS = {
    'gst-uri': 'gstreamer', 'gst-pipeline': 'gstreamer', 'vlc-uri': 'vlc', 'device': 'alsa',
    'jack': 'jack', 'input': 'file',
}

# options whose values are local filesystem paths (used for renumbering and impact reports)
PATH_OPTS = {'audioenc': {'stats', 'write-icy-text', 'input', 'decode'},
             'padenc': {'dir', 'dls', 'dump-current-slide', 'dump-completed-slide'}}

# options that may repeat
REPEATABLE = {'output', 'edi', 'vlc-opt', 'dls'}


def tool_of(argv: List[str]) -> Optional[str]:
    if not argv:
        return None
    b = argv[0].rsplit('/', 1)[-1]
    if 'odr-audioenc' in b:
        return 'audioenc'
    if 'odr-padenc' in b:
        return 'padenc'
    if 'odr-dabmux' in b:
        return 'dabmux'
    if 'odr-dabmod' in b:
        return 'dabmod'
    if 'ffmpeg' in b:
        return 'ffmpeg'
    if 'odr-mux-manager' in b:
        return 'manager'
    return None


@dataclass
class Opt:
    name: str                # long name, or raw token for unknown/positional
    value: Optional[str] = None
    known: bool = True
    style: str = 'long='     # 'long=', 'long ', 'short ', 'short', 'raw'


@dataclass
class Args:
    tool: str
    exe: str
    opts: List[Opt] = field(default_factory=list)

    @classmethod
    def parse(cls, argv: List[str]) -> 'Args':
        tool = tool_of(argv) or 'unknown'
        spec = AUDIOENC_OPTS if tool == 'audioenc' else PADENC_OPTS if tool == 'padenc' else {}
        short = {v[0]: k for k, v in spec.items() if v[0]}
        a = cls(tool, argv[0] if argv else '')
        i = 1
        while i < len(argv):
            t = argv[i]
            if t.startswith('--') and len(t) > 2:
                name, eq, val = t[2:].partition('=')
                if name in spec:
                    takes = spec[name][1]
                    if takes and not eq:
                        val = argv[i + 1] if i + 1 < len(argv) else ''
                        a.opts.append(Opt(name, val, True, 'long '))
                        i += 2
                        continue
                    a.opts.append(Opt(name, val if eq else None, True, 'long='))
                else:
                    a.opts.append(Opt(t, None, False, 'raw'))
            elif t.startswith('-') and len(t) >= 2 and t[1] in short:
                name = short[t[1]]
                takes = spec[name][1]
                if takes:
                    if len(t) > 2:
                        a.opts.append(Opt(name, t[2:], True, 'short'))
                    else:
                        val = argv[i + 1] if i + 1 < len(argv) else ''
                        a.opts.append(Opt(name, val, True, 'short '))
                        i += 2
                        continue
                else:
                    a.opts.append(Opt(name, None, True, 'short'))
                    # bundled flags like -DA
                    for ch in t[2:]:
                        if ch in short:
                            a.opts.append(Opt(short[ch], None, True, 'short'))
            else:
                a.opts.append(Opt(t, None, False, 'raw'))
            i += 1
        return a

    def spec(self):
        return AUDIOENC_OPTS if self.tool == 'audioenc' else PADENC_OPTS if self.tool == 'padenc' else {}

    def to_argv(self) -> List[str]:
        out = [self.exe]
        spec = self.spec()
        for o in self.opts:
            if not o.known:
                out.append(o.name)
                continue
            s = spec.get(o.name, (None, True))[0]
            if o.value is None:
                out.append(f'-{s}' if o.style.startswith('short') and s else f'--{o.name}')
            elif o.style == 'short ' and s:
                out += [f'-{s}', o.value]
            elif o.style == 'short' and s:
                out.append(f'-{s}{o.value}')
            elif o.style == 'long ':
                out += [f'--{o.name}', o.value]
            else:
                out.append(f'--{o.name}={o.value}')
        return out

    # ------------------------------------------------------------ access
    def has(self, name) -> bool:
        return any(o.known and o.name == name for o in self.opts)

    def get(self, name, default=None):
        for o in self.opts:
            if o.known and o.name == name:
                return o.value if o.value is not None else True
        return default

    def get_all(self, name) -> List[str]:
        return [o.value for o in self.opts if o.known and o.name == name]

    def set(self, name, value=True):
        """Set an option. value=True for flags, None/False to remove, str for values."""
        if value is None or value is False:
            self.opts = [o for o in self.opts if not (o.known and o.name == name)]
            return
        v = None if value is True else str(value)
        for o in self.opts:
            if o.known and o.name == name:
                o.value = v
                return
        # insert near related options to keep the house style readable
        self.opts.append(Opt(name, v, True, 'long=' if v is not None else 'long='))
        self._reorder_new(name)

    def set_all(self, name, values: List[str]):
        idx = next((i for i, o in enumerate(self.opts) if o.known and o.name == name), None)
        old = [o for o in self.opts if o.known and o.name == name]
        style = old[0].style if old else ('short ' if name in ('edi', 'output') and self.tool == 'audioenc' else 'long=')
        self.opts = [o for o in self.opts if not (o.known and o.name == name)]
        new = [Opt(name, v, True, style) for v in values]
        if idx is None:
            self.opts.extend(new)
            for v in new:
                pass
            if new:
                self._reorder_new(name, len(new))
        else:
            self.opts[idx:idx] = new

    _ORDER_AUDIO = ['gst-uri', 'gst-pipeline', 'vlc-uri', 'vlc-cache', 'vlc-opt', 'device', 'jack', 'input', 'format',
                    'fifo-silence', 'drift-comp', 'silence', 'audio-gain', 'bitrate', 'rate', 'channels', 'dab',
                    'dabmode', 'dabpsy', 'aaclc', 'sbr', 'ps', 'no-afterburner', 'bandwidth', 'pad', 'pad-socket',
                    'write-icy-text', 'write-icy-text-dl-plus', 'identifier', 'edi', 'output', 'fec',
                    'timestamp-delay', 'secret-key', 'startup-check', 'stats', 'level', 'restart']
    _ORDER_PAD = ['dir', 'sleep', 'raw-slides', 'erase', 'max-slide-size', 'dls', 'charset', 'raw-dls', 'remove-dls',
                  'item-state', 'output', 'label', 'label-ins', 'xpad-interval', 'verbose']

    def _reorder_new(self, name, n=1):
        order = self._ORDER_AUDIO if self.tool == 'audioenc' else self._ORDER_PAD if self.tool == 'padenc' else None
        if not order or name not in order:
            return
        new = self.opts[-n:]
        del self.opts[-n:]
        rank = order.index(name)
        pos = len(self.opts)
        for i, o in enumerate(self.opts):
            if o.known and o.name in order and order.index(o.name) > rank:
                pos = i
                break
        self.opts[pos:pos] = new


# ---------------------------------------------------------------- audio helpers
def codec_of(a: Args) -> str:
    """'mp2', 'aaclc', 'he' or 'hev2' as odr-audioenc would choose."""
    if a.has('dab'):
        return 'mp2'
    if a.has('ps'):
        return 'hev2'
    if a.has('sbr'):
        return 'he'
    if a.has('aaclc'):
        return 'aaclc'
    return 'auto'


def effective_codec(a: Args) -> str:
    """Codec odr-audioenc will actually use (resolves 'auto' like odr-audioenc.cpp does)."""
    c = codec_of(a)
    if c != 'auto':
        return c
    try:
        idx = int(a.get('bitrate', 64)) // 8
        ch = int(a.get('channels', 2))
    except (TypeError, ValueError):
        return 'auto'
    if ch == 2 and idx <= 6:
        return 'hev2'
    if (ch == 1 and idx <= 8) or (ch == 2 and idx <= 10):
        return 'he'
    return 'aaclc'


def set_codec(a: Args, codec: str):
    for f in ('dab', 'dabmode', 'dabpsy', 'aaclc', 'sbr', 'ps', 'no-afterburner', 'bandwidth'):
        if codec == 'mp2' and f in ('dabmode', 'dabpsy'):
            continue
        if codec != 'mp2' and f in ('no-afterburner', 'bandwidth'):
            continue
        a.set(f, None)
    if codec == 'mp2':
        a.set('dab')
    elif codec == 'aaclc':
        a.set('aaclc')
    elif codec == 'he':
        a.set('sbr')
    elif codec == 'hev2':
        a.set('sbr')
        a.set('ps')


def input_of(a: Args):
    for o in a.opts:
        if o.known and o.name in INPUT_KINDS:
            return INPUT_KINDS[o.name], o.name, o.value
    return None, None, None


def set_input(a: Args, kind: str, value: str):
    """Switch input backend. kind: gstreamer|vlc|alsa|jack|file. Backend options of the
    old kind (vlc-cache etc.) are dropped when they don't apply."""
    opt = {'gstreamer': 'gst-uri', 'vlc': 'vlc-uri', 'alsa': 'device', 'jack': 'jack', 'file': 'input'}[kind]
    old_idx = None
    for i, o in enumerate(a.opts):
        if o.known and o.name in INPUT_KINDS:
            old_idx = i
            break
    a.opts = [o for o in a.opts if not (o.known and o.name in INPUT_KINDS)]
    if kind != 'vlc':
        for f in ('vlc-cache', 'vlc-opt', 'vlc-gain'):
            a.set(f, None)
    if kind != 'file':
        for f in ('format', 'fifo-silence'):
            a.set(f, None)
    new = Opt(opt, value, True, 'long=')
    if old_idx is None:
        a.opts.insert(0, new)
    else:
        a.opts.insert(min(old_idx, len(a.opts)), new)


_TCP = re.compile(r'^(?:zmq\+)?tcp://(?P<host>\[[^\]]*\]|[^:/]+):(?P<port>\d+)')
LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1', '[::1]', '0.0.0.0', '*', 'lo', '[::]', '::'}


def parse_tcp(uri: str):
    m = _TCP.match(uri or '')
    if not m:
        return None, None
    return m.group('host'), int(m.group('port'))


def is_local(host: Optional[str], extra_local=()) -> bool:
    return host is not None and (host in LOCAL_HOSTS or host in extra_local)


def audio_outputs(a: Args):
    """List of dicts {kind: edi|zmq, uri, host, port, local}."""
    out = []
    for kind in ('edi', 'output'):
        for v in a.get_all(kind):
            h, p = parse_tcp(v)
            out.append({'kind': 'edi' if kind == 'edi' else 'zmq', 'uri': v, 'host': h, 'port': p,
                        'local': is_local(h)})
    return out


def pad_len_hint(pad: int, bitrate: int) -> str:
    if not pad:
        return 'No PAD: DLS and slideshow are off.'
    kbps = pad * 8 / 24 * (1 if True else 1)
    return f'{pad} bytes per frame ≈ {kbps:.1f} kbps of the {bitrate} kbps go to DLS/slides.'


VALID_PAD_LENGTHS = [6, 8, 12, 14, 16, 18, 20, 22, 26, 30, 34, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74, 78, 82, 86,
                     90, 94, 98, 102, 106, 110, 114, 118, 122, 126, 134, 142, 150, 158, 166, 174, 182, 190, 198]
