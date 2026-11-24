#!/usr/bin/env python3
"""
Seyrek kayıt: her karede referansın --esik üstündeki pikselleri (kare, y, x, fark) kaydeder.
Eşik / küme / RTS kurallarını çevrimdışı ayarlamak için (tools/seyrek_analiz.py).
Kullanım: sudo python3 seyrek_kayit.py ad --sure 180 "ac=9f 8e=00 8f=00 64=e0 46=04 13=fa 00=ff"
Çıktı: seyrek_<ad>.npz  (ref, sigma, f/y/x/d dizileri, kare sayısı, fps)
"""
import sys, os, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cosmic"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2, numpy as np, aveo_sensor as S
ap = argparse.ArgumentParser()
ap.add_argument("ad"); ap.add_argument("ciftler")
ap.add_argument("--sure", type=float, default=180); ap.add_argument("--esik", type=float, default=10)
a = ap.parse_args()
CIHAZ = "/dev/video0"
S.slot8_yaz([tuple(int(x, 16) for x in c.split("=")) for c in a.ciftler.split()])
S._gamma(CIHAZ, 3); S._gamma(CIHAZ, 8)
cap = cv2.VideoCapture(CIHAZ, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV")); cap.set(3, 640); cap.set(4, 480)
cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
def y():
    ok, f = cap.read(); assert ok; return f[:, :, 0].astype(np.int16)
try:
    for _ in range(30): y()
    k = np.stack([y() for _ in range(150)])
    ref = np.median(k, 0).astype(np.int16); sig = k.std(0).astype(np.float32); del k
    F, Yy, X, D = [], [], [], []; n = 0; t0 = time.time()
    while time.time() - t0 < a.sure:
        d = y() - ref; yy, xx = np.nonzero(d > a.esik)
        F.append(np.full(len(yy), n, np.int32)); Yy.append(yy.astype(np.int16))
        X.append(xx.astype(np.int16)); D.append(d[yy, xx].astype(np.int16)); n += 1
    fps = n / (time.time() - t0)
finally:
    cap.release()
    S.otomatige_don(CIHAZ)
np.savez_compressed(f"seyrek_{a.ad}.npz", ref=ref, sigma=sig, f=np.concatenate(F), y=np.concatenate(Yy),
                    x=np.concatenate(X), d=np.concatenate(D), kare=n, fps=fps)
print(f"{a.ad}: {n} kare, {fps:.1f} fps, {sum(map(len, F))} piksel kaydı, medyan sigma {np.median(sig):.2f}")
