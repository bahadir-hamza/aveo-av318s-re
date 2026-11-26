# Firmware / XDATA memory map (24 Nov 2026)

**Key finding:** vendor `0x01` IN (`ctrl_transfer(0xC2, 0x01, 0, addr, 1)`) is a raw 8051
**`MOVX` read of the full 16-bit XDATA space**, not only `0x000–0x1FF`. It is read-only. A full
64 KB dump takes ~25 s (`tools/xdata_dok.py 0 0x10000`). Two dumps taken one after the other
were byte-identical (camera idle). The dump is kept locally in `dumps/` (git-ignored, Aveo
copyright).

The XDATA space holds the RAM-resident firmware, so the chip can be analysed without any write
command. Ghidra headless script: `ghidra/Fw8051.java` (language `8051:BE:16:default`,
load the dump at address 0).

## Memory map

| Range | Content |
|---|---|
| `0x0000–0x00FF` | USB / core hardware registers. **`0x0007` = EP0 SETUP FIFO data port**: the ISR reads it 8× to get the SETUP packet, so a read pops the FIFO. That's why "0x007 never answers". |
| `0x0100–0x01FF` | ISP / control hardware registers (most `MOVX` targets in the code: `0x0100–0x0120`, `0x0180`, `0x01B0`, `0x01F4` …) |
| `0x01B8–0x01BF` | **Copy of the current SETUP packet** (bmRequestType, bRequest, wValue, wIndex, wLength). Reading `0x1BA` with wValue `0x5A3C` gives `3c`. |
| `0x0200–0x02FF` | repeating pattern `0c d7 67 64` |
| `0x0400–0x07FF` | USB endpoint buffers: old SETUP packets (`c2 09 … ff 0f`), copies of the "All Rights Reserved" ID string → **this is what vendor `0x09` leaks** |
| `0xA000–0xA1FF` | firmware work RAM (variables; both images use it) |
| `0xA100` | active device header: `"Aveo" 00 71 18 01 0f 11 06 …` = VID `1871`, PID `0F01`, bcdDevice `6.11` (matches lsusb), string `R003.201` |
| `0xA200–0xB3FF` | **firmware image 1**: `"Aveo"` signature, vector table at `0xA210`, version string `OTP V001.00 / Jun 11 2010 13:00:10` (at `0xA280`) |
| `0xC000–0xC3FF` | header + string descriptors of a second config: `"Aveo" 00 71 18 01 0d 17 09` (= PID `0D01`, bcd `9.17`), `Aveotek`, `USB2.0 Camera`; table at `0xC100` (pairs `9e 23 9f 45 a0 55 …`) |
| `0xC400–0xDEFF` | **firmware image 2**: vector table at `0xC410`, `OTP V006.00 / Sep 17 2010 17:02:57` (at `0xC4C0`) |
| `0xB400–0xBFFF`, `0xE000–0xFFFF`, `0x0800–0x9FFF` | `00` or `FF` (empty / unmapped) |

Vector tables use standard 8051 offsets from the table base (`+0x00` reset, `+0x03` INT0,
`+0x0B` T0, `+0x13` INT1, …) with absolute `LJMP` targets:

| | reset | INT0 (USB) | T0 | INT1 |
|---|---|---|---|---|
| V001 (`0xA210`) | `0xB007` | `0xA2C0` | `0xB10A` | `0xB10B` |
| V006 (`0xC410`) | `0xDCF5` | `0xC500` | `0xD556` | `0xDE3B` |

"OTP" = one-time-programmable memory → the driver's `0x07`/`0x08` "flash programming" is most
likely an **irreversible OTP burn**. Keep them forbidden.

Which image runs is not proven yet. The device descriptor (PID `0F01`, bcd `6.11`) matches the
header at `0xA100`, which belongs to the V001 layout, while `0xC000` describes PID `0D01`.

## USB interrupt (INT0) handler

Both ISRs do the same thing. They read `SFR 0xFF` (USB interrupt status), pop 8 SETUP bytes
from `0x0007` into `0x01B8–0x01BF`, and handle only a few requests themselves:

- `80 06 xx 02` (GET_DESCRIPTOR configuration) → own descriptor routine (`FUN_ce16` in V006)
- class `GET_CUR (0x81)`, wValue hi = 1, wIndex = 1 → VS PROBE (`FUN_ca48`)
- everything else → **`LCALL 0x0070`**, in mask-ROM CODE space. `MOVX` can't see it, so it
  isn't in the dump.
- after `SET_CONFIGURATION (0x0B)` with wValue 0: stream stop / register reset.

→ The vendor commands (`0x00`, `0x01`, `0x02`, `0x04`, `0x09`, `0x0A`, `0x10`, `0x11` …) are
handled in **mask ROM**, not in the RAM code. Their handlers can't be dumped this way.

⛔ V001 has a magic sequence. If RAM `0xA0FD == 'Z'` and a request with bRequest `0x01`,
wValue hi `0x01`, wIndex `0x0400` arrives, it clears `0xA200` (the image signature) and calls
`FUN_afbc` (re-load / switch image?). Currently `0xA0FD = 0x00`. Never send such a request.

## Image sensor: OmniVision OV7725

- **V001 (active image) is an OV7725-only build.** After sensor power-up (`FUN_ab38`) it writes
  the init table at `0xA58A` (73 reg/value pairs) with no detection. The table starts
  `12 80` (COM7 reset), `3d 03, 17 26, 18 a0, 19 04, 1a f3, 32 00, 29 a0, 2c f3, 65 20 …
  13 f0 … 90 05 91 01 … 9e 81, a6 04`, then gamma `7e…8d`. This is the well-known OV7725 VGA
  setup.
- The base code (V006 region) supports several sensors. `FUN_ccef` sets the SCCB address
  `0x42/0x43` (RAM `0xA15D/0xA15E`) and reads PID `0x0A` / VER `0x0B`:
  `77 4x` → type `0x44` (OV7740?), `77 2x` → `0x43` (OV7725), `76 7x` → `0x41` (OV7670,
  extra check of reg `0xBB`). Its tables at `0xC880–0xCA20` are OV7670 settings.
- **I2C (SCCB) primitives are in mask ROM.** Thunk table at `0xD819`: `d819` → `LCALL 0x9593`
  (read reg R7), `d81d` → `0x9963` (write R5 → reg R7), `d821` → `0x90F1` (write N pairs from
  XDATA pointer R4:R5, count R6:R7), more thunks follow.

### Hook table and why vendor `0x60` / `0x61` STALL

Each image has a hook table at vector base `+0x40`. The mask ROM calls it for vendor / class
requests:

| Slot | V006 (base) | V001 (active) |
|---|---|---|
| `+0x40` vendor hook | `0xD3DC`: `0x60` = sensor I2C write (reg = wIndex lo, val = wValue lo), `0x61` = sensor I2C read, `0xF0` = XDATA block read (addr = wIndex, len = wLength) | `0xB0FC`: `[0x0005] \|= 2` → **STALL** |
| `+0x44` PU SET_CUR hook | `0xD136` | `0xAA4A` (see below) |

→ The active OV7725 firmware **deliberately disables** the USB sensor access that the base code
(and the Windows driver's vendor `0x60`) supports.

### UVC Processing Unit → OV7725 registers (`0xAA4A`, V001)

| Internal code (`0xA08C`) | UVC control (v4l2 range) | OV7725 writes |
|---|---|---|
| `0xA7` | brightness (0–100) | `0x9B` BRIGHT = value |
| `0xA9` | contrast (0–100) | `0x9C` CNST = value |
| `0xB3` | saturation (0–4) | `0xA6` SDE \|= 2, `0xA7` USAT, `0xA8` VSAT = value << 5 |
| `0xB5` | sharpness (FW accepts < 32) | `0xAC` bit5 cleared (manual), `0x8F` EDGE low 5 bits = value |
| `0xB7` | **gamma (1–8)** | `d821`: writes **16 (reg, value) pairs from XDATA `0xA66A + 32·v`** |
| `0xAD` | power line freq (0–2) | `0x22` BDBase, `0x2B` EXHCL, `0x33` DM_LNL (banding) |

So brightness is only a DSP offset. Exposure (`0x08` AECH / `0x10` AEC), gain (`0x00`) and
COM8 (`0x13`, `0xFF` = all auto) are never touched by any UVC control.

The gamma tables for v = 1…8 are at `0xA68A, 0xA6AA … 0xA76A`. They are in RAM and each holds
16 pairs `7e…8d`. The firmware accepts v up to 100. Above 8 it sends **code bytes as reg/value
pairs** to the sensor (e.g. `COM7 = 0x80` = sensor reset at several v). ⛔ **Never send gamma > 8
with a raw UVC request.** uvcvideo clamps to 1–8.

### XDATA write works (tested 24 Nov 2026)

**Vendor `0x00` OUT writes any XDATA address**: `ctrl_transfer(0x42, 0x00, value, addr, None)`,
with wIndex = the full 16-bit address. The old "`0x100 | addr`" rule was just the address of
the `0x1xx` registers. Test (`tools/xdata_yaz_test.py`): `0xA77E` (register byte of
gamma slot 8, not in use) `0x88 → 0x00 → 0x88`. Possible aliases `0x07E/0x17E/0x37E/0x77E` did
not change. The chip stayed healthy (ID string OK, still enumerated). Before the test the
address/value was chosen so that any alias would have received its current value.

⚠️ This is a write into the running firmware's RAM: writing code or live variables can crash
the chip (recovery = physical unplug). Only write data areas whose use is understood.

### Plan: full sensor control through the gamma table

A custom 16-pair table placed in one gamma slot, followed by `v4l2-ctl -c gamma=N`,
would let the firmware itself write any OV7725 register: AEC/AGC off (`0x13`), exposure
(`0x08`/`0x10`), gain (`0x00`). Everything is volatile and reset on replug. Needs a write test
(user approval).

### ✅ Sensor writes work (tested 24 Nov 2026, `tools/sensor_yaz.py`)

Method: replace the last N pairs of gamma slot 8 (`0xA76A`, 16 pairs) with our own
(reg, value) pairs, then `v4l2-ctl -c gamma=8`. On stream start the firmware re-applies all PU
values, including gamma → our pairs reach the OV7725. The script checks the slot against the
known original before writing, and in `finally` restores it and sets gamma=3. Sensor
covered (dark), 640×480 YUYV, 10 frames after 20 warm-up frames:

| Pairs written | mean | temporal std / pixel | max |
|---|---|---|---|
| baseline gamma=3 (brightness 85) | 0.27 | 0.40 | 3 |
| `a6=46` (SDE negative) | **255.0** | 0.01 | 255 |
| `a6=06` (back to normal) | 0.58 | 0.53 | 40 |
| brightness 100: auto (`13=ff`) | 13.7 | 1.21 | 63 |
| brightness 100: `13=fa 00=00` (AEC/AGC off, gain 0) | 16.4 | **0.61** | 48–55 |
| brightness 100: `13=fa 00=ff` (gain max) | 14.0 | **2.0** | 87–104 |

- The negative-image test proves the write path.
- **Manual gain works**: gain 0x00 vs 0xFF changes the temporal noise by 3.3×. Auto AGC in the
  dark sits in between, so it is *not* at max gain.
- Exposure (`08/10` = 2 vs 512 lines) made no difference in the dark. That's expected; it needs
  a light test.
- At brightness 85 the dark image is clipped at 0, so noise is hidden. Use a higher brightness
  (offset) to see it.
- COM8 stays manual until `13=ff` is written again (or replug). The script's last step should
  always be `13=ff` unless manual mode is wanted.

Usage: `sudo python3 tools/sensor_yaz.py "13=fa 00=ff 08=01 10=f0" "13=ff"` (each argument =
one test with up to 16 hex pairs).

## Raw pixel data (24 Nov 2026)

Tools: `tools/ham_kare.py` (apply pairs, save raw YUYV bytes with `CAP_PROP_CONVERT_RGB=0`),
`tools/gurultu_kor.py` (noise correlation between neighbours), `tools/dsp_test.py`.
Sensor covered, gain 0xFF, AGC/AEC off.

**1. Read Y directly.** OpenCV's YUYV→BGR→gray conversion moves black (Y≈22) to ≈7 and
clips the negative noise at 0. The raw YUYV buffer `(480, 640, 2)`, `[..., 0]` = Y, keeps the
offset.

**2. The OV7725 DSP was smoothing and erasing single pixels.** OV7725 init values: `0x64` DSP_Ctrl1 =
`0xFF` (all stages on), `0x46` = `0x05` (lens correction), `0x0E` = `0xD9` (night mode).
Noise correlation between neighbouring pixels (0 = independent pixels):

| Setting | σ | horiz. k=1/2/3 | vert. r=1/2/3 |
|---|---|---|---|
| default | 1.17 | 0.77 / 0.58 / 0.38 | 0.72 / 0.48 / 0.25 |
| denoise + sharpness off (`ac=9f 8e=00 8f=00`) | 1.72 | 0.61 / 0.20 / 0.15 | 0.55 / 0.07 / 0.02 |
| **+ `64=e0 46=04`** (only SDE on) | 1.92 | **0.01 / 0.01 / 0.00** | **0.00 / 0.01 / 0.00** |

- The ~4-pixel smoothing kernel was the sensor's **auto denoise** (`0xAC` bit 6).
- The remaining 2-tap correlation was the Bayer interpolation (`0x64` bit 3).
- With `64=fe` (white-pixel correction off) transient single pixels went from 39 → 357 /min
  and stable bright pixels from 0 → ~300. **WPC replaces every isolated bright pixel**, which
  is exactly what a single-pixel hit looks like.
- `0x64` bit 5 (SDE) must stay on: it adds the black offset. With `64=c0`, Y≈1 and the noise
  is clipped again.
- With interpolation off the Y value of each pixel is the single Bayer pixel (2×2 phase means
  differ slightly). The data is **raw 8-bit per pixel**.

**3. COM7 RAW Bayer (`12=02`) also streams** (24 fps, no errors). Every byte of the YUYV
buffer is then a pixel value. With all DSP off, odd bytes are 0 and even bytes carry data with
a −0.23 horizontal correlation, so the bridge still does something to this path. The YUV path
with DSP off (above) is cleaner.

**4. The sensor re-runs the init table at every stream start** (COM7, denoise … reset). After
that the firmware re-applies the PU values (gamma slot 8 → our pairs). So settings never stick,
and opening the stream with the original slot fully restores the sensor.

10-bit data is not possible: the OV7725 ADC is 10-bit, but the DVP bus to the bridge is 8-bit.

`kozmik.py --mod manuel` now uses this "raw" mode by default (`--ham`, pairs in
`cosmic/aveo_sensor.py: HAM_CIFTLER`). First 2 min: black Y≈22, σ≈2.0, 2587 masked pixels
(1920 = edge columns, ~670 hot pixels formerly hidden by WPC), 1.5 events/min (all 2 px,
peak 26–33, close to the threshold).

## Event selection in raw mode (24 Nov 2026)

With WPC/denoise off and gain 0xFF the dark noise is **heavy-tailed**: σ≈2.1, but 1.3 % of the
pixels are > +10 in every frame. Within 3 min, 290 k different pixels exceeded +15 and 77
different pixels exceeded +40 exactly once. Single-pixel / threshold rules can't separate hits
from noise, and masking "noisy" pixels fails because nearly all pixels are occasionally noisy
(a max-deviation mask hid 76 % of the sensor). Data: `tools/seyrek_kayit.py` (stores every
pixel > +10 per frame), `tools/seyrek_analiz.py`.

Pixel noise is independent (correlation 0.00), so **adjacent-pixel pairs are random
coincidences**. Measured pair rates match `N(>T1)/frame × 8 × P(>T2)` (e.g. T>15: 2500/min
measured vs 2470 expected, the same in every direction, no readout artefact). Rule used by
`kozmik.py` since 24 Nov 20:25:

- event = ≥ 2 8-connected pixels > T2 = `max(20, 6σ)` with peak > T1 = `max(40, 8σ)`
- veto: the cluster contains a pixel that exceeded T2 more than 3×/min so far (RTS); the first
  120 s only collect these statistics
- expected accidental rate (no veto) ≈ 0.7–0.9 /min; with the veto almost all of it goes away.
  `durum.json: rastlanti_dk_ust_sinir` is the running upper bound (vetoed pixels included).

Earlier thresholds (T1 = 25–30) gave 1–1.5 events/min of pure coincidences. Expected physics
rate for 0.12 cm²: muons ≈ 0.1/min plus some γ/β background. First 6 min with the new rule:
0 events.

### First night with this rule (24 → 25 Nov, 20:25–07:45, 11.3 h)

Stable: 30 fps, 1.22 M frames, 0 disconnects, 0 light-leak frames, Pi at 52 °C.
**11 events** (≈1/h), 645 clusters vetoed (noisy pixels, 593 flagged).

| Time | Peak | Neighbour | Note |
|---|---|---|---|
| 21:20, 22:35, 01:33, 04:03, 05:58 | 40–44 | 21–27 | 2 px |
| 06:32:50 + 06:33:03 | 70 / 62 | 22 / 20 | **same pixel (307,42) 13 s apart → suspicious** |
| 06:35, 07:09, 07:43 | 40–57 | 20–28 | 2 px |
| **07:19** | **232** | **123** | clearest candidate |

Is a 2-pixel event noise? Check on the 3-min sparse recording: isolated noise spikes on quiet
pixels are truly single-pixel. Of 442 spikes > 30, **none** had a neighbour > 20, and only
~1 % had a neighbour > 10, the same in every direction (no readout echo). Every night event
has a neighbour > 20, so they are statistically separated from noise and look like charge
sharing. The rate (~1/h) is below the rough muon estimate (~6/h): with a peak threshold of 40
many deposits are probably missed. Since noise spikes > 30 never had a > 20 neighbour, T1 can
likely be lowered to 30.

### 45 h run (24 Nov 20:25 → 26 Nov 17:53): repeating pixels

Stable: 30 fps, 4.9 M frames, 0 disconnects, 0 light-leak frames. **44 events**, 2185 vetoed.
But **19 of the 44 events sit on just 9 spots** (within ±3 px). For 44 random hits about 0.15
such pairs would be expected, so these are **defect pixels that fire rarely** (minutes to hours
apart, too slow for the rate veto). Examples: (316,360) at 01:25, 04:45, 13:02; (361,421) peak
161 twice 12 s apart; (146,434) 1 s apart. The old repeat mask (3 events in the same 4×4 cell)
never fired, because one pixel's events fell on both sides of a cell border (y = 359 / 360).

Without the repeating spots: **25 single events in 45.4 h ≈ 0.55/h**. Best ones: 25 Nov 07:19
(peak 232, neighbour 123) and 25 Nov 13:37 (peak 232, x = 631 near the edge). 26 Nov
14:00–17:30 had more events (13 in 3.5 h, half of them repeats); the singles rose to ~1.7/h,
possibly temperature (not checked).

Fix (`kozmik.py`, from 26 Nov 17:53): the history of all events is read from `olaylar_v2.csv`
at start (survives restarts). A new event within `--tekrar-r 3` px of an earlier one is still
written, with column `tekrar` = number of earlier events nearby; once a spot reaches `--tekrar 2`
events it goes into the persistent mask. Old rows got the column retroactively (backup
`olaylar_v2.csv.bak`). For analysis, count only spots that ever had a single event:
the *first* event of a later-repeating spot has `tekrar = 0`.

## Next steps

- Try T1 = 30 (`--esik 30`) for one night and compare the rate (after the repeat fix has
  run a while, defect pixels would dominate a lower threshold).
- Calibrate with a known weak source (KCl "light salt" next to the sensor): rate must rise.
- Light test (user at home): verify exposure `0x08/0x10`, find the max useful exposure
  (frame length, dummy lines `0x2D/0x2E`, clock `0x11`).
- Cosmic detector: run with manual max gain + max exposure (`13=fa 00=ff …`) instead of auto
  and compare hit rate / noise. Possibly use longer frames (lower fps) for a higher duty cycle.
- Keep a persistent "sensor mode" in `kozmik.py`: write the slot, set gamma=8 at start; the
  table is lost on replug.
- Re-dump while streaming and diff against the idle dump → live variables (AE state).
