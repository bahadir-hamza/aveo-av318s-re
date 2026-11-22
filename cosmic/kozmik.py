#!/usr/bin/env python3
"""
Kozmik ışın / radyasyon dedektörü - Aveo USB webcam (sensör siyah bantla kapalı)

Kurulum:  sudo apt install -y python3-opencv python3-numpy
Çalıştır: python3 kozmik.py
Durdur:   Ctrl+C

Mantık:
  1) İlk N karede "karanlık referans" (dark frame) çıkarılır -> sıcak pikseller elenir.
  2) Sonraki her karede referanstan belirgin şekilde parlak piksel kümesi varsa
     bu bir "olay" (muhtemel parçacık izi) sayılır, kare kaydedilir, loglanır.
"""
import cv2, numpy as np, time, os, csv
from datetime import datetime

CIHAZ = 0            # /dev/video0
KALIBRASYON = 100    # karanlık referans için kare sayısı
ESIK = 40            # referansın kaç birim üstü "olay" sayılsın (0-255)
MIN_PIKSEL = 2       # en az kaç piksel eşiği aşmalı (tekil gürültüyü eler)
KAYIT = "olaylar"

os.makedirs(KAYIT, exist_ok=True)
cap = cv2.VideoCapture(CIHAZ, cv2.CAP_V4L2)
# Sıkıştırmasız format (YUYV) iste: MJPEG küçük izleri bozabilir
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def gri():
    ok, f = cap.read()
    if not ok:
        raise SystemExit("Kare okunamadı - kamera bağlı mı?")
    return cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)

print("Otomatik pozlama otursun diye 30 kare atlanıyor...")
for _ in range(30):
    gri()

print(f"Karanlık referans çıkarılıyor ({KALIBRASYON} kare)...")
kareler = np.stack([gri() for _ in range(KALIBRASYON)])
ref = np.median(kareler, axis=0)
sigma = kareler.std(axis=0)
# Sürekli parlayan (sıcak) pikselleri maskele
sicak = (ref > ref.mean() + 5 * ref.std()) | (sigma > 3 * np.median(sigma) + 5)
print(f"Referans hazır. Ort. seviye={ref.mean():.1f}, maskelenen sıcak piksel={int(sicak.sum())}")

log = open("olaylar.csv", "a", newline="")
yaz = csv.writer(log)
sayac, kare_no, bas = 0, 0, time.time()
print("Dinleniyor... (Ctrl+C ile çık)")
try:
    while True:
        g = gri(); kare_no += 1
        fark = g - ref
        fark[sicak] = 0
        parlak = fark > ESIK
        n = int(parlak.sum())
        if n >= MIN_PIKSEL:
            sayac += 1
            zaman = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            enparlak = float(fark.max())
            ys, xs = np.nonzero(parlak)
            # Kareyi kontrastı artırarak kaydet
            gorsel = np.clip(fark * 4, 0, 255).astype(np.uint8)
            cv2.imwrite(f"{KAYIT}/olay_{zaman}.png", gorsel)
            yaz.writerow([zaman, n, round(enparlak, 1), int(xs.mean()), int(ys.mean())])
            log.flush()
            dk = (time.time() - bas) / 60
            print(f"[{zaman}] OLAY #{sayac}: {n} piksel, tepe={enparlak:.0f}, "
                  f"konum=({int(xs.mean())},{int(ys.mean())})  | {sayac/dk:.2f} olay/dk")
        if kare_no % 1800 == 0:  # ~her dakika (30 fps varsayımı)
            dk = (time.time() - bas) / 60
            print(f"... {dk:.1f} dk, {kare_no} kare, {sayac} olay")
except KeyboardInterrupt:
    dk = (time.time() - bas) / 60
    print(f"\nBitti: {dk:.1f} dakikada {sayac} olay ({sayac/max(dk,1e-9):.2f}/dk)")
finally:
    cap.release(); log.close()
