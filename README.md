# MPBNL Multiplex WebFrontend (ODR Mux Manager)

A self-hosted web UI to **monitor and manage an ODR-DabMux multiplex** and the
`odr-audioenc` / `odr-padenc` encoders that supervisor runs for it. It installs as the
`odr-mux-manager` service and command, next to (and separate from) the MPBNL SPI WebFrontend.

Point it at your mux folder (e.g. `/home/ryan/dab` with `conf.mux`, `supervisor/`, `mot/`) and
it imports what is there, without changing anything until you click **Apply**.

## What it does

- **On air (main page)**:
  - live L/R levels per station (from the odr-dabmux management port, so no extra sockets)
  - input buffer state, and encoder up/down (supervisord)
  - DLS and slides **decoded from the mux's own EDI output**, i.e. what is really broadcast
  - the CU bar, with unapplied changes shown striped
  - silence, dead-encoder and no-data alerts; stations with problems sort to the top
- **Stations**:
  - edit service, subchannel/protection (live CU), components and secondary components
  - encoders: GStreamer/VLC/ALSA/JACK/file input, picked from what your odr-audioenc build supports
  - codec: DAB+ AAC/HE/HEv2 or **MP2 with psy model and channel mode**
  - PAD, DLS and slide settings
- **Local ↔ external feed**:
  - stations fed by EDI/ZMQ from another machine get no encoders
  - switching a station to external parks its encoders; switching back restores them exactly
- **Remove / reorder with renumbering**:
  - by default, numbers stay as they are and only the order changes
  - optional "close gaps": remove station 9 and 10→9, 11→10 …; service/subchannel/component names,
    subchannel id, port, `mot/P##`, stats and DLS paths and `# P##` comments all shift
  - an **impact report** lists everything outside the manager that has to be repointed
  - folders are renamed in two steps; external feeds keep their port
- **Linking & FI**, **other ensembles**, **announcement clusters**, and per-service announcement support.
- **Data services**:
  - SPI, **Journaline**, TPEG, Broadcast Website, packet slideshow, or custom
  - each one points at a generator's `.dat` file and sets packet address, data groups and user-app signalling
- **DMB radio/TV (T-DMB)**:
  - any ffmpeg input: files, HLS/RTMP/SRT/HTTP streams, capture devices (v4l2, DeckLink, ALSA…)
    or test sources, with an input format and extra input options
  - ffmpeg encodes H.264 Baseline + AAC; the manager packs it as T-DMB (MPEG-4 Systems: IOD in the
    PMT, OD + BIFS scene in SL sections, SL-packetized PES), adds Reed-Solomon (204,188) + the
    interleaver (byte-exact with odr-dabmux's original DMB code), and feeds a non-blocking FIFO at
    exactly the subchannel rate (null-packet stuffing)
  - the audio/video split is worked out from the subchannel size after the packaging overhead,
    and a subchannel that's too small is refused
  - checked by decoding the stream back out of odr-dabmux's output with GPAC
- **Checks**:
  - over capacity, invalid UEP/EEP combinations, short labels odr-dabmux rejects, garbled labels (auto-fix)
  - codec or bitrate mismatch between encoder and subchannel
  - port clashes, log names that don't match the program, linkage pointing at itself, …
- **Apply**:
  - shows a diff (secrets masked) and takes a backup
  - writes files atomically, then `supervisorctl reread/update` (only changed encoders restart)
    and restarts odr-dabmux when the mux changed
  - **one-click rollback**, folder moves included
- **Users**:
  - admin, editor, viewer (read-only), and **station monitor**: confidence monitoring of assigned
    stations only (levels, DLS, slides, encoder state), filtered server-side
- **Network**:
  - listens on `127.0.0.1` or `0.0.0.0`; the installer asks, admins can change it later
  - a change must be confirmed on the new address within 60 s, or it reverts

## Install

```bash
git clone https://github.com/ryanginn/ODR-Mux-Manager.git
cd ODR-Mux-Manager
sudo ./install.sh
```

The installer asks for:
- the listen address (`127.0.0.1` / `0.0.0.0`)
- the port (default **8092**; the SPI generator uses 8090)
- the user to run as, which must be able to edit your mux folder

It prints a first-run link with a setup token (`sudo odr-mux-manager setup-token`).

Supervisor access: the service user must be able to use `/var/run/supervisor.sock`. Set
`chmod=0770` and `chown=root:<group>` under `[unix_http_server]` in `supervisord.conf`.

## Ports it uses or reads

| What | Default |
| :-- | :-- |
| Web UI | 8092 |
| odr-dabmux management (read) | `general.managementport` from your mux (12720) |
| On-air decoder (read) | the mux's EDI TCP output (`listenport`, e.g. 9201) |
| supervisord | its unix socket |

## Development

```bash
pip install flask cheroot pyzmq pytest
python3 -m pytest tests
python3 -m odr_mux check /path/to/dab        # station list + checks on the command line
```

The tests cover:
- byte-identical round trips of real configs
- renumbering, and apply/rollback on a real folder
- the DMB coder against odr-dabmux's reference code, and the T-DMB structure (plus a GPAC decode when GPAC is installed)
- DLS and slide decoding from a capture of real odr-dabmux output
- the API's role scoping and secret handling
