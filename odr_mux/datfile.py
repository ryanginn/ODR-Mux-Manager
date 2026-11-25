"""Inspect a packet-mode .dat file as written by an SPI / Journaline / TPEG generator.

odr-dabmux (inputproto file, type packet) sends the file's packets unchanged, including their packet
address. A receiver only decodes the packets whose address matches FIG 0/3, i.e. the component's
`address` - so a generator writing a different address gives "Waiting for the page..." forever.
"""
from __future__ import annotations

import os
import time
from collections import Counter

PACKET_SIZES = {0: 24, 1: 48, 2: 72, 3: 96}


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc ^ 0xFFFF


def parse_packets(data: bytes):
    """Yield (address, size, useful_len, first, last, crc_ok) for consecutive packets."""
    i = 0
    while i + 24 <= len(data):
        size = PACKET_SIZES[data[i] >> 6]
        if i + size > len(data):
            break
        pkt = data[i:i + size]
        first_last = (pkt[0] >> 2) & 3
        address = ((pkt[0] & 3) << 8) | pkt[1]
        useful = pkt[2] & 0x7F
        crc_ok = _crc16(pkt[:-2]) == ((pkt[-2] << 8) | pkt[-1])
        yield address, size, useful, bool(first_last & 2), bool(first_last & 1), crc_ok
        i += size


def inspect(path: str, expected_address=None, limit: int = 512 * 1024) -> dict:
    out = {'path': path, 'exists': os.path.exists(path)}
    if not out['exists']:
        out['problems'] = [f'{path} does not exist (yet). Is the generator running and writing there?']
        return out
    st = os.stat(path)
    out.update(size=st.st_size, mtime=st.st_mtime, age=time.time() - st.st_mtime)
    with open(path, 'rb') as f:
        data = f.read(limit)
    addrs, sizes = Counter(), Counter()
    total = bad = padding = groups = 0
    for address, size, useful, first, last, ok in parse_packets(data):
        total += 1
        sizes[size] += 1
        if not ok:
            bad += 1
            continue
        if address == 0 or useful == 0:
            padding += 1
            continue
        addrs[address] += 1
        if first:
            groups += 1
    out.update(packets=total, crc_errors=bad, padding=padding, data_groups=groups,
               addresses={f'0x{a:X}': n for a, n in addrs.most_common()},
               packet_sizes={str(k): v for k, v in sorted(sizes.items())})
    problems = []
    if st.st_size == 0:
        problems.append('The file is empty: the generator has not written anything yet.')
    elif total == 0 or bad > total * 0.5:
        problems.append('The file does not look like packet-mode data (most packet CRCs are wrong). '
                        'Is this the generator\'s DAB packet output, and is the subchannel type right?')
    elif not addrs:
        problems.append('The file only contains padding packets: no data.')
    exp = None
    if expected_address is not None:
        try:
            exp = int(str(expected_address), 0)
        except ValueError:
            exp = None
    if exp is not None and addrs and exp not in addrs:
        found = ', '.join(out['addresses'])
        problems.append(f'The generator writes packet address {found}, but the service is configured for '
                        f'0x{exp:X}. Receivers only decode the configured address, so set the packet address '
                        f'to {next(iter(out["addresses"]))} here (or change it in the generator).')
    if out.get('age', 0) > 3600 and st.st_size:
        problems.append(f'The file was last written {int(out["age"] // 60)} minutes ago; '
                        f'check that the generator is still running.')
    out['problems'] = problems
    out['ok'] = not problems
    return out
