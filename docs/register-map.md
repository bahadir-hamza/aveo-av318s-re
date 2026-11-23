# Internal register space (vendor request `0x01`, wValue = 0)

Read one byte: `ctrl_transfer(0xC2, 0x01, 0, address, 1)`.
Some reads return 0 bytes; retry. Address **`0x007` never answers** (status / read-to-clear?).
Space `0x000–0x1FF` holds data, `0x200–0x2FE` reads `0xFF`, `0x300+` reads `0x00`.

> The first dump was shifted by one byte after `0x007`; the addresses below are corrected.

## AE statistics blocks (identified)

Measured with [tools/reg_fark.py](../tools/reg_fark.py): changing UVC brightness / contrast /
gamma changes these registers, and their low bytes jitter constantly with sensor noise. They
look like **16-bit little-endian luminance measurements per window**, i.e. auto-exposure
statistics rather than settings.

| Range | Content |
|---|---|
| `0x180–0x18B` | 6 × 16-bit window values (e.g. brightness 0→100: `0x181` 14→17, `0x187` 16→20) |
| `0x1E0–0x1EF` | 8 × 16-bit window values (`0x1e1` 11→13, `0x1ed` 5→6) |

Sharpness changed only `0x1e1` slightly; saturation changed nothing in this range.
→ The actual setting registers (brightness value etc.) are **not** in `wValue = 0` space;
other `wValue` pages are still to be explored (read-only).

## "Live" registers

Change between consecutive reads with no setting changed (sensor covered, dark):

`0x01b, 0x034–0x03b, 0x03f, 0x077, 0x110, 0x115, 0x118, 0x11a, 0x11b, 0x171,
0x184, 0x185, 0x188, 0x1de, 0x1e2, 0x1e4, 0x1e5, 0x1e7, 0x1e8, 0x1ea, 0x1eb, 0x1ee`

`0x034–0x03b` change a lot every read (frame counter / timestamp / AE state?).

## Dump of `0x100–0x1FF` (sensor covered, brightness 85)

```
100  00 ac ac ff 00 00 01 ac 40 18 01 00 40 08 00 01
110  63 14 f0 0b 58 b8 2d 00 88 00 c4 74 17 06 80 11
120  49 00 80 00 40 80 20 00 00 00 00 05 01 00 e0 01
130  50 05 60 0a 60 0f 60 14 60 15 70 1f 70 29 70 33
140  70 3d 70 47 70 51 70 52 80 7d 80 a8 80 d3 80 00
150  16 28 35 3f 41 53 62 6e 7a 84 8e 8f b2 cf e8 00
160  8d e6 a6 80 80 e6 c0 9a 9a 80 80 80 d0 ad 95 86
170  00 d9 b0 01 e0 02 80 67 04 02 00 00 02 10 00 21
180  00 0e 01 02 e4 7b 00 11 4d 02 00 80 40 00 00 80
190  00 00 00 00 80 00 00 00 00 03 01 01 00 00 00 00
1a0  00 00 00 08 22 2c af 00 00 00 00 00 00 00 00 00
1b0  01 00 00 01 00 00 03 00 c2 01 00 00 bc 01 01 00
1c0  60 00 00 00 00 00 00 00 00 00 32 00 44 22 01 80
1d0  80 00 80 02 01 50 00 00 00 04 00 02 00 20 03 0b
1e0  00 0b a7 02 de 09 00 14 21 02 e1 e8 00 05 bc 00
1f0  01 00 00 20 2d 01 02 00 a1 00 00 00 00 00 00 00
```

- `0x150–0x15E`: `16 28 35 3f 41 53 62 6e 7a 84 8e 8f b2 cf e8` — monotonically increasing,
  looks like a **gamma curve**
- `0x131–0x14E`: pairs `05 60 0a 60 0f 60 14 60 15 70 …` — another (x, y) curve
- `0x160–0x16F`: `8d e6 a6 80 80 e6 c0 9a …` — colour matrix / saturation?
- `0x1CA` = `0x32` (50) — same as the driver's default **"AE Target"** → candidate, needs a test with light

## Write test (vendor `0x00` OUT)

Writes are accepted and read back correctly (`0x150`: 0x16 → 0x40 → 0x16; `0x14F`: 0x00 → 0x30 → 0x00),
but the **mean image level did not change** (7.7 ± 0.1 in the dark). Together with the fact that
UVC brightness/contrast changes no setting register here, this space looks like a **RAM copy of
the settings** (the flash-programming routine writes and verifies the same addresses), not the
live ISP registers. Registers are volatile; a USB power cycle restores them.

## TODO

- Read other `wValue` pages (read-only) to locate setting registers.
- With the sensor uncovered: dark ↔ light diff to find exposure / gain state registers.
- Identify the image sensor (chip ID) — the sensor sits on a separate round board, connected
  via parallel (DVP) bus.
