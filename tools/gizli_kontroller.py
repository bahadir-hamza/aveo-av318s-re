#!/usr/bin/env python3
"""
Aveo AV318S - bildirilmemiş (gizli) UVC kontrollerini yoklama
Camera Terminal (Unit 1) bmControls=0 ama Windows sürücüsü pozlama komutları gönderiyor.

Kurulum : sudo apt install -y python3-usb
Kullanım:
  sudo python3 gizli_kontroller.py                 # sadece OKUR (güvenli)
  sudo python3 gizli_kontroller.py --manuel 300    # AE kapat, pozlama=300 (x100us = 30 ms)
  sudo python3 gizli_kontroller.py --otomatik      # AE'yi geri aç

Not: Çalışırken uvcvideo sürücüsü geçici olarak ayrılır, bitince geri takılır.
     Kozmik ışın scriptini önce durdur (Ctrl+C).
"""
import sys, usb.core, usb.util

VID, PID = 0x1871, 0x0F01
VC_IF = 0          # VideoControl arayüzü
CT, PU = 1, 3      # Camera Terminal ID, Processing Unit ID

SET_CUR, GET_CUR, GET_MIN, GET_MAX, GET_RES, GET_LEN, GET_INFO, GET_DEF = \
    0x01, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87

# (birim, selector, uzunluk, ad)
KONTROLLER = [
    (CT, 0x02, 1, "CT  AE Mode (otomatik pozlama modu)"),
    (CT, 0x03, 1, "CT  AE Priority"),
    (CT, 0x04, 4, "CT  Exposure Time Absolute (x100us)"),
    (CT, 0x05, 1, "CT  Exposure Time Relative"),
    (PU, 0x01, 2, "PU  Backlight Compensation"),
    (PU, 0x04, 2, "PU  Gain"),
    (PU, 0x06, 2, "PU  Hue"),
    (PU, 0x0A, 2, "PU  White Balance Temperature"),
    (PU, 0x0B, 1, "PU  White Balance Temperature Auto"),
]

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    sys.exit("Kamera bulunamadı")

def al(birim, sel, istek, uzunluk):
    return bytes(dev.ctrl_transfer(0xA1, istek, sel << 8, (birim << 8) | VC_IF, uzunluk, timeout=500))

def yaz(birim, sel, veri):
    dev.ctrl_transfer(0x21, SET_CUR, sel << 8, (birim << 8) | VC_IF, veri, timeout=500)

def sayi(b):
    return int.from_bytes(b, "little") if b else None

ayrildi = False
try:
    if dev.is_kernel_driver_active(VC_IF):
        dev.detach_kernel_driver(VC_IF)
        ayrildi = True

    if "--manuel" in sys.argv or "--otomatik" in sys.argv:
        if "--manuel" in sys.argv:
            deger = int(sys.argv[sys.argv.index("--manuel") + 1])
            yaz(CT, 0x02, bytes([0x01]))                 # AE Mode = 1 (manuel)
            yaz(CT, 0x04, deger.to_bytes(4, "little"))   # pozlama süresi
            print(f"AE kapatıldı, pozlama = {deger} (x100us = {deger/10:.1f} ms)")
        else:
            yaz(CT, 0x02, bytes([0x02]))                 # AE Mode = 2 (otomatik)
            print("AE açıldı")
        print("Okuma doğrulaması:",
              "AE =", sayi(al(CT, 0x02, GET_CUR, 1)),
              " pozlama =", sayi(al(CT, 0x04, GET_CUR, 4)))
    else:
        for birim, sel, n, ad in KONTROLLER:
            print(f"\n{ad}  (unit {birim}, sel {sel})")
            try:
                info = al(birim, sel, GET_INFO, 1)[0]
                print(f"  INFO: 0x{info:02x}  (GET={'evet' if info&1 else 'hayır'}, SET={'evet' if info&2 else 'hayır'})")
            except usb.core.USBError as e:
                print(f"  INFO: cevap yok ({e.strerror}) -> büyük ihtimalle desteklenmiyor")
                continue
            for ad2, q in (("CUR", GET_CUR), ("MIN", GET_MIN), ("MAX", GET_MAX),
                           ("DEF", GET_DEF), ("RES", GET_RES)):
                try:
                    print(f"  {ad2}: {sayi(al(birim, sel, q, n))}")
                except usb.core.USBError as e:
                    print(f"  {ad2}: ({e.strerror})")
finally:
    if ayrildi:
        try:
            usb.util.release_interface(dev, VC_IF)
        except Exception:
            pass
        dev.attach_kernel_driver(VC_IF)
        print("\nuvcvideo sürücüsü geri takıldı.")
