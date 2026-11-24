#!/usr/bin/env python3
# Tek bayt XDATA yazma testi (kullanıcı onaylı, 24 Kas 2026)
# vendor 0x00 OUT, wValue=değer, wIndex=0xA77E (gamma v=8 tablosu, şu an kullanılmıyor)
import usb.core, sys, time
dev = usb.core.find(idVendor=0x1871, idProduct=0x0F01)
A = 0xA77E; ORIG = 0x88; TEST = 0x00
ALIAS = [0x07E, 0x17E, 0x37E, 0x77E]
def rd(a):
    for _ in range(5):
        b = bytes(dev.ctrl_transfer(0xC2, 0x01, 0, a, 1, timeout=1000))
        if b: return b[0]
    raise SystemExit(f"okuma başarısız 0x{a:04x}")
def durum(t):
    v = {a: rd(a) for a in [A] + ALIAS}
    print(t, " ".join(f"{a:04x}={x:02x}" for a, x in v.items())); return v
v0 = durum("önce :")
if v0[A] != ORIG or any(v0[a] != 0 for a in ALIAS): sys.exit("beklenmeyen durum, yazma yapılmadı")
dev.ctrl_transfer(0x42, 0x00, TEST, A, None, timeout=1000)
time.sleep(0.05)
v1 = durum("yazma:")
if v1[A] == TEST:
    print("SONUÇ: XDATA RAM yazılabiliyor -> geri yükleniyor")
    dev.ctrl_transfer(0x42, 0x00, ORIG, A, None, timeout=1000); time.sleep(0.05)
    durum("geri :")
else:
    print("SONUÇ: 0xA77E değişmedi (alias değerlerini kontrol et)")
print("ID:", bytes(dev.ctrl_transfer(0xC2, 0x02, 0, 0, 64, timeout=1000))[:20])
