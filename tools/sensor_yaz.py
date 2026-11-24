#!/usr/bin/env python3
# OV7725 sensör yazma, gamma slot 8 üzerinden (kullanıcı onaylı, 24 Kas 2026)
# Kullanım: sudo python3 sensor_yaz.py "a6=46" ["13=fa 00=00 ..."]   (en fazla 16 çift)
#  - slot 8 (0xA76A, 16 çift) orijinali doğrulanır, sondaki çiftler verilenlerle değiştirilir
#  - gamma=8 ayarlanır, akış başlatılır (firmware PU değerlerini yeniden uygular), ölçülür
#  - finally: slot 8 orijinaline döner, gamma=3
import sys, time, subprocess, usb.core, cv2, numpy as np
SLOT = 0xA76A
ORIG = bytes.fromhex("7e147f2d805081778285839684a285ad86b987c488d289de8ae78be88ce88d20")
dev = usb.core.find(idVendor=0x1871, idProduct=0x0F01)
def rd(a):
    for _ in range(5):
        b = bytes(dev.ctrl_transfer(0xC2, 0x01, 0, a, 1, timeout=1000))
        if b: return b[0]
    raise RuntimeError(f"okuma yok {a:04x}")
def wr(a, v): dev.ctrl_transfer(0x42, 0x00, v, a, None, timeout=1000)
def slot(): return bytes(rd(SLOT + i) for i in range(32))
def yaz_slot(b):
    cur = slot()
    for i in range(32):
        if cur[i] != b[i]: wr(SLOT + i, b[i])
    assert slot() == b, "slot doğrulanamadı"
def gamma(v): subprocess.run(["v4l2-ctl", "-d", "/dev/video0", "-c", f"gamma={v}"], check=True)
def olc(et, n=10):
    cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    for _ in range(20): cap.read()
    fr = []
    for _ in range(n):
        ok, f = cap.read()
        if ok: fr.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    a = np.stack(fr); m = a.mean(0)
    print(f"{et:28s} ortalama={a.mean():6.2f}  std(piksel)={a.std(0).mean():5.2f}  "
          f"std(uzay)={m.std():5.2f}  max={a.max():5.0f}  >40 piksel={int((a>40).sum()/len(fr))}", flush=True)
    return a.mean()
if __name__ == "__main__":
    s0 = slot()
    if s0 != ORIG: sys.exit(f"slot 8 beklenenden farklı: {s0.hex()} -> hiçbir şey yazılmadı")
    deneyler = sys.argv[1:]
    try:
        gamma(3); olc("taban (gamma=3)")
        gamma(8); olc("orijinal slot8 (gamma=8)")
        for d in deneyler:
            pairs = [tuple(int(x, 16) for x in p.split("=")) for p in d.split()]
            assert 1 <= len(pairs) <= 16
            b = bytearray(ORIG)
            for k, (r, v) in enumerate(pairs):
                j = 16 - len(pairs) + k; b[2*j] = r; b[2*j+1] = v
            gamma(3); yaz_slot(bytes(b)); gamma(8)
            olc(d)
    finally:
        gamma(3)
        yaz_slot(ORIG)
        print("geri yüklendi: slot8 =", slot() == ORIG, " ID:", bytes(dev.ctrl_transfer(0xC2, 0x02, 0, 0, 64, timeout=1000))[:4])
