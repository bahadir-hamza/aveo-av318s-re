#!/usr/bin/env python3
"""
Aveo AV318S - sensör register'larını SALT OKUNUR tara
Windows sürücüsü (FUN_00034718, komut 1 GET):
    vendor 0x61, IN, wValue=0, wIndex=(yüksek << 8) | adres, 2 bayt
Yazma karşılığı 0x60'tır - bu script ONU GÖNDERMEZ.

Kullanım: sudo python3 sensor_oku.py [yuksek_bayt]     (varsayılan 0)
Kozmik ışın scripti çalışırken de kullanılabilir.
"""
import sys, time, usb.core

VID, PID = 0x1871, 0x0F01
OKUMA = 0x61
YUKSEK = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    sys.exit("Kamera bulunamadı")

def oku(adres):
    assert OKUMA == 0x61
    for _ in range(3):
        try:
            r = bytes(dev.ctrl_transfer(0xC2, OKUMA, 0, (YUKSEK << 8) | adres, 2, timeout=500))
            if len(r) == 2:
                return r
        except usb.core.USBError as e:
            return e.strerror
        time.sleep(0.003)
    return None

# İlk deneme
ilk = oku(0x00)
print(f"wIndex yüksek bayt = 0x{YUKSEK:02x}, adres 0x00 -> {ilk!r}")
if not isinstance(ilk, bytes):
    sys.exit("Okuma kabul edilmedi.")

tablo = {}
for a in range(0x100):
    tablo[a] = oku(a)

print("\n     " + " ".join(f"  {c:x}  " for c in range(8)))
for satir in range(0, 0x100, 8):
    hucre = []
    for a in range(satir, satir + 8):
        v = tablo[a]
        hucre.append(v.hex() if isinstance(v, bytes) else " -- ")
    print(f"{satir:02x}:  " + "  ".join(hucre))

# Bilinen sensör kimlikleri için ipuçları (her iki bayt sırasını da göster)
print("\nKimlik adayları:")
for a in (0x00, 0x01, 0x02, 0x0a, 0x0b, 0x1c, 0x1d, 0x30, 0x31, 0xfc, 0xfd, 0xf0, 0xf1):
    v = tablo.get(a)
    if isinstance(v, bytes):
        print(f"  0x{a:02x}: {v.hex()}   (bayt0=0x{v[0]:02x}, bayt1=0x{v[1]:02x})")
