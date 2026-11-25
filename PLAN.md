# ODR Mux Manager — Plan

A self-hosted web UI for managing an ODR-DabMux multiplex and its supervisor-run
encoders. It is a separate app from the MPBNL SPI WebFrontend (ODR-SPI-Generator) but
uses the same stack and look.

## Stack

- Python ≥ 3.9, Flask + cheroot, plain-JS single-page app.
- Same design tokens and light/dark themes as the SPI generator. The logo spot stays blank
  for now.
- Runs as the systemd service `odr-mux-manager`, installed with `install.sh` /
  `uninstall.sh` and updatable from Settings.
- Its own config, data and state, kept apart from the SPI generator:
  - `/etc/odr-mux-manager/`
  - `/var/lib/odr-mux-manager/`

## Network / ports

| What | Default | Notes |
| :-- | :-- | :-- |
| Web UI | `8092` | Chosen to avoid the SPI generator (8090), the dabmux inputs (9001–9026, 2492), EDI (9201), ZMQ (18081), and the management/telnet/zmq ports 12720–12722 |
| Bind address | `127.0.0.1` or `0.0.0.0` | Asked by the installer; an admin can change both under Settings → Network |

- When the bind address or port is changed in Settings, the service restarts on the new
  address.
- After that restart the new address must be confirmed within 60 s, or the old one is
  restored, so a mistake can't lock you out.
- The manager only *connects* to dabmux (management port 12720, telnet 12721), to
  supervisor (its unix socket), and to the audioenc `--stats` sockets. It never listens on
  any of those ports.
- On startup it checks for port clashes and warns about them. For example, the supervisor
  `inet_http_server` default of 9001 would clash with sub-01's input.

## Users & roles

| Role | Can do |
| :-- | :-- |
| **Admin** | Everything: users, network settings, Apply, rollback |
| **Editor** | Edit the mux and encoders and Apply; no user or network admin |
| **Viewer** | Read-only view of every page: monitor, config, CU, history |
| **Station monitor** | Confidence monitoring of **assigned stations only**: their audio levels, DLS, SLS, and encoder up/down. No config, and nothing from other stations is visible (filtered server-side) |

- Session cookies, Argon2/PBKDF2 password hashes, login rate limiting, an audit log, and a
  first-run setup token. Same model as the SPI generator.
- Station assignments follow a station through renumbering, because they are keyed on an
  internal ID and not on `P##`.

## Model

1. **Import.** Point the app at the mux folder (e.g. `/home/ryan/dab`) and it finds:
   - `conf.mux` (or another `.mux` you pick)
   - `supervisor/*.conf`
   - `mot/P##/`
   - the SPI `.dat`
2. **Parse.** The boost INFO config is read with comments and tabs kept, then turned into
   one internal model of the mux.
3. **Link encoders to subchannels by port.** `-e tcp://127.0.0.1:90NN` is matched to
   `inputuri tcp://0.0.0.0:90NN`, never by `P##` number, because the existing mux doesn't
   line up (P04 → port 9003 → sub-03).
4. **Fix labels.** Garbled labels like `RaidiÃ³` are repaired on import.
5. **Apply:**
   1. diff of every file
   2. backup snapshot
   3. write the files
   4. `supervisorctl reread/update`
   5. restart dabmux, or update it live over remote control where possible (labels)
   6. one-click rollback

## Pages

1. **Monitor (main page)**
   - Top strip: CU bar (used / pending striped / free, out of 864), ensemble, uptime, and
     dabmux/supervisor status.
   - A card per station with:
     - live L/R meters from the stats sockets, plus a silence alert
     - current DLS
     - current slide and a countdown to the next one
     - bitrate, protection and CU
     - encoder and buffer status
     - restart buttons (Editor and above)
   - Cards with a problem sort to the top. Filters: All / Issues / Audio / Data, plus
     search.
   - Click a card for a detail view: bigger meters, DLS history, every slide, and the log
     tail.
2. **Services / Subchannels / Components.** Live CU cost, EEP-A/B and UEP rules,
   secondary components, PTY, language, user apps.
3. **Station list with remove/reorder.**
   - Removing or reordering renumbers:
     - `srv-`/`sub-`/`comp-` names
     - ports
     - `mot/P##`
     - supervisor program names
     - stats and log paths
     - linking `keyservice` references
   - Before anything changes, an **impact report** lists each affected station and what
     must be repointed outside the manager: external scripts writing DLS, remote `-o`
     outputs, and stats readers.
   - Folder renames go through temporary names in two steps.
4. **Encoders.** odr-padenc and odr-audioenc settings, kept as a pair per station.
5. **Linking & frequency information.** Visual editors for linkage sets and FI.
6. **Announcements.** Ensemble clusters plus on/off switches per service.
7. **Data services.** SPI, Journaline and TPEG as packet or enhanced-packet subchannels
   with a `.dat` file input. Bitrate, packet size and address are checked against each
   other.
   - The current odr-dabmux `userapp` names are only `slideshow`, `spi`, `website` and
     `journaline`.
   - TPEG (and DMB) therefore need the older single-app `figtype` key. The editor writes
     whichever form is needed.
8. **DMB (experimental, last phase).** See the DMB section below.
9. **Settings, users, backups/history, audit log.**

## DAB (MP2) and DAB+ side by side

A mux can mix MP2 and DAB+ stations, so each station has a **codec** setting:

| Codec | Subchannel | Encoder flags |
| :-- | :-- | :-- |
| DAB+ AAC-LC | `type dabplus` | `--aaclc` (or no profile flag) |
| DAB+ HE-AAC v1 | `type dabplus` | `--sbr` |
| DAB+ HE-AAC v2 | `type dabplus` | `--ps` |
| **DAB (MP2)** | `type audio` | `--dab`, `--dabmode`, `--dabpsy` |

Encoder settings by codec:

- **MP2 options:**
  - **Channel mode** (`--dabmode`): stereo `s`, joint stereo `j`, dual mono `d`, mono `m`.
    The default is `j` for stereo and `m` for mono.
  - **Psychoacoustic model** (`--dabpsy`): 0, 1, 2 or 3. The encoder's default is 1;
    your stations use 2.
  - **Sample rate:** 48 kHz, or 24 kHz for low-sampling-frequency mode (LSF).
- **DAB+ options:** afterburner on/off, bandwidth, and sample rate 32 or 48 kHz.
- **Shown for every codec:** PAD length, with a hint about how much space it leaves for the
  slideshow, plus silence timeout, drift compensation, ICY text, and the stats socket.

Protection and CU:

- **MP2 uses UEP** by default: `protection-profile UEP`, levels 1–5. The CU count comes
  from the UEP table (ETSI EN 300 401, Table 6) for each bitrate and level. Some
  bitrate/level pairs don't exist, and the editor greys those out.
- MP2 can also be set to EEP-A/B.
- On the monitor and CU bar, each station shows a codec badge (`MP2` / `AAC` / `HE` /
  `HEv2`) next to its bitrate.

Example: MP2 at 128 kbps with UEP level 3 = 96 CU, versus 60 CU for DAB+ at 128 kbps with
EEP-4B. The CU bar shows what switching a station's codec would free up or cost.

## Secrets in stream URLs

Some source URLs carry credentials, such as a stream key in the query string:

- These parts are **masked in the UI**, except to admins who click to reveal.
- They are never sent to Viewer or Station-monitor users.
- They are left out of the audit log and the diff preview (shown as `•••`).
- Backups keep them, so backup files are only readable by the service user.

## DMB

What current ODR-DabMux does (checked against the latest source, June 2026):

- It still accepts `type dmb` subchannels.
- It treats them as **raw stream-mode data** (input from `udp`, `file` or `fifo`).
- The old Reed-Solomon (204,188) + outer interleaver stage is "unported": dabmux logs a
  warning and passes the bytes through unchanged.

So "is DMB supported?" isn't a simple yes/no.

- **The manager does the DMB outer coding itself** (TS → RS(204,188) → interleaver), so
  it works with a stock odr-dabmux.
- **The DMB setup page tells you which situation you're in:**
  - dabmux version found
  - whether `dmb` is accepted
  - whether the outer coding is handled by dabmux or by the manager
- **If anything is missing, the page shows step-by-step instructions:** build or upgrade
  odr-dabmux, install the ffmpeg codecs, and add the supervisor programs.

### DMB encoders (DMB Radio and DMB TV)

These are created and managed like the existing encoder pairs: supervisor programs,
editable in the UI, and shown on the monitor with levels and status.

1. **Source → ffmpeg:**
   - DMB TV: H.264 Baseline video (QVGA/CIF) plus HE-AAC v2 audio
   - DMB Radio: audio only
2. **`odr-mux-manager dmb-mux` (new):** builds the T-DMB MPEG-2 TS to ETSI TS 102 428, with
   the MPEG-4 SL packetisation, IOD and OD/BIFS that ffmpeg can't produce. Optionally adds
   slideshow / DLS-style text.
3. **Outer coding:** RS(204,188) + interleaver, then UDP to dabmux (`type dmb`,
   `inputproto udp`).
4. **Signalling:** the component gets DSCTy MPEG-2 TS and user app type DMB.

Capacity: DMB TV needs roughly 300–550 kbps (≈ 200–400 CU), and DMB Radio roughly 96–192
kbps. The current mux has 1 CU free, so the CU bar and checker will say exactly what would
have to give.

Testing risk: few receivers outside Korea decode T-DMB. The first milestone is a stream
that a software decoder accepts, using a test receiver that we'll pick when we get there.

## Checker (examples from the current mux)

- 863/864 CU used: warn when the free capacity drops below a threshold.
- Log file name doesn't match the program (`s21punk` → `r2xmas.log`, `variant` →
  `test.log`).
- An option is stuck on the wrong line (`--silence=60` on the `--gst-uri` line).
- A DAB linkage entry points at the set's own key service (`mpb2-dab-5a` → 0x2492).
- An EEP-B bitrate that isn't a multiple of 32; duplicate ports, SIds or subchannel IDs.
- Codec mismatch between encoder and subchannel: `--dab` with `type dabplus`, or a DAB+
  encoder with `type audio`.
- Bitrate mismatch between the encoder and the subchannel.
- MP2 bitrate/UEP level pair that isn't valid.
- `--dabpsy` / `--dabmode` set on a DAB+ encoder, or `--sbr` / `--ps` on an MP2 one.

## Build order

1. Config parser/writer that reproduces the files exactly on a round trip (tested against
   the real files), import, and the CU calculator.
2. **Monitor main page:** reading levels, DLS and SLS from files; auth and roles; installer
   with bind address and port.
3. Service, subchannel, component and encoder editors, plus the checker and Apply/rollback.
4. Remove/reorder with renumbering, MOT moves and the impact report.
5. Linking, FI, announcements, user apps.
6. Data services (SPI, Journaline, TPEG).
7. On-air decoding from dabmux's EDI/ZMQ output, to show what is actually transmitted.
8. DMB: support check and instructions page, then the outer coder, the DMB Radio encoder, and the DMB TV encoder.

## Status (first build)

Steps 1–8 are built and tested. 30 automated tests cover them, and they were also run live
against real supervisord, odr-dabmux v5.5.1, odr-audioenc v3.6.0 and odr-padenc built from source.

| Step | Status |
| :-- | :-- |
| 1. Lossless config read/write, import, CU | ✅ byte-identical round trip of both sample setups |
| 2. Monitor main page, auth/roles, installer | ✅ levels from the dabmux management port, station-monitor scoping |
| 3. Editors, checker, Apply/rollback | ✅ checker matches dabmux on short labels; apply restarts only changed programs |
| 4. Remove/reorder + MOT moves + impact report | ✅ done live: P02→P01 with folder rename and encoder on the new port |
| 5. Linking, FI, announcements, user apps | ✅ |
| 6. Data services (SPI, Journaline, TPEG, …) | ✅ |
| 7. On-air decoding (EDI) | ✅ DLS + MOT slides for DAB+ and MP2, from real mux output |
| 8. DMB | ✅ T-DMB (IOD/OD/BIFS/SL) from any ffmpeg input; recovered from the mux output and decoded with GPAC |

Findings along the way:

- **odr-dabmux UDP input bug.** For `type data` / `dmb`, `Udp::readFrame()` never removes consumed
  bytes, so it repeats the first frame forever. DMB therefore uses a non-blocking FIFO.
  Worth reporting upstream; it's a one-line fix.
- **X-PAD continuation length.** An X-PAD without a CI list continues the previous application
  with the length of the whole previous X-PAD (CI bytes included).

## Decisions (from review)

- Removing or reordering stations **keeps the numbers by default**; closing the gap is opt-in.
- Audio levels keep coming from the odr-dabmux management port (stats sockets stay optional).
- Full T-DMB packaging is built, with ffmpeg as the input for video and audio.
- The odr-dabmux UDP bug won't be reported upstream; the FIFO workaround stays.

## Open questions

- HE-AAC for DMB needs an ffmpeg built with libfdk_aac. Should the installer offer to build one?
- T-DMB receiver testing on real hardware (car radios, phones with T-DMB) still has to be done.
