# Internal register space (vendor request `0x01`, wValue = 0)

Read one byte: `ctrl_transfer(0xC2, 0x01, 0, address, 1)`.
Some reads return 0 bytes; retry. Address **`0x007` never answers** (status / read-to-clear?).
Space `0x000–0x1FF` holds data, `0x200–0x2FE` reads `0xFF`, `0x300+` reads `0x00`.

> The first full dump was taken with a script that did not handle the empty read at `0x007`,
> so table contents listed below from that dump may be shifted by one byte. Re-dump with the
> current [tools/eeprom_oku.py](../tools/eeprom_oku.py).

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

## Tables seen in the first dump (addresses approximate, see note above)

- around `0x14F–0x15E`: `16 28 35 3f 41 53 62 6e 7a 84 8e 8f b2 cf e8` — monotonically
  increasing → most likely a **gamma curve**
- around `0x130–0x14D`: pairs `05 60 0a 60 0f 60 14 60 15 70 …` — another curve (x, y)
- around `0x160`: `e6 a6 80 80 e6 c0 9a 9a 80 80 80 d0 …` — colour matrix / saturation?

## TODO

- Read other `wValue` pages (read-only) to locate setting registers.
- With the sensor uncovered: dark ↔ light diff to find exposure / gain state registers.
- Identify the image sensor (chip ID) — the sensor sits on a separate round board, connected
  via parallel (DVP) bus.
