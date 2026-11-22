#!/usr/bin/env python3
"""
Aveo AV318S - UVC Extension Unit (XU) SALT OKUNUR sorgulama
Unit 4, GUID {aab8f252-8ed1-4972-8ced-96b17f04408b}, bmControls=0x01 -> selector 1

Hiçbir şey YAZMAZ (SET_CUR kullanılmaz). Sadece GET_* sorguları yapar.
Kullanım: python3 xu_oku.py [/dev/video0]
"""
import ctypes, fcntl, os, sys

DEV = sys.argv[1] if len(sys.argv) > 1 else "/dev/video0"
UNIT = 4
SELECTORS = [1]          # bmControls=0x01 -> sadece selector 1 bildirilmiş
DENE_GIZLI = True        # bildirilmeyen selector 2..16 da (okuma ile) yoklansın mı

class uvc_xu_control_query(ctypes.Structure):
    _fields_ = [("unit", ctypes.c_uint8),
                ("selector", ctypes.c_uint8),
                ("query", ctypes.c_uint8),
                ("size", ctypes.c_uint16),
                ("data", ctypes.POINTER(ctypes.c_uint8))]

def _IOWR(t, nr, size):
    return (3 << 30) | (size << 16) | (ord(t) << 8) | nr

UVCIOC_CTRL_QUERY = _IOWR('u', 0x21, ctypes.sizeof(uvc_xu_control_query))

GET_CUR, GET_MIN, GET_MAX, GET_RES, GET_LEN, GET_INFO, GET_DEF = \
    0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87

def sorgu(fd, sel, q, size):
    buf = (ctypes.c_uint8 * size)()
    req = uvc_xu_control_query(UNIT, sel, q, size,
                               ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8)))
    fcntl.ioctl(fd, UVCIOC_CTRL_QUERY, req)
    return bytes(buf)

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

def incele(fd, sel, sessiz=False):
    try:
        ln = int.from_bytes(sorgu(fd, sel, GET_LEN, 2), "little")
    except OSError as e:
        if not sessiz:
            print(f"  selector {sel}: GET_LEN başarısız ({e.strerror})")
        return
    info = sorgu(fd, sel, GET_INFO, 1)[0]
    bayrak = []
    if info & 1: bayrak.append("GET")
    if info & 2: bayrak.append("SET")
    if info & 4: bayrak.append("otomatik-devre-dışı")
    if info & 8: bayrak.append("otomatik-güncelleme")
    if info & 16: bayrak.append("asenkron")
    print(f"\n=== Selector {sel} ===")
    print(f"  Uzunluk : {ln} bayt")
    print(f"  INFO    : 0x{info:02x} ({', '.join(bayrak) or '-'})")
    for ad, q in [("CUR", GET_CUR), ("MIN", GET_MIN), ("MAX", GET_MAX),
                  ("RES", GET_RES), ("DEF", GET_DEF)]:
        try:
            v = sorgu(fd, sel, q, ln)
            print(f"  {ad:<4}    : {hexs(v)}")
        except OSError as e:
            print(f"  {ad:<4}    : (desteklenmiyor: {e.strerror})")

fd = os.open(DEV, os.O_RDWR)
print(f"Cihaz: {DEV}  Unit: {UNIT}  (ioctl=0x{UVCIOC_CTRL_QUERY:08x})")
for s in SELECTORS:
    incele(fd, s)
if DENE_GIZLI:
    print("\n--- Bildirilmeyen selector'lar yoklanıyor (2..16, sadece okuma) ---")
    for s in range(2, 17):
        incele(fd, s, sessiz=True)
    print("(Yukarıda ek bölüm yoksa gizli selector bulunamadı.)")
os.close(fd)
