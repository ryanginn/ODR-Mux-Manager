"""Comment-preserving reader/writer for boost::property_tree INFO files (odr-dabmux .mux).

The goal is a *lossless* round trip: a file that is parsed and written back without
edits is byte-identical. Every node remembers the raw text it came from; only nodes that
are edited (or created) are re-rendered, using the indentation of their surroundings.
"""
from __future__ import annotations

import re
from typing import Iterator, List, Optional

_SPECIAL = set(' \t;{}"')


def _quote(v: str) -> str:
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t') + '"'


def format_value(v: str, quoted: bool = False) -> str:
    if v == '' or quoted or any(c in _SPECIAL for c in v):
        return _quote(v)
    return v


class ParseError(ValueError):
    def __init__(self, msg, line=None):
        super().__init__(f"line {line}: {msg}" if line else msg)
        self.line = line


class Node:
    __slots__ = ('key', 'value', 'children', 'pre', 'raw', 'raw_close', 'tail',
                 'indent', 'quoted', 'comment', 'brace_next_line', '_orig', 'parent', 'line')

    def __init__(self, key: str, value: Optional[str] = None, children: Optional[list] = None):
        self.key = key
        self.value = value
        self.children: Optional[List[Node]] = children
        self.pre: List[str] = []         # raw comment/blank lines before this node
        self.raw: Optional[str] = None   # raw header line(s) as read
        self.raw_close: Optional[str] = None
        self.tail: List[str] = []        # raw lines between last child and '}'
        self.indent: Optional[str] = None
        self.quoted = False
        self.comment: Optional[str] = None  # inline '; ...' comment on header line
        self.brace_next_line = False
        self._orig = None
        self.parent: Optional[Node] = None
        self.line = 0
        if children is not None:
            for c in children:
                c.parent = self

    # ------------------------------------------------------------------ queries
    @property
    def is_block(self) -> bool:
        return self.children is not None

    def dirty(self) -> bool:
        return self.raw is None or self._orig != (self.key, self.value, self.is_block)

    def __iter__(self) -> Iterator['Node']:
        return iter(self.children or [])

    def __repr__(self):
        return f"Node({self.key!r}, {self.value!r}, {len(self.children) if self.children is not None else '-'})"

    def child(self, key: str) -> Optional['Node']:
        for c in self.children or []:
            if c.key == key:
                return c
        return None

    def find(self, path: str) -> Optional['Node']:
        n = self
        for part in path.split('.'):
            if n is None:
                return None
            n = n.child(part)
        return n

    def get(self, path: str, default=None):
        n = self.find(path)
        if n is None or n.value is None:
            return default
        return n.value

    def keys(self):
        return [c.key for c in self.children or []]

    def index(self) -> int:
        return self.parent.children.index(self)

    # ------------------------------------------------------------------ edits
    def _ensure_block(self):
        if self.children is None:
            self.children = []

    def set(self, key: str, value, quoted: Optional[bool] = None) -> 'Node':
        """Set (or create) a leaf child. ``value=None`` removes it."""
        if value is None:
            self.remove(key)
            return None
        value = str(value)
        n = self.child(key)
        if n is None:
            n = Node(key, value)
            if quoted:
                n.quoted = True
            self.append(n)
        else:
            if n.value != value:
                n.value = value
            if quoted is not None and n.quoted != quoted:
                n.quoted = quoted
                n.raw = None if n.value is not None else n.raw
        return n

    def block(self, key: str, create: bool = True) -> Optional['Node']:
        n = self.child(key)
        if n is None and create:
            n = Node(key, None, [])
            self.append(n)
        elif n is not None and n.children is None and create:
            n.children = []
        return n

    def append(self, node: 'Node', index: Optional[int] = None) -> 'Node':
        self._ensure_block()
        node.parent = self
        if index is None:
            self.children.append(node)
        else:
            self.children.insert(index, node)
        return node

    def remove(self, key_or_node) -> Optional['Node']:
        if self.children is None:
            return None
        n = key_or_node if isinstance(key_or_node, Node) else self.child(key_or_node)
        if n is not None and n in self.children:
            self.children.remove(n)
            n.parent = None
        return n

    def rename(self, new_key: str):
        self.key = new_key

    def to_dict(self):
        """Plain JSON-able view: leaves -> str, blocks -> {key: ...} (dupes as list)."""
        if self.children is None:
            return self.value
        out = {}
        for c in self.children:
            v = c.to_dict()
            if c.key in out:
                if not isinstance(out[c.key], list) or not getattr(out[c.key], '_dup', False):
                    lst = _DupList([out[c.key]])
                    out[c.key] = lst
                out[c.key].append(v)
            else:
                out[c.key] = v
        if self.value is not None:
            out['_value'] = self.value
        return out


class _DupList(list):
    _dup = True


# ---------------------------------------------------------------------- parsing
def _read_token(s: str, i: int, ln: int):
    """Read a key or value token starting at s[i]; return (token, quoted, new_i)."""
    if s[i] == '"':
        out = []
        i += 1
        while True:
            if i >= len(s):
                raise ParseError('unterminated string', ln)
            c = s[i]
            if c == '\\' and i + 1 < len(s):
                nxt = s[i + 1]
                out.append({'n': '\n', 't': '\t', '"': '"', '\\': '\\', '0': '\0',
                            'a': '\a', 'b': '\b', 'f': '\f', 'r': '\r', 'v': '\v'}.get(nxt, nxt))
                i += 2
                continue
            if c == '"':
                return ''.join(out), True, i + 1
            out.append(c)
            i += 1
    j = i
    while j < len(s) and s[j] not in ' \t;{}"':
        j += 1
    return s[i:j], False, j


def _skip_ws(s, i):
    while i < len(s) and s[i] in ' \t':
        i += 1
    return i


class InfoDoc:
    """A parsed .mux file. ``root`` is a block Node whose children are the sections."""

    def __init__(self, text: str = ''):
        self.newline = '\r\n' if '\r\n' in text else '\n'
        self.final_newline = text.endswith('\n') or text == ''
        self.root = Node('', None, [])
        self._parse(text)

    @classmethod
    def load(cls, path) -> 'InfoDoc':
        with open(path, 'r', encoding='utf-8', errors='surrogateescape', newline='') as f:
            return cls(f.read())

    def _parse(self, text: str):
        lines = text.split(self.newline) if text else []
        if lines and lines[-1] == '':
            lines.pop()
        stack = [self.root]
        pending: List[str] = []
        last: Optional[Node] = None  # last node created at the current level, for '{' on next line
        for ln, line in enumerate(lines, 1):
            s = line
            i = _skip_ws(s, 0)
            indent = s[:i]
            if i >= len(s) or s[i] == ';':
                pending.append(line)
                continue
            if s.startswith('#include', i):
                n = Node('#include', s[i + 8:].strip().strip('"'))
                n.raw, n.pre, n.indent, n.line = line, pending, indent, ln
                n._orig = (n.key, n.value, False)
                pending = []
                stack[-1].append(n)
                last = None
                continue
            if s[i] == '}':
                if len(stack) == 1:
                    raise ParseError("unexpected '}'", ln)
                blk = stack.pop()
                blk.tail = pending
                blk.raw_close = line
                pending = []
                last = blk
                rest = _skip_ws(s, i + 1)
                if rest < len(s) and s[rest] != ';':
                    raise ParseError("text after '}' is not supported", ln)
                continue
            if s[i] == '{':
                if last is None or last.children is not None or last.parent is not stack[-1]:
                    raise ParseError("'{' without a key", ln)
                last.children = []
                last.brace_next_line = True
                last.raw = last.raw + self.newline + (('\n'.join(pending) + self.newline) if pending else '') + line
                pending = []
                last._orig = (last.key, last.value, True)
                stack.append(last)
                rest = _skip_ws(s, i + 1)
                if rest < len(s) and s[rest] != ';':
                    raise ParseError("text after '{' is not supported", ln)
                continue
            key, _, i = _read_token(s, i, ln)
            i = _skip_ws(s, i)
            value, quoted = None, False
            if i < len(s) and s[i] not in ';{}':
                value, quoted, i = _read_token(s, i, ln)
                i = _skip_ws(s, i)
            opens = False
            if i < len(s) and s[i] == '{':
                opens = True
                i = _skip_ws(s, i + 1)
            comment = None
            if i < len(s) and s[i] == ';':
                comment = s[i:]
            elif i < len(s):
                if s[i] == '}':
                    raise ParseError("'}' on the same line as a key is not supported", ln)
                raise ParseError(f'unexpected text {s[i:]!r}', ln)
            n = Node(key, value, [] if opens else None)
            n.raw, n.pre, n.indent, n.quoted, n.comment, n.line = line, pending, indent, quoted, comment, ln
            n._orig = (n.key, n.value, opens)
            pending = []
            stack[-1].append(n)
            last = n
            if opens:
                stack.append(n)
        if len(stack) != 1:
            raise ParseError(f"missing '}}' for section '{stack[-1].key}' opened on line {stack[-1].line}")
        self.root.tail = pending

    # ------------------------------------------------------------------ writing
    def _guess_indent_unit(self) -> str:
        for sec in self.root.children:
            for c in sec.children or []:
                if c.indent is not None and c.indent:
                    return c.indent
        return '    '

    def dumps(self) -> str:
        out: List[str] = []
        unit = self._guess_indent_unit()
        for c in self.root.children:
            self._emit(c, out, '', unit)
        out.extend(self.root.tail)
        nl = self.newline
        text = nl.join(out)
        if out and self.final_newline:
            text += nl
        return text

    def _emit(self, n: Node, out: List[str], indent: str, unit: str):
        out.extend(n.pre)
        ind = n.indent if n.indent is not None else indent
        if not n.dirty() and n.raw is not None:
            out.extend(n.raw.split(self.newline))
        else:
            parts = [ind + (format_value(n.key) if n.key != '#include' else '#include')]
            if n.value is not None:
                parts.append(format_value(n.value, n.quoted))
            line = ' '.join(parts)
            if n.children is not None:
                line += ' {'
            if n.comment:
                line += ' ' + n.comment
            out.append(line)
        if n.children is not None:
            child_indent = ind + unit
            # use the indentation of existing siblings when we have it
            for c in n.children:
                if c.indent is not None:
                    child_indent = c.indent
                    break
            for c in n.children:
                self._emit(c, out, child_indent, unit)
            out.extend(n.tail)
            if n.raw_close is not None and not (n.raw is None):
                out.append(n.raw_close)
            else:
                out.append(ind + '}')

    # convenience
    def section(self, name: str, create: bool = False) -> Optional[Node]:
        return self.root.block(name, create=create) if create else self.root.child(name)

    def find(self, path: str) -> Optional[Node]:
        return self.root.find(path)

    def get(self, path: str, default=None):
        return self.root.get(path, default)


def parse_int(v, default=None):
    """dabmux hexparse(): accepts 0x.. hex or decimal."""
    if v is None:
        return default
    v = str(v).strip()
    try:
        if v.lower().startswith('0x'):
            return int(v, 16)
        return int(v)
    except ValueError:
        return default


def parse_bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


_URI_PORT = re.compile(r'^(?P<scheme>[a-z+]+)://(?P<host>\[[^\]]*\]|[^:/]*)(?::(?P<port>\d+))?(?P<rest>.*)$', re.I)


def split_uri(uri: str):
    m = _URI_PORT.match(uri or '')
    if not m:
        return None
    d = m.groupdict()
    d['port'] = int(d['port']) if d['port'] else None
    return d


def with_port(uri: str, port: int) -> str:
    d = split_uri(uri)
    if not d:
        return uri
    return f"{d['scheme']}://{d['host']}:{port}{d['rest']}"
