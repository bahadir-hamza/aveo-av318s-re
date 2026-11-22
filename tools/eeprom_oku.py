#!/usr/bin/env python3
"""
Aveo AV318S - register/bellek alanı SALT OKUNUR dökümü
Windows sürücüsündeki doğrulama fonksiyonu (FUN_0002c5d8) şunu kullanıyor:
    vendor istek 0x01, yön IN, wValue=0, wIndex=adres, uzunluk 1

Bu script SADECE bRequest=0x01 IN gönderir. Yazma komutu YOKTUR.
(0x02, 0x03, 0x07, 0x08 kalıcı belleğe yazar - asla gönderme!)

Kurulum : sudo apt install -y python3-usb
Kullanım: sudo python3 eeprom_oku.py [bayt_sayisi] [wValue]
Çıktı   : eeprom.bin + ekrana hexdump. Okunamayan adresler 0x00 yazılır ve listelenir
          (adres kayması olmaz).
"""
import sys, time, usb.core

VID, PID = 0x1871, 0x0F01
OKUMA = 0x01                      # tek izin verilen istek
BOYUT = int(sys.argv[1], 0) if len(sys.argv) > 1 else 1024
SAYFA = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0   # wValue (deneysel: sayfa/bank)

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    sys.exit("Kamera bulunamadı")

def oku(adres):
    assert OKUMA == 0x01          # güvenlik: başka istek gönderilemez
    for _ in range(5):
        r = dev.ctrl_transfer(0xC2, OKUMA, SAYFA, adres, 1, timeout=500)
        if len(r) == 1:
            return r[0]
        time.sleep(0.002)
    return None

veri, okunamayan = bytearray(), []
for adres in range(BOYUT):
    b = oku(adres)
    if b is None:
        okunamayan.append(adres)
        b = 0
    veri.append(b)
    if adres % 128 == 0:
        print(f"\r{adres}/{BOYUT}", end="", flush=True)

open("eeprom.bin", "wb").write(veri)
print(f"\n{len(veri)} bayt -> eeprom.bin (wValue={SAYFA})")
if okunamayan:
    print("Okunamayan adresler:", ", ".join(f"0x{a:03x}" for a in okunamayan))
print()
for i in range(0, len(veri), 16):
    satir = veri[i:i+16]
    asc = "".join(chr(c) if 32 <= c < 127 else "." for c in satir)
    print(f"{i:04x}  {satir.hex(' '):<47}  {asc}")
