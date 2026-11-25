"""Lossless reader/writer for supervisord ``[program:x]`` config files.

Untouched sections and entries are written back byte-for-byte. Edited entries are
re-rendered; a ``command=`` is rendered in the house style used by ODR setups::

    command=/usr/local/bin/odr-audioenc
     --gst-uri=...
     --bitrate=128
"""
from __future__ import annotations

import re
import shlex
from typing import List, Optional

_HEADER = re.compile(r'^\[(?P<name>[^\]]+)\]\s*(?:[;#].*)?$')
_ENTRY = re.compile(r'^(?P<key>[A-Za-z0-9_.\-]+)\s*[=:]\s?(?P<val>.*)$')


class Entry:
    __slots__ = ('key', 'value', 'raw', 'cont_indent', '_orig', 'is_comment')

    def __init__(self, key: Optional[str], value: str = '', raw: Optional[List[str]] = None,
                 is_comment=False):
        self.key = key
        self.value = value           # continuation lines joined with '\n'
        self.raw = raw               # original lines
        self.cont_indent = ' '
        self.is_comment = is_comment
        self._orig = (key, value)

    def dirty(self):
        return self.raw is None or self._orig != (self.key, self.value)


class Section:
    def __init__(self, name: str):
        self.name = name             # e.g. "program:odr-audioencoder-radio1"
        self.pre: List[str] = []     # comment/blank lines before the header (e.g. "# P01")
        self.header_raw: Optional[str] = None
        self.entries: List[Entry] = []
        self._orig_name = name
        self.file: Optional['SupervisorFile'] = None

    # --------------------------------------------------------------- props
    @property
    def kind(self):
        return self.name.split(':', 1)[0] if ':' in self.name else self.name

    @property
    def program(self) -> Optional[str]:
        return self.name.split(':', 1)[1] if self.name.startswith('program:') else None

    def entry(self, key) -> Optional[Entry]:
        for e in self.entries:
            if e.key == key and not e.is_comment:
                return e
        return None

    def get(self, key, default=None):
        e = self.entry(key)
        return e.value if e else default

    def set(self, key, value):
        if value is None:
            e = self.entry(key)
            if e:
                self.entries.remove(e)
            return
        value = str(value)
        e = self.entry(key)
        if e is None:
            # keep trailing comments/blank lines after the new entry
            idx = len(self.entries)
            while idx > 0 and self.entries[idx - 1].is_comment:
                idx -= 1
            self.entries.insert(idx, Entry(key, value))
        elif e.value != value:
            e.value = value

    # --------------------------------------------------------------- command
    @property
    def argv(self) -> List[str]:
        cmd = self.get('command', '')
        try:
            return shlex.split(cmd.replace('\n', ' '))
        except ValueError:
            return cmd.split()

    @argv.setter
    def argv(self, argv: List[str]):
        e = self.entry('command')
        indent = e.cont_indent if e else ' '
        if not argv:
            self.set('command', None)
            return
        lines = [shlex.quote(argv[0])]
        i = 1
        while i < len(argv):
            a = argv[i]
            # keep a short option and its separate value on one line ("-e tcp://...")
            if (a.startswith('-') and not a.startswith('--') and len(a) == 2
                    and i + 1 < len(argv) and not argv[i + 1].startswith('-')):
                lines.append(indent + a + ' ' + _q(argv[i + 1]))
                i += 2
                continue
            lines.append(indent + _q(a))
            i += 1
        self.set('command', '\n'.join(lines))
        e = self.entry('command')
        e.cont_indent = indent

    @property
    def comment_tag(self) -> Optional[str]:
        """The "# P01" style comment right above the header, if any."""
        for line in reversed(self.pre):
            s = line.strip()
            if s.startswith(('#', ';')):
                return s.lstrip('#;').strip()
            if s:
                break
        return None

    @comment_tag.setter
    def comment_tag(self, tag: str):
        for i in range(len(self.pre) - 1, -1, -1):
            s = self.pre[i].strip()
            if s.startswith(('#', ';')):
                self.pre[i] = '# ' + tag
                return
            if s:
                break
        self.pre.append('# ' + tag)

    def dirty(self):
        return self.header_raw is None or self.name != self._orig_name or any(e.dirty() for e in self.entries)


def _q(s: str) -> str:
    # supervisor uses shlex; quote only when needed so the house style stays clean
    if s and re.fullmatch(r'[A-Za-z0-9_@%+=:,./\-?&~*\[\]#!]+', s):
        return s
    if '=' in s and s.startswith('--'):
        k, v = s.split('=', 1)
        if re.fullmatch(r'[A-Za-z0-9_@%+=:,./\-?&~*\[\]#!]*', v):
            return s
        return k + '=' + shlex.quote(v)
    return shlex.quote(s)


class SupervisorFile:
    def __init__(self, text: str = '', path=None):
        self.path = path
        self.newline = '\r\n' if '\r\n' in text else '\n'
        self.final_newline = text.endswith('\n') or text == ''
        self.head: List[str] = []    # lines before the first section
        self.sections: List[Section] = []
        self.tail: List[str] = []
        self._parse(text)

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8', errors='surrogateescape', newline='') as f:
            return cls(f.read(), path)

    def _parse(self, text):
        lines = text.split(self.newline) if text else []
        if lines and lines[-1] == '':
            lines.pop()
        cur: Optional[Section] = None
        buf: List[str] = []
        entry: Optional[Entry] = None
        for line in lines:
            if entry is not None and line[:1] in (' ', '\t') and line.strip():
                entry.raw.append(line)
                entry.value += '\n' + line.strip()
                if len(entry.raw) == 2:
                    entry.cont_indent = line[:len(line) - len(line.lstrip())]
                entry._orig = (entry.key, entry.value)
                continue
            entry = None
            m = _HEADER.match(line)
            if m:
                cur = Section(m.group('name').strip())
                cur.header_raw = line
                cur.pre = buf
                cur.file = self
                buf = []
                self.sections.append(cur)
                continue
            s = line.strip()
            if not s or s.startswith(('#', ';')):
                buf.append(line)
                continue
            m = _ENTRY.match(line)
            if m and cur is not None:
                for b in buf:
                    cur.entries.append(Entry(None, b, [b], is_comment=True))
                buf = []
                entry = Entry(m.group('key'), m.group('val').strip(), [line])
                cur.entries.append(entry)
                continue
            # anything else: keep verbatim
            if cur is None:
                buf.append(line)
            else:
                for b in buf:
                    cur.entries.append(Entry(None, b, [b], is_comment=True))
                buf = []
                cur.entries.append(Entry(None, line, [line], is_comment=True))
        if cur is None:
            self.head = buf
        else:
            self.tail = buf

    # ---------------------------------------------------------------- output
    def dumps(self) -> str:
        out: List[str] = list(self.head)
        for sec in self.sections:
            out.extend(sec.pre)
            if sec.header_raw is not None and sec.name == sec._orig_name:
                out.append(sec.header_raw)
            else:
                out.append(f'[{sec.name}]')
            for e in sec.entries:
                if e.is_comment:
                    out.append(e.value if e.raw is None else e.raw[0])
                elif not e.dirty():
                    out.extend(e.raw)
                else:
                    vlines = e.value.split('\n')
                    out.append(f'{e.key}={vlines[0]}')
                    for v in vlines[1:]:
                        out.append(v if v[:1] in (' ', '\t') else e.cont_indent + v)
        out.extend(self.tail)
        text = self.newline.join(out)
        if out and self.final_newline:
            text += self.newline
        return text

    # --------------------------------------------------------------- helpers
    def programs(self) -> List[Section]:
        return [s for s in self.sections if s.program]

    def program(self, name) -> Optional[Section]:
        for s in self.sections:
            if s.program == name:
                return s
        return None

    def add_program(self, name, entries: dict, tag: Optional[str] = None, after: Optional[Section] = None,
                    argv: Optional[List[str]] = None) -> Section:
        sec = Section('program:' + name)
        sec.file = self
        sec.pre = ([''] if self.sections or self.head else []) + ([f'# {tag}'] if tag else [])
        if argv:
            sec.argv = argv
        for k, v in entries.items():
            if k == 'command' and argv:
                continue
            sec.set(k, v)
        # the "command" entry should come first
        sec.entries.sort(key=lambda e: 0 if e.key == 'command' else 1)
        if after is not None and after in self.sections:
            self.sections.insert(self.sections.index(after) + 1, sec)
        else:
            self.sections.append(sec)
        return sec

    def remove_section(self, sec: Section):
        if sec in self.sections:
            self.sections.remove(sec)
