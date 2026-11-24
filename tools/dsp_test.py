#!/usr/bin/env python3
"""
OV7725 DSP aşamalarını kapatma testi (gamma slot 8 üzerinden, cosmic/aveo_sensor.py).
Y kanalı ham YUYV'den doğrudan okunur (OpenCV renk dönüşümü yok).

Her deney: sensör çiftleri uygulanır -> akış açılır -> 30 kare ısınma -> 60 kare referans
(medyan, sigma) -> --sure saniye boyunca referansın max(esik, 6*sigma) üstüne çıkan
GEÇİCİ pikseller sayılır (referansta zaten parlak olanlar hariç).
  tekil  = komşusu eşik altında olan tek piksel (WPC'nin sildiği tür)
  kume   = 2+ piksellik kümeler
Kullanım: sudo python3 dsp_test.py --sure 20 "13=fa 00=ff" "13=fa 00=ff 64=fe" ...
Son adımda her zaman 64=ff 46=05 13=ff (init değerleri) uygulanır ve slot 8 geri alınır.
"""
import sys, os, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cosmic"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2, numpy as np
import aveo_sensor as S

CIHAZ = "/dev/video0"
ap = argparse.ArgumentParser()
ap.add_argument("--sure", type=float, default=20)
ap.add_argument("--esik", type=float, default=15)
ap.add_argument("--k", type=float, default=6)
ap.add_argument("--kaydet", default=None, help="her deneyin bir ham Y karesini .npy olarak kaydet")
ap.add_argument("deneyler", nargs="+")
a = ap.parse_args()

def ac():
    cap = cv2.VideoCapture(CIHAZ, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    cap.set(3, 640); cap.set(4, 480)
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    return cap

def y(cap):
    ok, f = cap.read()
    if not ok: raise RuntimeError("kare yok")
    return f[:, :, 0].astype(np.float32)

def deney(ad, ciftler):
    S.slot8_yaz(ciftler); S._gamma(CIHAZ, 3); S._gamma(CIHAZ, 8)
    cap = ac()
    try:
        for _ in range(30): y(cap)
        k = np.stack([y(cap) for _ in range(60)])
        ref = np.median(k, 0); sig = k.std(0)
        esik = np.maximum(a.esik, a.k * np.maximum(sig, 0.5))
        sicak = ref > ref.mean() + 6 * max(ref.std(), 1)
        tekil = kume = n = 0; t0 = time.time(); sayim = np.zeros(ref.shape, np.int32)
        while time.time() - t0 < a.sure:
            g = y(cap); n += 1
            p = ((g - ref) > esik) & ~sicak
            if not p.any(): continue
            sayim += p
            komsu = cv2.filter2D(p.astype(np.uint8), -1, np.ones((3, 3), np.float32)) - p
            tekil += int((p & (komsu == 0)).sum())
            adet, _ = cv2.connectedComponents((p & (komsu > 0)).astype(np.uint8), connectivity=8)
            kume += adet - 1
        fps = n / (time.time() - t0)
        if a.kaydet: np.save(f"{a.kaydet}_{ad.replace(' ', '_').replace('=', '')}.npy", g.astype(np.uint8))
        print(f"{ad:32s} fps={fps:4.1f} ort={ref.mean():6.2f} sigma={np.median(sig):5.2f} "
              f"sicak={int(sicak.sum()):5d} tekil/dk={tekil / n * fps * 60:8.1f} "
              f"kume/dk={kume / n * fps * 60:7.1f}", flush=True)
        top = int(sayim.sum()); bir = int((sayim == 1).sum()); cok = sayim[sayim >= 2]
        print(f"{'':32s} konum: {top} piksel-olay, {int((sayim>0).sum())} farklı piksel, "
              f"tek seferlik={bir} ({100*bir/max(top,1):.0f}%), >=2 kez: {len(cok)} piksel "
              f"({int(cok.sum())} olay), en çok={int(sayim.max())}", flush=True)
    finally:
        cap.release()

try:
    for d in a.deneyler:
        deney(d, [tuple(int(x, 16) for x in c.split("=")) for c in d.split()])
finally:
    S.slot8_yaz([(0x64, 0xFF), (0x46, 0x05), (0x13, 0xFF)])
    S._gamma(CIHAZ, 3); S._gamma(CIHAZ, 8)
    c = ac(); [c.read() for _ in range(10)]; c.release()     # init değerleri sensöre gitsin
    print("geri alındı:", S.otomatige_don(CIHAZ))
