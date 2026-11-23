# Vendor commands (from the Windows driver)

Source: `dvitdcnt.sys` v2.9.9.5 (x64, AVStream, internal project name `avstreamuvc` /
`aveodcnt`). Addresses are Ghidra virtual addresses (image base `0x10000`).

## Driver building blocks

| Address | Name given | What it does |
|---|---|---|
| `0x2b368` | `usb_is_high_speed` | IRP_MJ_PNP / QUERY_INTERFACE on the USB bus interface |
| `0x2b8dc` | `usb_submit_urb_sync` | `IOCTL_INTERNAL_USB_SUBMIT_URB` (0x220003), waits for completion |
| `0x2ba18` | `usb_get_config_descriptor` | URB function `0x0B`, descriptor type 2 |
| `0x2ba90` | `usb_vendor_request` | URB function **`0x19`** (VENDOR_ENDPOINT): request, value, index, buffer, length, direction |
| `0x2bb24` | `uvc_class_request` | URB function **`0x1B`** (CLASS_INTERFACE) |
| `0x2bbb8` | `uvc_vs_probe_commit` | class request, wIndex = interface, fixed length 26 (VS PROBE/COMMIT) |
| `0x2bc04` | `uvc_unit_request` | class request, wIndex = unit << 8 |
| `0x58818` / `0x588fc` | `xu_get` / `xu_set` | KS property handlers, XU pass-through (GET_LEN → GET_CUR / SET_CUR) |
| `0x57bc8` | (registry load) | reads all settings from the registry (Exposure, AE Gain, BPC Enable, …) |
| `0x30404` | (format convert) | YUY2/UYVY/RGB conversion, **MJPG decoder** ("decoder error=%d"), scaling |
| `0x34f8c` | (property dispatcher) | central handler for the driver's private property set, see below |

Entity IDs are not hard-coded; the driver stores them in its device context:
`+0x70` = Camera Terminal, `+0x78` = Processing Unit, `+0x80` = Extension Unit.

## Vendor requests

Recipient is *endpoint* (`bmRequestType` **`0xC2`** for IN, **`0x42`** for OUT); on Linux
`0xC2` works with pyusb without detaching `uvcvideo`.

| bRequest | Dir | wValue | wIndex | Len | Meaning | Safety |
|---|---|---|---|---|---|---|
| `0x01` | IN | 0 | address | 1 / 8 | **Read internal register / memory byte(s)** | ✅ read-only |
| `0x00` | OUT | value | address \| `0x100` | 0 | register write (generic, property cmd 2) | ⚠️ untested |
| `0x60` | OUT | value | (sub << 8) \| addr | 0 | register write, probably sensor (property cmd 1) | ⚠️ untested |
| `0x5e` | OUT | 0 | value | 0 | Low-light mode | ⚠️ untested |
| `0x5f` | OUT | 0 | 0/1 | 0 | manual white balance enable | ⚠️ untested |
| `0x69` / `0x6a` / `0x6b` | OUT | gain | 0 | 0 | WB R / G / B gain (default `0x32`) | ⚠️ untested |
| `0x8c`, `0xb0`, `0xd1`, `0x61`, `0xaa` | | | | | unknown | ⚠️ |
| **`0x02`** | OUT | 0 | addr | n | block write, followed by `0x03` | ⛔ **NEVER** |
| **`0x03`** | OUT | 0 | 1 | 0 | commit (200 ms delay) | ⛔ **NEVER** |
| **`0x07`** | OUT | 0 | 32-byte page no. | 32 | write page | ⛔ **NEVER** |
| **`0x08`** | OUT | 0 | 1 | 0 | burn / commit after verify (200 ms delay) | ⛔ **NEVER** |

`0x07` → verify via `0x01` → `0x08` is a classic **flash/EEPROM programming** sequence
(function `0x2c624`). `0x02` + `0x03` follows the same write-then-commit pattern.

## Private property set (dispatcher `0x34f8c`)

`Id` = command, `+0x18` = sub-op (`0x01` set auto flag, `0x03` set value, `0xff` reset),
`+0x20` = value.

| Id | Function | Goes to |
|---|---|---|
| 1 | raw write | vendor `0x60` |
| 2 | raw write | vendor `0x00` |
| 3 | flash programming | vendor `0x07`/`0x08` ⛔ |
| 4 | mirror / flip / low light | driver flags, vendor `0x5e` |
| 5 | exposure (auto / manual) | CT sel 2 & 4 (STALL on this camera) |
| 6 | white balance | vendor `0x5f`, `0x69`–`0x6b` |
| 7–0x0b, 0x17 | backlight, hue, sharpness, gamma, brightness, contrast… | PU requests |
| 0x0e, 0x0f, 0x11, 0x14, 0x15 | auto contrast, effects, **BPC**, digital zoom/pan, special effects | **software only** (driver context) |
| 0x18, 0x41, 0xf0 | unknown | vendor `0xd1`, `0xb0`, `0x8c` |
| 0xf1 | block write + commit | vendor `0x02`/`0x03` ⛔ |

## Tested on the device (23 Nov 2026)

The driver supports several Aveo chip generations; this AV318S answers only a subset.

### Chip identification (driver function `0x2b220`)

1. Vendor `0x02` **IN**, wValue 0, wIndex 0 → the chip always returns 42 bytes:
   `AVEO Technology Corp. All Rights Reserved.` The driver compares it with its own copy
   (genuine-chip check). ✅ our chip
2. If that fails: vendor `0x08` **IN**, 12 bytes, compared with `"Ver R"` — older generation.
   Never sent to our chip by the driver → **not tested** (0x08 OUT is the flash commit command).

### Results

| bRequest | Dir | Result on this chip |
|---|---|---|
| `0x00` | OUT | ✅ **register write works**: wValue = value, wIndex = `0x100 \| addr`; read-back via `0x01` confirms |
| `0x01` | IN | ✅ register read |
| `0x02` | IN | ✅ identification string (42 bytes, independent of wLength) |
| `0x60` / `0x61` | OUT / IN | ❌ STALL for every wIndex high byte 0x00–0xFF (sensor access of another generation?) |
| `0x8c` | OUT | ❌ STALL (level 1–34; probably focus motor of the "financial camera" model) |
| CT / PU unadvertised controls | | ❌ STALL (see usb-descriptors.md) |

### IN-direction scan of all bRequest codes (wValue 0, wIndex 0, wLength 64)

`0x03`, `0x07`, `0x08` were skipped on purpose.

| bRequest | Answer |
|---|---|
| `0x01` | 1 byte (`f4`) |
| `0x02` | 42 bytes (identification string) |
| `0x04` | 1 byte (`99`) — unknown |
| `0x09` | **more than 64 bytes** (overflow) — unknown, possibly a memory block → see `tools/bellek_dok.py` |
| `0x0a` | 2 bytes (`00 00`) — unknown |
| `0x10`, `0x11` | accepted, 0 bytes … |
| `0x12`–`0x1b` | timeouts, then the device **dropped off the bus** |

> ⛔ **`0x10` / `0x11` make the chip disconnect and hang.** It did not re-enumerate, and on a
> Raspberry Pi 5 `uhubctl` could not recover it (the Pi 5 does not really cut VBUS, it only
> disables the port). A physical unplug is needed. Never send them.

### Windows property page (`CamIntfc.ax`)

The user-mode part only offers: horizontal / vertical flip, anti-flicker 50/60 Hz, special colour
(B&W, sepia, sea blue, grass green), face tracking, and software effects (negative, glass,
monitor, distorting mirror, emboss, neon, fish-eye, canvas, mosaic, magnifier, aim, newspaper,
photo frames, digital zoom). **No exposure, gain or focus control** — the exposure code in the
driver belongs to other camera models. Talks to the driver via `KsSynchronousDeviceControl`;
9 UI languages.
