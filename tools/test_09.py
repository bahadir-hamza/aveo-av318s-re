#!/usr/bin/env python3
# Salt okunur: vendor 0x09 IN, wValue/wIndex etkisi ve cevap uzunluğu dağılımı (bkz. docs/vendor-commands.md)
import usb.core, collections
dev = usb.core.find(idVendor=0x1871, idProduct=0x0F01)
def r(wl, wv=0, wi=0):
    try: return bytes(dev.ctrl_transfer(0xC2, 0x09, wv, wi, wl, timeout=1000))
    except usb.core.USBError as e: return f"E{e.errno}"
for name, wv, wi in [("taban",0,0),("wV=1",1,0),("wV=0x100",0x100,0),("wV=0x8000",0x8000,0),
                     ("wI=1",0,1),("wI=0x100",0,0x100),("wI=0x8000",0,0x8000)]:
    c = collections.Counter(); nz = set()
    for k in range(20):
        b = r(0x0FFF, wv, wi)
        if isinstance(b, str): c[b] += 1
        else:
            c[len(b)] += 1
            nz |= {(i, v) for i, v in enumerate(b) if v}
    print(f"{name:10s} {dict(c)} nonzero={sorted(nz)[:10]}")
print("ID:", bytes(dev.ctrl_transfer(0xC2, 0x02, 0, 0, 64, timeout=1000))[:20])
