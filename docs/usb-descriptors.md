# USB / UVC descriptors

Device: `1871:0f01` Aveo Technology Corp. USB2.0 Camera (UVC 1.00)

## VideoControl topology

| ID | Entity | Notes |
|---|---|---|
| 1 | Input Terminal – Camera Sensor (`0x0201`) | `bControlSize 3`, **`bmControls 0x000000`** (no controls advertised) |
| 3 | Processing Unit | `bmControls 0x043b` → Brightness, Contrast, Saturation, Sharpness, Gamma, Power Line Frequency. lsusb warns "Descriptor too short". |
| 4 | Extension Unit | GUID `{aab8f252-8ed1-4972-8ced-96b17f04408b}`, `bNumControls 1`, `bmControls 0x01`, source ID 3 |
| 2 | Output Terminal – USB Streaming (`0x0101`) | |

Interrupt endpoint `0x85` (64 bytes) on the VideoControl interface.

## Extension Unit 4, selector 1

Queried with `UVCIOC_CTRL_QUERY` ([tools/xu_oku.py](../tools/xu_oku.py)):

| Query | Result |
|---|---|
| GET_LEN | 33 bytes |
| GET_INFO | `0x03` (GET + SET) |
| GET_CUR | **STALL** (broken pipe) — presumably needs a SET_CUR command first (mailbox style) |
| GET_MIN / MAX / RES / DEF | `00…` / `ff…` / `01 00…` / `80…` (placeholders) |

Selectors 2–16 do not respond.

In the Windows driver the XU is only passed through to user mode as a KS property set keyed by
the GUID (property Id = selector, GET_LEN then GET_CUR/SET_CUR). The user-mode program that
builds the 33-byte commands is **not** part of the driver package (`CamIntfc.ax` does not
reference the GUID). The command format is therefore still unknown.

## Unadvertised controls

The Windows driver sends Camera Terminal requests for AE mode (sel 2) and absolute exposure
time (sel 4), plus PU backlight (1), gain (4), hue (6), white balance (0x0A/0x0B).
Sent directly with pyusb ([tools/gizli_kontroller.py](../tools/gizli_kontroller.py)), **all of
them STALL**, while the advertised Brightness control answers normally with the same method
(GET_INFO `0x03`, GET_CUR `0x001e`). Conclusion: this camera does not support them; the driver
is shared between several camera models.
