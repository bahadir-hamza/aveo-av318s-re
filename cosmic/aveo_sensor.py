#!/usr/bin/env python3
"""
Aveo AV318S + OV7725: firmware'deki gamma tablosu üzerinden sensör register yazma.

Yöntem (docs/firmware.md):
  - Aktif firmware, UVC gamma = v ayarlandığında XDATA 0xA66A + 32*v adresindeki
    16 (register, değer) çiftini OV7725'e yazar. Akış başlarken de tüm PU değerlerini
    (gamma dahil) yeniden uygular.
  - Vendor 0x00 OUT (wValue=değer, wIndex=XDATA adresi) RAM'e yazabilir.
  - Gamma slot 8'i (0xA76A) kendi çiftlerimizle doldurup gamma=8 seçince firmware bunları
    sensöre yazar. Kamera çıkarılıp takılınca her şey sıfırlanır (RAM).

Slot 8 = varsayılan gamma eğrisi (v=3 tablosu, init tablosuyla aynı) + sonda bizim çiftler,
böylece görüntünün gamma'sı değişmez.

pyusb root yetkisi ister (sudo ya da 1871:0f01 için udev kuralı).
"""
import subprocess
import usb.core

VID, PID = 0x1871, 0x0F01
SLOT8 = 0xA76A
SLOT3 = 0xA6CA
# Firmware'in orijinal içerikleri (24 Kas 2026 dökümü)
ORIG_SLOT8 = bytes.fromhex("7e147f2d805081778285839684a285ad86b987c488d289de8ae78be88ce88d20")
ORIG_SLOT3 = bytes.fromhex("7e0c7f16802a814e8261836f847b8586868e879788a489af8ac58bd78ce88d20")

# OV7725 register'ları
COM8, GAIN, AECH, AEC = 0x13, 0x00, 0x08, 0x10
COM8_OTO = 0xFF      # AGC + AEC + AWB otomatik (init tablosunun son değeri)
COM8_MANUEL = 0xFA   # AGC kapalı, AEC kapalı, AWB açık


class SensorHatasi(Exception):
    pass


def _cihaz():
    try:
        dev = usb.core.find(idVendor=VID, idProduct=PID)
    except usb.core.NoBackendError as e:
        raise SensorHatasi(f"libusb yok: {e}")
    if dev is None:
        raise SensorHatasi("kamera USB'de bulunamadı")
    return dev


def _oku(dev, adr):
    for _ in range(5):
        b = bytes(dev.ctrl_transfer(0xC2, 0x01, 0, adr, 1, timeout=1000))
        if b:
            return b[0]
    raise SensorHatasi(f"XDATA okunamadı 0x{adr:04x}")


def _blok(dev, adr, n):
    return bytes(_oku(dev, adr + i) for i in range(n))


def _yaz(dev, adr, deger):
    dev.ctrl_transfer(0x42, 0x00, deger, adr, None, timeout=1000)


def _gamma(cihaz_yolu, v):
    subprocess.run(["v4l2-ctl", "-d", cihaz_yolu, "-c", f"gamma={v}"],
                   check=True, capture_output=True)


def slot8_yaz(ciftler):
    """Slot 8'i (varsayılan gamma çiftleri + verilen çiftler) ile doldurur. En fazla 16 çift."""
    if not 1 <= len(ciftler) <= 16:
        raise ValueError("1-16 çift olmalı")
    try:
        dev = _cihaz()
        if _blok(dev, SLOT3, 32) != ORIG_SLOT3:
            raise SensorHatasi("gamma slot 3 beklenen içerikte değil -> farklı firmware? yazılmadı")
        mevcut = _blok(dev, SLOT8, 32)
        # Slot 8 ya orijinal olmalı ya da daha önce bizim yazdığımız (v3 tabanlı) içerik
        if mevcut != ORIG_SLOT8 and mevcut[:8] != ORIG_SLOT3[:8]:
            raise SensorHatasi(f"slot 8 tanınmayan içerikte ({mevcut.hex()}) -> yazılmadı")
        yeni = bytearray(ORIG_SLOT3)
        for k, (r, d) in enumerate(ciftler):
            j = 16 - len(ciftler) + k
            yeni[2 * j], yeni[2 * j + 1] = r, d
        for i in range(32):
            if mevcut[i] != yeni[i]:
                _yaz(dev, SLOT8 + i, yeni[i])
        if _blok(dev, SLOT8, 32) != bytes(yeni):
            raise SensorHatasi("slot 8 doğrulanamadı")
    except usb.core.USBError as e:
        raise SensorHatasi(f"USB hatası: {e} (root yetkisi / udev kuralı gerekli olabilir)")


def slot8_geri_al():
    try:
        dev = _cihaz()
        mevcut = _blok(dev, SLOT8, 32)
        for i in range(32):
            if mevcut[i] != ORIG_SLOT8[i]:
                _yaz(dev, SLOT8 + i, ORIG_SLOT8[i])
        return _blok(dev, SLOT8, 32) == ORIG_SLOT8
    except (usb.core.USBError, SensorHatasi):
        return False


def manuel_ayarla(cihaz_yolu, kazanc, pozlama=None):
    """AGC/AEC kapalı, sabit kazanç (0-255) ve isteğe bağlı sabit pozlama (satır, 0-0xFFFF).
    Akış başlamadan ÖNCE çağrılmalı: firmware akış başında gamma'yı (=bizim çiftleri) uygular."""
    ciftler = [(COM8, COM8_MANUEL), (GAIN, kazanc & 0xFF)]
    if pozlama is not None:
        ciftler += [(AECH, (pozlama >> 8) & 0xFF), (AEC, pozlama & 0xFF)]
    slot8_yaz(ciftler)
    _gamma(cihaz_yolu, 3)       # değişiklik olsun diye önce 3, sonra 8
    _gamma(cihaz_yolu, 8)


def oto_ayarla(cihaz_yolu):
    """Slot 8 = varsayılan gamma + COM8=FF, gamma=8: akış başında AGC/AEC kesin otomatik olur.
    Görüntü normal otomatik moddan farksızdır (gamma eğrisi aynı)."""
    slot8_yaz([(COM8, COM8_OTO)])
    _gamma(cihaz_yolu, 3)
    _gamma(cihaz_yolu, 8)


def otomatige_don(cihaz_yolu):
    """COM8'i otomatiğe al, slot 8'i orijinale döndür, gamma=3. Hata olursa False."""
    ok = True
    try:
        slot8_yaz([(COM8, COM8_OTO)])
        _gamma(cihaz_yolu, 3)
        _gamma(cihaz_yolu, 8)   # COM8=FF yazılsın
    except (SensorHatasi, subprocess.CalledProcessError):
        ok = False
    try:
        _gamma(cihaz_yolu, 3)
    except subprocess.CalledProcessError:
        ok = False
    return slot8_geri_al() and ok
