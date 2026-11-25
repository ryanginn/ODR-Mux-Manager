"""Detect installed ODR tools and what they were built with (VLC / GStreamer / ALSA / JACK, DMB)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from typing import Optional

_cache = {'ts': 0, 'data': None}

SEARCH = ['/usr/local/bin', '/usr/bin', '/opt/odr/bin']


def find_tool(name: str, overrides: Optional[dict] = None) -> Optional[str]:
    if overrides and overrides.get(name):
        return overrides[name] if os.path.exists(overrides[name]) else None
    p = shutil.which(name)
    if p:
        return p
    for d in SEARCH:
        c = os.path.join(d, name)
        if os.access(c, os.X_OK):
            return c
    return None


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or '') + (r.stderr or '')
    except (OSError, subprocess.TimeoutExpired):
        return ''


def audioenc_features(path: str) -> dict:
    out = _run([path, '-h'])
    ver = _run([path, '--version']).strip().splitlines()
    feats = {
        'version': ver[0] if ver else None,
        'gstreamer': 'GStreamer input was disabled' not in out and '--gst-uri' in out,
        'vlc': 'VLC input was disabled' not in out and '--vlc-uri' in out,
        'alsa': 'Alsa input was disabled' not in out and '--device' in out,
        'jack': 'JACK input was disabled' not in out and '--jack' in out,
        'file': True,
        'mp2': '--dab' in out,
    }
    return feats


def dabmux_features(path: str) -> dict:
    ver = _run([path, '--version'])
    help_ = _run([path, '-h'])
    m = re.search(r'(v?\d+\.\d+\.\d+[^\s]*)', ver or help_)
    return {
        'version': m.group(1) if m else (ver.strip().splitlines() or [None])[0],
        # Every current odr-dabmux accepts `type dmb`, but since the input refactor it
        # passes the data through RAW (the old RS(204,188)+interleaver input is unported).
        'dmb_type': True,
        'dmb_outer_coding': False,
    }


def detect(cfg: Optional[dict] = None, max_age=300) -> dict:
    if _cache['data'] is not None and time.time() - _cache['ts'] < max_age:
        return _cache['data']
    ov = (cfg or {}).get('tool_paths') or {}
    tools = {}
    for name in ('odr-audioenc', 'odr-padenc', 'odr-dabmux', 'odr-dabmod', 'ffmpeg', 'supervisorctl', 'gpac'):
        tools[name] = find_tool(name, ov)
    data = {'tools': tools}
    data['audioenc'] = audioenc_features(tools['odr-audioenc']) if tools['odr-audioenc'] else None
    data['dabmux'] = dabmux_features(tools['odr-dabmux']) if tools['odr-dabmux'] else None
    if tools['ffmpeg']:
        enc = _run([tools['ffmpeg'], '-hide_banner', '-encoders'], timeout=10)
        data['ffmpeg'] = {
            'h264': any(x in enc for x in ('libx264', 'h264_v4l2m2m', 'h264_vaapi', 'h264_nvenc', 'h264_omx')),
            'libx264': 'libx264' in enc,
            'aac': ' aac ' in enc or 'libfdk_aac' in enc,
            'he_aac': 'libfdk_aac' in enc,
        }
    else:
        data['ffmpeg'] = None
    inputs = []
    a = data['audioenc'] or {}
    for k in ('gstreamer', 'vlc', 'alsa', 'jack', 'file'):
        if a.get(k):
            inputs.append(k)
    data['inputs'] = inputs
    _cache.update(ts=time.time(), data=data)
    return data


def invalidate():
    _cache['data'] = None
