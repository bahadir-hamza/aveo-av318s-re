#!/usr/bin/env python3
"""
Aveo AV318S - çip register yazma testi (KONTROLLÜ)
Okuma : vendor 0x01 IN , wIndex = adres (0x100-0x1FF), 1 bayt
Yazma : vendor 0x00 OUT, wValue = değer, wIndex = adres   (sürücüdeki komut 2)
İzin verilen tek yazma isteği 0x00'dır; adres 0x100-0x1FF dışına çıkamaz.
Register'lar uçucudur: sorun olursa  sudo uhubctl -l 3 -p 2 -a cycle -d 3

Kullanım:
  sudo python3 reg_yaz_test.py dok                 # 0x100-0x1FF tablosunu göster
  sudo python3 reg_yaz_test.py ayni 0x150          # adrese mevcut değerini yaz (değişiklik yok)
  sudo python3 reg_yaz_test.py dene 0x150 0x40     # değeri değiştir, görüntü ortalamasını ölç, geri al
Kozmik ışın scriptini önce durdur.
"""
import sys, time, usb.core

VID, PID = 0x1871, 0x0F01
dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    sys.exit("Kamera bulunamadı")

def oku(adr):
    for _ in range(5):
        r = dev.ctrl_transfer(0xC2, 0x01, 0, adr, 1, timeout=500)
        if len(r) == 1:
            return r[0]
        time.sleep(0.003)
    return None

def yaz(adr, deger):
    assert 0x100 <= adr <= 0x1FF, "adres 0x100-0x1FF dışında"
    assert 0 <= deger <= 0xFF
    dev.ctrl_transfer(0x42, 0x00, deger, adr, None, timeout=500)   # bRequest 0x00, OUT

def ortalama(n=30):
    import cv2, numpy as np
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    for _ in range(15):
        cap.read()
    vals = []
    for _ in range(n):
        ok, f = cap.read()
        if ok:
            vals.append(float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()))
    cap.release()
    return sum(vals) / len(vals) if vals else float("nan")

mod = sys.argv[1] if len(sys.argv) > 1 else "dok"

if mod == "dok":
    for s in range(0x100, 0x200, 16):
        d = [oku(a) for a in range(s, s + 16)]
        print(f"{s:03x}  " + " ".join("--" if v is None else f"{v:02x}" for v in d))

elif mod == "ayni":
    adr = int(sys.argv[2], 0)
    v = oku(adr)
    print(f"0x{adr:03x} önce: {v}")
    yaz(adr, v)
    time.sleep(0.05)
    print(f"0x{adr:03x} sonra: {oku(adr)}  (aynı değer yazıldı)")

elif mod == "dene":
    adr, yeni = int(sys.argv[2], 0), int(sys.argv[3], 0)
    eski = oku(adr)
    print(f"0x{adr:03x} = 0x{eski:02x}, görüntü ortalaması ölçülüyor...")
    m0 = ortalama()
    yaz(adr, yeni); time.sleep(0.1)
    print(f"yazıldı 0x{yeni:02x}, okunan 0x{oku(adr):02x}")
    m1 = ortalama()
    yaz(adr, eski); time.sleep(0.1)
    print(f"geri alındı, okunan 0x{oku(adr):02x}")
    m2 = ortalama()
    print(f"ortalama: önce {m0:.2f} | değişiklikle {m1:.2f} | geri alınca {m2:.2f}")
