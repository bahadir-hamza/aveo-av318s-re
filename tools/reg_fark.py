#!/usr/bin/env python3
"""
Aveo AV318S - ISP register fark analizi (SALT OKUNUR)
Register okuma: vendor 0x01 IN (bmRequestType 0xC2), wIndex=adres, 1 bayt.
Kameraya YAZMA yapılmaz; ayarlar sadece normal v4l2-ctl (UVC) ile değiştirilir.

Kullanım: sudo python3 reg_fark.py
Not: Kozmik ışın scripti çalışıyorsa test sırasında birkaç sahte olay görebilirsin.
     Test bitince brightness tekrar 85'e ayarlanır.
"""
import subprocess, time, usb.core

VID, PID = 0x1871, 0x0F01
ARALIK = range(0x000, 0x200)
CIHAZ = "/dev/video0"
SON_BRIGHTNESS = 85

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    raise SystemExit("Kamera bulunamadı")

bos_sayac = {}

def oku1(adr):
    # Bazı okumalar 0 bayt dönebiliyor: 5 kez dene, olmazsa 0xFFFF (okunamadı) işaretle
    for _ in range(5):
        r = dev.ctrl_transfer(0xC2, 0x01, 0, adr, 1, timeout=500)
        if len(r) == 1:
            return r[0]
        time.sleep(0.002)
    bos_sayac[adr] = bos_sayac.get(adr, 0) + 1
    return 0xFFFF

def oku_hepsi():
    return [oku1(a) for a in ARALIK]

def ayarla(ad, deger):
    subprocess.run(["v4l2-ctl", "-d", CIHAZ, "-c", f"{ad}={deger}"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)

def fark(a, b, haric=()):
    return [(i + ARALIK.start, a[i], b[i]) for i in range(len(a))
            if a[i] != b[i] and 0xFFFF not in (a[i], b[i])
            and (i + ARALIK.start) not in haric]

def yaz(baslik, liste):
    print(f"\n== {baslik} ==")
    if not liste:
        print("  (değişen register yok)")
    for adr, x, y in liste:
        print(f"  0x{adr:03x}: {x:3d} (0x{x:02x})  ->  {y:3d} (0x{y:02x})")

# 1) Kendiliğinden değişen register'lar (5 okuma)
print("Canlı register'lar aranıyor...")
okumalar = [oku_hepsi() for _ in range(5)]
canli = set()
for o in okumalar[1:]:
    canli |= {adr for adr, _, _ in fark(okumalar[0], o)}
print("Kendiliğinden değişenler:", ", ".join(f"0x{a:03x}" for a in sorted(canli)) or "yok")
for adr in sorted(canli):
    print(f"  0x{adr:03x}: " + " ".join(f"{o[adr - ARALIK.start]:3d}" for o in okumalar))

# 2) Her kontrolü min ve max'a çekip farka bak
testler = [("brightness", 0, 100), ("contrast", 0, 100), ("saturation", 0, 4),
           ("gamma", 1, 8), ("sharpness", 0, 100)]
for ad, dusuk, yuksek in testler:
    ayarla(ad, dusuk);  a = oku_hepsi()
    ayarla(ad, yuksek); b = oku_hepsi()
    yaz(f"{ad}: {dusuk} -> {yuksek}", fark(a, b, haric=canli))

# Varsayılanlara dön
for ad, deger in [("contrast", 57), ("saturation", 2), ("gamma", 3), ("sharpness", 10),
                  ("brightness", SON_BRIGHTNESS)]:
    ayarla(ad, deger)
print(f"\nAyarlar geri yüklendi (brightness={SON_BRIGHTNESS}).")
if bos_sayac:
    print("Okunamayan adresler (kaç kez):",
          ", ".join(f"0x{a:03x}({n})" for a, n in sorted(bos_sayac.items())))
