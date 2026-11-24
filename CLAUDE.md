# CLAUDE.md — aveo-av318s-re

Reverse engineering of the **Aveo AV318S** USB camera controller (`1871:0f01`, UVC 1.00) and a
DIY **cosmic ray detector** built from it. Read `README.md` and `docs/` first — they hold all
findings so far. Talk to the user in **Turkish**, keep answers short and actionable.

## Setup

- The camera is plugged into a **Raspberry Pi 5** (hub 3, port 2), reachable over **Tailscale SSH**
  as user `pi` (ask the user for the host name / IP if `ssh pi@raspberrypi` does not resolve).
- Working dir on the Pi: `~/kozmikDeney/` (scripts, `olaylar/`, `olaylar.csv`).
- The cosmic ray detector runs in **tmux** session `kozmik` (`python3 kozmik.py`). Stop it
  before any test that changes camera settings or opens `/dev/video0`; restart it afterwards.
- Windows driver analysed in Ghidra on this Mac (`dvitdcnt.sys` v2.9.9.5, `CamIntfc.ax`);
  the driver files are NOT in the repo (copyright) — see README for where to get them.
- Pyusb on the Pi: vendor requests use `bmRequestType 0xC2` (IN) / `0x42` (OUT); no need to
  detach `uvcvideo` for them.

## SAFETY RULES (always)

- **Never send** vendor `0x02` OUT, `0x03`, `0x07`, `0x08` (persistent memory writes / commit).
- **Never send** `0x10` / `0x11` (suspected to make the chip drop off the bus; recovery needs a
  physical unplug, and the user may not be home).
- `uhubctl -l 3 -p 2 -a cycle` does **not** really cut power on the Pi 5 (only disables the port);
  it re-enumerates a healthy chip but cannot recover a hung one.
- Register writes: only vendor `0x00` OUT (volatile). wIndex = full XDATA address (tested 24 Nov:
  RAM 0xA77E written + restored OK). Only write data areas whose use is understood (never code / live vars).
- Ask the user before: any new write command, `git push`, anything that could hang the camera.
- Prefer read-only experiments.

## Known commands (this chip)

| Req | Dir | Use |
|---|---|---|
| 0x00 | OUT | XDATA write, 1 byte (wValue=value, wIndex=full address) — works for RAM too |
| 0x01 | IN | XDATA read, 1 byte, wIndex=addr, full 0x0000–0xFFFF → firmware dump (0x007 = EP0 FIFO, never read; retry empty reads) |
| 0x02 | IN | returns fixed 42-byte ID string "AVEO Technology Corp. All Rights Reserved." |
| 0x04 | IN | 1 byte (0x99) — unknown |
| 0x09 | IN | unimplemented: random length, returns stale EP0 buffer (echoed SETUP packets) — dead end |
| 0x0a | IN | 2 bytes (00 00) — unknown |
| 0x60/0x61, 0x8c, CT/PU exposure/gain | | STALL — not supported on this chip |

## Firmware dump (24 Nov 2026) — see docs/firmware.md

- `0x01` dumps all 64 KB XDATA (`tools/xdata_dok.py`, ~25 s). Two RAM images: V001 at 0xA200, V006 at 0xC400.
  Dump in `dumps/` (git-ignored, never commit). Ghidra: `ghidra/Fw8051.java`, Ghidra at
  `/opt/homebrew/Cellar/ghidra/12.2/libexec`.
- Vendor commands are handled in mask ROM (`LCALL 0x0070`, not dumpable).
- ⛔ Never send bRequest 0x01 with wValue hi 0x01 + wIndex 0x0400 (V001 magic: erases image signature).
- **Sensor = OmniVision OV7725** (V001 is an OV7725-only build; init table 0xA58A). I2C primitives are in mask ROM.
- V001 vendor hook (0xB0FC) just STALLs → 0x60/0x61 sensor access disabled on purpose.
- UVC PU → OV7725: brightness→0x9B, contrast→0x9C, saturation→0xA7/0xA8, sharpness→0x8F,
  power line→0x22/0x2B/0x33, **gamma v → writes 16 reg/val pairs from XDATA 0xA66A+32·v**.
- ⛔ Never send raw UVC gamma > 8 (firmware sends code bytes to the sensor, incl. COM7 reset).
- ✅ **Sensor write works** via gamma slot 8 (`tools/sensor_yaz.py`, approved & tested 24 Nov): SDE negative
  proved it; manual gain works (gain 0→0xFF = 3.3× noise). Exposure 0x08/0x10 not yet verified (needs light).
  Always end tests with `13=ff` (auto) unless manual mode is wanted; script restores slot 8 + gamma=3.

## Vendor 0x09 — done (24 Nov 2026)

Not a memory dump: length is random (Overflow / 0 / 64 regardless of wLength), content is zeros
plus copies of our own SETUP packets. usbfs rejects wLength > 4096. See docs/vendor-commands.md.
Firmware dump needs another route (e.g. reading the SPI flash / EEPROM chip directly).

## Other open items

- Light test (needs the user at home, sensor uncovered): dark ↔ light register diff; test 0x1CA
  (= 0x32, candidate "AE Target").
- Cosmic: `kozmik.py` v2 deployed to the Pi on 24 Nov (old one = `kozmik_eski_20261124.py`, not running).
  Writes `olaylar_v2.csv`, `olaylar/*.npz` (signed diff), `durum.json`, `maske.npy`.
  `--mod manuel` (sudo) = AGC/AEC off, gain 0xFF, 30 fps (auto: night mode → 15.9 fps). Restores auto on exit.
  Edge columns 0–1 / 638–639 are noisy at high gain → masked by default (`--kenar 2`).
  Running since 24 Nov 19:50 in tmux `kozmik`: `sudo python3 kozmik.py --mod manuel --kazanc 0xff`
  (= raw mode `--ham`: Y read directly, OV7725 denoise/WPC/BPC/gamma/interpolation/CMX/lens off,
  pixels independent; see docs/firmware.md "Raw pixel data"). Sensor re-inits on every stream start.
  Open: no udev rule for 1871:0f01 yet (pyusb needs root); exposure value not verified (light test).
- Docs in `docs/` and README must be updated with every finding; the user pushes to GitHub
  (`bahadir-hamza/aveo-av318s-re`) — ask before pushing.
