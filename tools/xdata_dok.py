#!/usr/bin/env python3
# Salt okunur: vendor 0x01 IN ile XDATA 0x0000-0xFFFF tam döküm (bkz. docs/firmware.md)
# Kullanım: sudo python3 xdata_dok.py 0 0x10000  -> tam_0000_10000.bin (~25 sn)
import usb.core, sys, time
dev = usb.core.find(idVendor=0x1871, idProduct=0x0F01)
bas, son = int(sys.argv[1],0), int(sys.argv[2],0)
out = bytearray(); bos = []
t0 = time.time()
for a in range(bas, son):
    v = None
    for _ in range(4):
        try:
            b = bytes(dev.ctrl_transfer(0xC2, 0x01, 0, a, 1, timeout=200))
            if b: v = b[0]; break
        except usb.core.USBError: pass
    if v is None: bos.append(a); v = 0
    out.append(v)
    if a % 0x1000 == 0xfff: print(f"0x{a:04x} {time.time()-t0:.0f}s bos={len(bos)}", flush=True)
open(f"tam_{bas:04x}_{son:04x}.bin","wb").write(out)
print("cevapsız adres sayısı:", len(bos), "ilk:", [hex(x) for x in bos[:20]])
