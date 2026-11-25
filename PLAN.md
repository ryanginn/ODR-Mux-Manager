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
8. **DMB.** Subchannel type `dmb`, shown only if the installed odr-dabmux supports it.
9. **Settings, users, backups/history, audit log.**

## Checker (examples from the current mux)

- 863/864 CU used: warn when the free capacity drops below a threshold.
- Log file name doesn't match the program (`s21punk` → `r2xmas.log`, `variant` →
  `test.log`).
- An option is stuck on the wrong line (`--silence=60` on the `--gst-uri` line).
- A DAB linkage entry points at the set's own key service (`mpb2-dab-5a` → 0x2492).
- An EEP-B bitrate that isn't a multiple of 32; duplicate ports, SIds or subchannel IDs.

## Build order

1. Config parser/writer that reproduces the files exactly on a round trip (tested against
   the real files), import, and the CU calculator.
2. **Monitor main page:** reading levels, DLS and SLS from files; auth and roles; installer
   with bind address and port.
3. Service, subchannel, component and encoder editors, plus the checker and Apply/rollback.
4. Remove/reorder with renumbering, MOT moves and the impact report.
5. Linking, FI, announcements, user apps.
6. Data services and DMB.
7. On-air decoding from dabmux's EDI/ZMQ output, to show what is actually transmitted.

## Open questions

- Should removing a station close the number gap (10→9, port 9010→9009), or only change the
  display order? Assumed: close the gap, with the impact report.
- Is anything else already listening on the `/var/tmp/P##.stats` sockets?
