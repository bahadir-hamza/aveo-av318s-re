#!/usr/bin/env python3
"""
Aveo AV318S - vendor 0x09 ile bellek dökümü denemesi (SALT OKUNUR)
Komut taramasında 0x09 IN, 64 bayttan fazla veri döndürdü.
Bu script YALNIZCA 0x09'u IN yönünde gönderir. (0x10/0x11 çipi kilitler - kullanma!)

Kullanım:
  sudo python3 bellek_dok.py kesif
      -> blok boyutu, hangi parametrenin (wValue / wIndex) adres olduğunu bulur
  sudo python3 bellek_dok.py dok wvalue 64 1024
  sudo python3 bellek_dok.py dok windex 64 1024
      -> seçilen parametreyi <adim> kadar artırarak en fazla <blok_sayisi> blok okur
         ilk blok tekrar gelirse (başa sarma) durur. Çıktı: bellek_<param>.bin
"""
import sys, hashlib, usb.core

dev = usb.core.find(idVendor=0x1871, idProduct=0x0F01)
if dev is None:
    sys.exit("Kamera bulunamadı (takılı kaldıysa önce fiziksel olarak çıkarıp tak)")

def oku(wvalue=0, windex=0, n=4096):
    return bytes(dev.ctrl_transfer(0xC2, 0x09, wvalue, windex, n, timeout=1000))

def ozet(b):
    asc = "".join(chr(c) if 32 <= c < 127 else "." for c in b[:32])
    return f"{len(b):4d} bayt  md5={hashlib.md5(b).hexdigest()[:8]}  {b[:16].hex(' ')}  {asc}"

mod = sys.argv[1] if len(sys.argv) > 1 else "kesif"

if mod == "kesif":
    taban = oku()
    print("taban (0,0):     ", ozet(taban))
    print("tekrar (0,0):    ", ozet(oku()), " <- aynıysa içerik sabit")
    for v in (1, 0x40, 0x100, 0x1000):
        print(f"wValue=0x{v:04x}:   ", ozet(oku(wvalue=v)))
    for i in (1, 0x40, 0x100, 0x1000):
        print(f"wIndex=0x{i:04x}:   ", ozet(oku(windex=i)))
    open("bellek_taban.bin", "wb").write(taban)
    print("\ntaban blok -> bellek_taban.bin")

elif mod == "dok":
    param, adim, sayi = sys.argv[2], int(sys.argv[3], 0), int(sys.argv[4], 0)
    assert param in ("wvalue", "windex")
    veri, ilk = bytearray(), None
    for k in range(sayi):
        a = k * adim
        b = oku(wvalue=a) if param == "wvalue" else oku(windex=a)
        if ilk is None:
            ilk = b
        elif b == ilk:
            print(f"\nadres 0x{a:04x}: ilk blok tekrar geldi -> başa sardı, duruluyor")
            break
        veri += b
        if k % 32 == 0:
            print(f"\r0x{a:04x}  toplam {len(veri)} bayt", end="", flush=True)
    ad = f"bellek_{param}.bin"
    open(ad, "wb").write(veri)
    print(f"\n{len(veri)} bayt -> {ad}")
