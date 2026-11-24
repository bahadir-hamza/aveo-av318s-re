#!/usr/bin/env python3
"""Sensör çiftlerini uygula, ham YUYV baytlarını (CONVERT_RGB=0) kaydet ve yapısını özetle.
Kullanım: sudo python3 ham_kare.py ad "12=02 13=fa 00=ff"   -> ham_<ad>.npy (N x 480 x 640 x 2)"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cosmic"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2, numpy as np, aveo_sensor as S
CIHAZ = "/dev/video0"
ad, ciftler = sys.argv[1], [tuple(int(x, 16) for x in c.split("=")) for c in sys.argv[2].split()]
S.slot8_yaz(ciftler); S._gamma(CIHAZ, 3); S._gamma(CIHAZ, 8)
cap = cv2.VideoCapture(CIHAZ, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV")); cap.set(3, 640); cap.set(4, 480)
cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
kar, t0, hata = [], time.time(), 0
while len(kar) < 40 and time.time() - t0 < 15:
    ok, f = cap.read()
    if ok: kar.append(f.copy())
    else: hata += 1
dt = time.time() - t0
cap.release()
print(f"{ad}: {len(kar)} kare, {hata} hata, {len(kar)/dt:.1f} fps")
if kar:
    a = np.stack(kar[10:] or kar); np.save(f"ham_{ad}.npy", a)
    Y, C = a[..., 0].astype(np.float32), a[..., 1].astype(np.float32)
    print(f"  Y ort={Y.mean():.2f} std(zaman)={Y.std(0).mean():.2f}  C ort={C.mean():.2f} std={C.std(0).mean():.2f}")
    m = Y.mean(0)
    print("  Y 2x2 faz ortalamaları:", [round(float(m[i::2, j::2].mean()), 2) for i in (0, 1) for j in (0, 1)])
    print("  Y satır ort. (ilk 8):", np.round(m.mean(1)[:8], 1).tolist(), " son:", round(float(m.mean(1)[-1]), 1))
    print("  Y sütun ort. 0-8:", np.round(m.mean(0)[:8], 1).tolist(), " 320-328:", np.round(m.mean(0)[320:328], 1).tolist())
    b = a[-1].reshape(-1)
    print("  ham bayt başı:", b[:16].tolist())
