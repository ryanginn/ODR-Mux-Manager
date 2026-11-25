"""Label helpers: mojibake repair and DAB label rules (as enforced by odr-dabmux)."""
from __future__ import annotations

import re

# Characters of the EBU Latin based repertoire (ETSI TS 101 756 Annex C) that odr-dabmux can
# convert. Anything outside is replaced by the converter.
_EBU_EXTRA = set('ÁÀÉÈÍÌÓÒÚÙÑÇŞßİĲĳáàéèíìóòúùñçşğıĳªαº¹²³±İńűťŤŜŝÂÄÊËÎÏÔÖÛÜřčšžđŀâäêëîïôöûüňšžďľĀĆŊŘĜŦĐĪĶŞŬŪĂÅÆŒŷÝÕØÞŊŔĆŚŹťðãåæœŵýõøþŋŕćśźŧ'
                 'ÃĎĚĞÕĢĪĬĮĴĶĹĽŁŃŇŐŒŖŘŠŢŤŨŰŲŴŶŸŹŻŽčęğģīĭįĵķĺľłńňőœŗřšţťũűųŵŷÿźżžĉċĕėęěĝğġĥħĩīĭįıĵĸķĺļľŀłņňŉőœŗşťŧũūŭůųŵŷżž€£$¥¢¤§«»°×÷µ¶·¿¡')


def looks_mojibake(s: str) -> bool:
    return bool(s) and bool(re.search(r'[ÃÂÅÄ][\u0080-¿]', s))


def repair_mojibake(s: str) -> str:
    """Undo UTF-8 text that was decoded as Latin-1/CP1252 one or more times ("RaidiÃ³" -> "Raidió")."""
    if not s:
        return s
    cur = s
    for _ in range(3):
        if not looks_mojibake(cur):
            break
        fixed = None
        for enc in ('latin-1', 'cp1252'):
            try:
                fixed = cur.encode(enc).decode('utf-8')
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        if fixed is None or fixed == cur:
            break
        cur = fixed
    return cur


def ebu_unsupported(s: str):
    return sorted({c for c in s if not (32 <= ord(c) < 127) and c not in _EBU_EXTRA})


def short_label_flag(label: str, short: str):
    """Mirror of DabLabel::setFIG1ShortLabel. Returns (ok, message)."""
    if not short:
        return True, ''
    i = 0
    for ch in label:
        if i < len(short) and short[i] == ch:
            i += 1
    if i < len(short):
        return False, f'"{short}" is not made of characters of "{label}" in order'
    if len(short) > 8:
        return False, 'short label is longer than 8 characters'
    return True, ''


def check_label(label: str, short: str | None, what: str):
    """Return [(severity, message)]."""
    out = []
    if label is None:
        return out
    if looks_mojibake(label) or (short and looks_mojibake(short)):
        out.append(('warning', f'{what}: label looks garbled ("{label}"); suggested "{repair_mojibake(label)}"'))
    if len(label) > 16:
        out.append(('error', f'{what}: label "{label}" is {len(label)} characters (max 16)'))
    bad = [] if looks_mojibake(label) else ebu_unsupported(label + (short or ''))
    if bad:
        out.append(('warning', f'{what}: characters {"".join(bad)} cannot be sent in the EBU Latin charset'))
    if short is not None:
        ok, msg = short_label_flag(label, short)
        if not ok:
            out.append(('error', f'{what}: short label {msg} (odr-dabmux will refuse to start)'))
    return out


def suggest_short_label(label: str) -> str:
    """Pick up to 8 characters of the label (in order) that read well."""
    if len(label) <= 8:
        return label
    words = label.split()
    cand = ''.join(w for w in words)[:8]
    if len(cand) <= 8 and short_label_flag(label, cand)[0]:
        return cand
    return label[:8]
