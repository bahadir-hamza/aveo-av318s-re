#!/usr/bin/env python3
"""
Vendor 0x8c testi: pozlama mı, odak mı?
Sürücü (komut 0xF0, alt kod 4/5): vendor 0x8c OUT, wValue = seviye (1..34), wIndex = 0, veri yok
Her seviyede kare hızı, ortalama parlaklık ve gürültü (std) ölçülür.
Test sonunda: sudo uhubctl -l 3 -p 2 -a cycle -d 3   (çipi sıfırla)
Kozmik ışın scriptini önce durdur.
"""
import time, usb.core, cv2, numpy as np

dev = usb.core.find(idVendor=0x1871, idProduct=0x0F01)
if dev is None:
    raise SystemExit("Kamera bulunamadı")

def gonder(seviye):
    assert 1 <= seviye <= 34
    dev.ctrl_transfer(0x42, 0x8C, seviye, 0, None, timeout=500)

def olc(sure=4.0):
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    for _ in range(20):            # AE / ayar otursun
        cap.read()
    n, ort, std, t0 = 0, [], [], time.time()
    while time.time() - t0 < sure:
        ok, f = cap.read()
        if ok:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
            ort.append(g.mean()); std.append(g.std()); n += 1
    cap.release()
    return n / sure, float(np.mean(ort)), float(np.mean(std))

def satir(ad, r):
    print(f"{ad:<14} fps={r[0]:5.1f}   ortalama={r[1]:6.2f}   gürültü(std)={r[2]:5.2f}")

satir("başlangıç", olc())
for s in (1, 17, 34, 1):
    try:
        gonder(s)
    except usb.core.USBError as e:
        print(f"seviye {s}: istek reddedildi ({e.strerror})")
        continue
    time.sleep(0.3)
    satir(f"0x8c = {s}", olc())
print("\nBitti. Çipi sıfırlamak için: sudo uhubctl -l 3 -p 2 -a cycle -d 3")
