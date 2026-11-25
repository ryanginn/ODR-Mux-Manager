"""Capacity Unit (CU) calculation, matching odr-dabmux (MuxElements.cpp / DabMultiplexer.cpp).

Mode I: 864 CU per CIF. Tables are from ETSI EN 300 401 (Table 6 for UEP, clause 6.2.1 for EEP).
"""
from __future__ import annotations

TOTAL_CU = 864

# (bitrate, level 1..5) -> CU, from EN 300 401 Table 6 (dabmux BitRateTable/ProtectionLevelTable/
# Sub_Channel_SizeTable; dabmux stores level-1, the table lists levels 5..1 per bitrate).
_UEP_SIZES = [16, 21, 24, 29, 35, 24, 29, 35, 42, 52, 29, 35, 42, 52, 32, 42,
              48, 58, 70, 40, 52, 58, 70, 84, 48, 58, 70, 84, 104, 58, 70, 84,
              104, 64, 84, 96, 116, 140, 80, 104, 116, 140, 168, 96, 116, 140, 168, 208,
              116, 140, 168, 208, 232, 128, 168, 192, 232, 280, 160, 208, 280, 192, 280, 416]
_UEP_LEVELS = [4, 3, 2, 1, 0, 4, 3, 2, 1, 0, 4, 3, 2, 1, 4, 3, 2, 1, 0, 4, 3, 2, 1, 0,
               4, 3, 2, 1, 0, 4, 3, 2, 1, 4, 3, 2, 1, 0, 4, 3, 2, 1, 0, 4, 3, 2, 1, 0,
               4, 3, 2, 1, 0, 4, 3, 2, 1, 0, 4, 3, 1, 4, 2, 0]
_UEP_RATES = [32] * 5 + [48] * 5 + [56] * 4 + [64] * 5 + [80] * 5 + [96] * 5 + [112] * 4 + \
             [128] * 5 + [160] * 5 + [192] * 5 + [224] * 5 + [256] * 5 + [320] * 3 + [384] * 3

UEP_TABLE = {(r, l + 1): s for r, l, s in zip(_UEP_RATES, _UEP_LEVELS, _UEP_SIZES)}
UEP_BITRATES = sorted(set(_UEP_RATES))

# MPEG-1/2 Layer II bitrates allowed by odr-audioenc --dab
MP2_BITRATES_48K = [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384]
MP2_BITRATES_24K = [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]

_EEP_A = {1: (12, 8), 2: (8, 8), 3: (6, 8), 4: (4, 8)}     # CU = bitrate * num / den
_EEP_B = {1: (27, 32), 2: (21, 32), 3: (18, 32), 4: (15, 32)}


def uep_levels_for(bitrate: int):
    return sorted(l for (r, l) in UEP_TABLE if r == bitrate)


def protection_form(subch_type: str, profile: str | None) -> str:
    """Return 'UEP', 'EEP_A' or 'EEP_B' as dabmux would pick it before fallback."""
    p = (profile or '').upper()
    if p in ('EEP_A', 'EEP_B', 'UEP'):
        return p
    return 'UEP' if subch_type == 'audio' else 'EEP_A'


def effective_protection(subch_type: str, profile: str | None, bitrate: int, level: int):
    """(form, level) after dabmux' UEP->EEP fallback for bitrates without a UEP entry."""
    form = protection_form(subch_type, profile)
    if form == 'UEP' and (bitrate, level) not in UEP_TABLE:
        # dabmux keeps the level and profile defaults (EEP_A) when it falls back
        return 'EEP_A', level, True
    return form, level, False


def cu_for(subch_type: str, bitrate: int, profile: str | None, level: int) -> int:
    try:
        bitrate = int(bitrate)
        level = int(level)
    except (TypeError, ValueError):
        return 0
    form, level, _ = effective_protection(subch_type, profile, bitrate, level)
    if form == 'UEP':
        return UEP_TABLE.get((bitrate, level), 0)
    table = _EEP_A if form == 'EEP_A' else _EEP_B
    if level not in table:
        return 0
    num, den = table[level]
    return (bitrate * num) // den


def protection_label(subch_type, profile, bitrate, level) -> str:
    try:
        form, level, fb = effective_protection(subch_type, profile, int(bitrate), int(level))
    except (TypeError, ValueError):
        return '?'
    if form == 'UEP':
        return f'UEP-{level}'
    return f"EEP-{level}{form[-1]}"


def validate_protection(subch_type, profile, bitrate, level):
    """Return a list of (severity, message) problems."""
    out = []
    try:
        bitrate = int(bitrate)
        level = int(level)
    except (TypeError, ValueError):
        return [('error', 'bitrate and protection must be numbers')]
    if bitrate % 8:
        out.append(('error', f'bitrate {bitrate} is not a multiple of 8'))
    form = protection_form(subch_type, profile)
    if form == 'UEP':
        if not 1 <= level <= 5:
            out.append(('error', 'UEP protection level must be 1..5'))
        elif (bitrate, level) not in UEP_TABLE:
            ok = uep_levels_for(bitrate)
            out.append(('warning', f'UEP-{level} does not exist at {bitrate} kbps; odr-dabmux will silently fall back '
                        f'to EEP-{level}A' + (f' (UEP levels for {bitrate} kbps: {ok})' if ok else '')))
        if subch_type not in ('audio',):
            out.append(('warning', 'UEP is only defined for MPEG audio (type audio)'))
    else:
        if not 1 <= level <= 4:
            out.append(('error', 'EEP protection level must be 1..4'))
        if form == 'EEP_B' and bitrate % 32:
            out.append(('error', f'EEP-B needs a bitrate that is a multiple of 32 kbps (got {bitrate})'))
    if subch_type == 'dabplus' and bitrate % 8:
        out.append(('error', 'DAB+ bitrate must be a multiple of 8'))
    return out
