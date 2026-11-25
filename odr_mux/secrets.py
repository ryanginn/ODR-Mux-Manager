"""Masking credentials that live inside stream URLs (``?skey=...``, ``user:pass@host``)."""
from __future__ import annotations

import re

MASK = '•••'
_KEYS = r'(?:s?key|token|secret|password|passwd|pass|pwd|auth|apikey|api_key|access_token|sig|signature)'
_QUERY = re.compile(r'(?P<pre>[?&;]' + _KEYS + r'=)(?P<val>[^&#\s]+)', re.I)
_USERINFO = re.compile(r'(?P<pre>[a-z][a-z0-9+.\-]*://[^/@\s:]+:)(?P<val>[^@/\s]+)(?=@)', re.I)


def has_secret(s: str) -> bool:
    return bool(s) and bool(_QUERY.search(s) or _USERINFO.search(s))


def mask(s: str) -> str:
    if not s:
        return s
    s = _QUERY.sub(lambda m: m.group('pre') + MASK, s)
    s = _USERINFO.sub(lambda m: m.group('pre') + MASK, s)
    return s


def unmask(new: str, old: str) -> str:
    """When a masked value comes back from the UI unchanged, restore the real secret."""
    if not new or MASK not in new or not old:
        return new
    if mask(old) == new:
        return old
    # Replace each masked slot by the old secret in the same position
    olds = [m.group('val') for m in _QUERY.finditer(old)] + [m.group('val') for m in _USERINFO.finditer(old)]
    it = iter(olds)
    return re.sub(re.escape(MASK), lambda _m: next(it, MASK), new)


def mask_text(text: str) -> str:
    """Mask every secret in a blob of text (diffs, logs)."""
    return mask(text)
