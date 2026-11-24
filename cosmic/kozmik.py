#!/usr/bin/env python3
"""
Kozmik ışın / radyasyon dedektörü - Aveo AV318S USB kamera (OV7725, sensör siyah bantla kapalı)

Kurulum:  sudo apt install -y python3-opencv python3-numpy python3-usb
Çalıştır: python3 kozmik.py                       # sensör otomatik (AGC/AEC açık)
          sudo python3 kozmik.py --mod manuel     # AGC/AEC kapalı, sabit kazanç (pyusb root ister)
          python3 kozmik.py --help
Durdur:   Ctrl+C (ya da SIGTERM)

Mantık:
  1) Isınma kareleri atlanır, KALIBRASYON karede piksel başına karanlık referans (medyan) ve
     gürültü (sigma) çıkarılır. Sıcak pikseller maskelenir (maske.npy'de saklanır).
  2) Her karede işaretli fark = kare - referans. Eşik piksel başına max(--esik, --k * sigma).
  3) Eşiği aşan pikseller kümelere ayrılır (8-komşuluk, 1 piksel boşluk birleştirilir);
     --min-piksel üstü her küme bir olaydır. Önceki karede aynı yerdeki küme "devam" sayılır.
  4) Aynı 4x4 hücrede --tekrar kez olay = sıcak piksel -> kalıcı maskeye eklenir.
  5) Olaysız kareler referansı ve sigma'yı yavaşça günceller (sıcaklık kayması).
  6) Kamera koparsa bekler, yeniden açar, sensör ayarlarını yeniden uygular.

Çıktılar (çalışma dizininde):
  olaylar_v2.csv        her olay bir satır (başlıklı)
  olaylar/olay_*.png    olay çevresi kırpma, kontrastlı ve 4x büyütülmüş
  olaylar/olay_*.npz    ham kırpma (uint8) + işaretli fark (float32) + sigma + meta
  durum.json            canlı durum (her dakika)
  maske.npy             kalıcı sıcak piksel maskesi
"""
import argparse, csv, json, os, signal, sys, time
from datetime import datetime

import cv2
import numpy as np

BY_ID = "/dev/v4l/by-id/usb-AVEO_Technology_Corp._USB2.0_Camera-video-index0"
BILINEN_SICAK = [(639, 322), (0, 465)]   # (x, y) bilinen titreyen pikseller
KIRP = 24                                # olay çevresinde kırpma yarıçapı (piksel)
CSV_ALANLAR = ["zaman", "kare", "piksel", "tepe", "toplam", "cx", "cy",
               "x0", "y0", "w", "h", "mod", "kazanc"]


def argumanlar():
    p = argparse.ArgumentParser(description="Aveo/OV7725 kozmik ışın dedektörü")
    p.add_argument("--cihaz", default=BY_ID if os.path.exists(BY_ID) else "/dev/video0")
    p.add_argument("--mod", choices=["oto", "manuel"], default="oto",
                   help="sensör modu: oto = AGC/AEC açık, manuel = sabit kazanç/pozlama")
    p.add_argument("--kazanc", type=lambda s: int(s, 0), default=0xFF, help="manuel kazanç 0-255")
    p.add_argument("--pozlama", type=lambda s: int(s, 0), default=None,
                   help="manuel pozlama (satır, ör. 0x1f0). Verilmezse dokunulmaz")
    p.add_argument("--brightness", type=int, default=85)
    p.add_argument("--isinma", type=int, default=30, help="atlanacak ilk kare sayısı")
    p.add_argument("--kalibrasyon", type=int, default=100)
    p.add_argument("--esik", type=float, default=25.0, help="mutlak alt eşik (0-255)")
    p.add_argument("--k", type=float, default=8.0, help="sigma katsayısı")
    p.add_argument("--min-piksel", type=int, default=2)
    p.add_argument("--kenar", type=int, default=2,
                   help="maskelenecek sol/sağ kenar sütun sayısı (yüksek kazançta gürültülü)")
    p.add_argument("--isik-limit", type=int, default=2000,
                   help="bir karede bu kadar piksel aşarsa ışık sızıntısı say, olay değil")
    p.add_argument("--tekrar", type=int, default=3, help="aynı hücrede kaç olay = sıcak piksel")
    p.add_argument("--ema", type=float, default=1 / 1800, help="referans güncelleme hızı")
    p.add_argument("--kayit", default="olaylar")
    p.add_argument("--maske", default="maske.npy")
    p.add_argument("--max-kayit-saat", type=int, default=600,
                   help="saatte en fazla kaç olay görüntüsü kaydedilsin (disk koruması)")
    return p.parse_args()


def zaman_damgasi():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def log(msj):
    print(f"{datetime.now():%H:%M:%S} {msj}", flush=True)


class Kamera:
    """Kopmaya dayanıklı V4L2 kamera. Her (yeniden) açılışta sensör ayarlarını uygular."""

    def __init__(self, a):
        self.a = a
        self.cap = None
        self.sensor_manuel = False
        self.slot_yazildi = False
        self.kopma = 0

    def _v4l2(self, ayar):
        os.system(f"v4l2-ctl -d {self.a.cihaz} -c {ayar} >/dev/null 2>&1")

    def _sensor_hazirla(self):
        """Akış başlamadan önce: brightness + sensör modu. Firmware akış başında gamma'yı
        (= slot 8'deki çiftleri) yeniden uygular, bu yüzden ayar burada yapılır."""
        self._v4l2(f"brightness={self.a.brightness}")
        self.sensor_manuel = False
        try:
            import aveo_sensor
            if self.a.mod == "manuel":
                aveo_sensor.manuel_ayarla(self.a.cihaz, self.a.kazanc, self.a.pozlama)
                self.sensor_manuel = True
                pz = "değişmedi" if self.a.pozlama is None else f"0x{self.a.pozlama:x} satır"
                log(f"Sensör MANUEL: AGC/AEC kapalı, kazanç=0x{self.a.kazanc:02x}, pozlama {pz}")
            else:
                # Önceki bir çökme sensörü manuelde bırakmış olabilir: COM8=FF'yi açıkça uygula
                aveo_sensor.oto_ayarla(self.a.cihaz)
            self.slot_yazildi = True
        except Exception as e:  # yetki yok, kamera yok, farklı firmware...
            if self.a.mod == "manuel":
                log(f"UYARI: manuel sensör modu uygulanamadı ({e}) -> otomatik modda devam")
            self._v4l2("gamma=3")

    def ac(self):
        bekle = 2
        while True:
            if os.path.exists(self.a.cihaz):
                self._sensor_hazirla()
                cap = cv2.VideoCapture(self.a.cihaz, cv2.CAP_V4L2)
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))  # sıkıştırmasız
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                if cap.isOpened() and cap.read()[0]:
                    self.cap = cap
                    return
                cap.release()
            log(f"Kamera açılamadı ({self.a.cihaz}), {bekle} sn sonra tekrar...")
            time.sleep(bekle)
            bekle = min(bekle * 2, 60)

    def oku(self):
        """Gri kare (float32). Okuma başarısızsa kamerayı yeniden açar; None = yeniden açıldı."""
        ok, f = self.cap.read()
        if ok:
            return cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        self.kopma += 1
        log("Kare okunamadı -> kamera yeniden açılıyor")
        self.kapat(sensoru_geri_al=False)
        time.sleep(2)
        self.ac()
        return None

    def kapat(self, sensoru_geri_al=True):
        # Sensörü akış sürerken otomatiğe döndür (PU değişikliği hemen uygulanır)
        if sensoru_geri_al and self.slot_yazildi:
            try:
                import aveo_sensor
                ok = aveo_sensor.otomatige_don(self.a.cihaz)
                log("Sensör otomatiğe döndürüldü" if ok else "UYARI: sensör tam geri alınamadı")
            except Exception as e:
                log(f"UYARI: sensör geri alınamadı: {e}")
            self.sensor_manuel = self.slot_yazildi = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class Dedektor:
    def __init__(self, a, kam):
        self.a, self.kam = a, kam
        self.ref = self.var = self.esik = None
        self.maske = None
        self.tekrar = {}
        self.onceki = []          # önceki karedeki küme merkezleri
        self.sayac = self.kare = self.isik = self.devam = 0
        self.saat_kayit, self.saat_bas = 0, time.time()

    # --- kalibrasyon ---
    def _kareler(self, n):
        out = []
        while len(out) < n:
            g = self.kam.oku()
            if g is None:      # kopma oldu, baştan say
                out = []
                continue
            out.append(g)
        return out

    def kalibre_et(self):
        log(f"Isınma: {self.a.isinma} kare atlanıyor...")
        self._kareler(self.a.isinma)
        log(f"Karanlık referans çıkarılıyor ({self.a.kalibrasyon} kare)...")
        k = np.stack(self._kareler(self.a.kalibrasyon))
        self.ref = np.median(k, axis=0)
        sig = k.std(axis=0)
        self.var = np.maximum(sig, 0.5) ** 2
        yeni_sicak = (self.ref > self.ref.mean() + 5 * self.ref.std()) | \
                     (sig > 3 * np.median(sig) + 5)
        self.maske = np.zeros_like(yeni_sicak)
        if os.path.exists(self.a.maske):
            try:
                eski = np.load(self.a.maske)
                if eski.shape == self.maske.shape:
                    self.maske |= eski
            except Exception as e:
                log(f"UYARI: {self.a.maske} okunamadı: {e}")
        self.maske |= yeni_sicak
        for x, y in BILINEN_SICAK:
            self._maskele(x, y)
        if self.a.kenar > 0:
            self.maske[:, :self.a.kenar] = True
            self.maske[:, -self.a.kenar:] = True
        self._esik_guncelle()
        self._maske_kaydet()
        log(f"Referans hazır: ort={self.ref.mean():.2f}, medyan sigma={np.median(sig):.2f}, "
            f"maskeli piksel={int(self.maske.sum())}")

    def _esik_guncelle(self):
        self.esik = np.maximum(self.a.esik, self.a.k * np.sqrt(self.var)).astype(np.float32)

    def _maskele(self, x, y, r=2):
        h, w = self.maske.shape
        self.maske[max(0, y - r):min(h, y + r + 1), max(0, x - r):min(w, x + r + 1)] = True

    def _maske_kaydet(self):
        tmp = self.a.maske + ".tmp.npy"
        np.save(tmp, self.maske)
        os.replace(tmp, self.a.maske)

    # --- ana döngü ---
    def isle(self, g):
        self.kare += 1
        fark = g - self.ref
        fark[self.maske] = 0
        parlak = fark > self.esik
        n = int(parlak.sum())

        if n > self.a.isik_limit:
            self.isik += 1
            if self.isik % 30 == 1:
                log(f"UYARI: {n} piksel eşik üstü -> ışık sızıntısı? (bant/kapak kontrol et)")
            return
        if n < self.a.min_piksel:
            self._referans_guncelle(g, fark)
            self.onceki = []
            return

        # 1 piksel boşlukları birleştirmek için genişletilmiş maskede etiketle
        genis = cv2.dilate(parlak.astype(np.uint8), np.ones((3, 3), np.uint8))
        adet, etiket = cv2.connectedComponents(genis, connectivity=8)
        merkezler = []
        for i in range(1, adet):
            ys, xs = np.nonzero(parlak & (etiket == i))
            if len(xs) < self.a.min_piksel:
                continue
            w = fark[ys, xs]
            cx, cy = float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum())
            merkezler.append((cx, cy))
            if any(abs(cx - px) < 4 and abs(cy - py) < 4 for px, py in self.onceki):
                self.devam += 1          # önceki karedeki izin devamı (afterglow)
                continue
            hucre = (int(cx) // 4, int(cy) // 4)
            self.tekrar[hucre] = self.tekrar.get(hucre, 0) + 1
            if self.tekrar[hucre] >= self.a.tekrar:
                self._maskele(int(cx), int(cy))
                self._esik_guncelle()
                self._maske_kaydet()
                log(f"  -> ({int(cx)},{int(cy)}) tekrar ediyor, sıcak piksel olarak maskelendi")
                continue
            self._olay(g, fark, xs, ys, cx, cy)
        self.onceki = merkezler

    def _referans_guncelle(self, g, fark):
        a = self.a.ema
        self.ref += a * fark * (~self.maske)
        self.var += a * (fark * fark - self.var)
        np.maximum(self.var, 0.25, out=self.var)
        if self.kare % 300 == 0:
            self._esik_guncelle()

    def _olay(self, g, fark, xs, ys, cx, cy):
        self.sayac += 1
        z = zaman_damgasi()
        tepe = float(fark[ys, xs].max())
        toplam = float(fark[ys, xs].sum())
        x0, y0 = int(xs.min()), int(ys.min())
        w, h = int(xs.max()) - x0 + 1, int(ys.max()) - y0 + 1
        kaz = f"0x{self.a.kazanc:02x}" if self.kam.sensor_manuel else "oto"
        mod = "manuel" if self.kam.sensor_manuel else "oto"
        self.csv.writerow({"zaman": z, "kare": self.kare, "piksel": len(xs),
                           "tepe": round(tepe, 1), "toplam": round(toplam, 1),
                           "cx": round(cx, 1), "cy": round(cy, 1), "x0": x0, "y0": y0,
                           "w": w, "h": h, "mod": mod, "kazanc": kaz})
        self.csv_dosya.flush()
        self._kaydet(z, g, fark, int(cx), int(cy), tepe, len(xs))
        dk = self.canli_sure() / 60
        log(f"OLAY #{self.sayac}: {len(xs)} piksel, tepe={tepe:.0f}, toplam={toplam:.0f}, "
            f"konum=({cx:.0f},{cy:.0f}) {w}x{h} | {self.sayac / max(dk, 1e-9):.2f}/dk")

    def _kaydet(self, z, g, fark, cx, cy, tepe, n):
        if time.time() - self.saat_bas > 3600:
            self.saat_bas, self.saat_kayit = time.time(), 0
        if self.saat_kayit >= self.a.max_kayit_saat:
            return
        self.saat_kayit += 1
        H, W = g.shape
        x0, x1 = max(0, cx - KIRP), min(W, cx + KIRP)
        y0, y1 = max(0, cy - KIRP), min(H, cy + KIRP)
        dk = fark[y0:y1, x0:x1]
        np.savez_compressed(f"{self.a.kayit}/olay_{z}.npz",
                            ham=g[y0:y1, x0:x1].astype(np.uint8), fark=dk.astype(np.float32),
                            sigma=np.sqrt(self.var[y0:y1, x0:x1]).astype(np.float32),
                            konum=np.array([x0, y0]), tepe=tepe, piksel=n,
                            mod="manuel" if self.kam.sensor_manuel else "oto",
                            kazanc=self.a.kazanc)
        gorsel = np.clip(dk * (200.0 / max(tepe, 1.0)), 0, 255).astype(np.uint8)
        gorsel = cv2.resize(gorsel, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(f"{self.a.kayit}/olay_{z}.png", gorsel)

    def canli_sure(self):
        return time.time() - self.bas

    def durum_yaz(self, fps):
        d = {"zaman": datetime.now().isoformat(timespec="seconds"),
             "canli_dk": round(self.canli_sure() / 60, 2), "kare": self.kare,
             "fps": round(fps, 2), "olay": self.sayac,
             "olay_dk": round(self.sayac / max(self.canli_sure() / 60, 1e-9), 3),
             "devam_kumesi": self.devam, "isik_karesi": self.isik, "kopma": self.kam.kopma,
             "ref_ort": round(float(self.ref.mean()), 3),
             "sigma_medyan": round(float(np.median(np.sqrt(self.var))), 3),
             "maskeli": int(self.maske.sum()),
             "mod": "manuel" if self.kam.sensor_manuel else "oto",
             "kazanc": self.a.kazanc if self.kam.sensor_manuel else None}
        with open("durum.json.tmp", "w") as f:
            json.dump(d, f, indent=1)
        os.replace("durum.json.tmp", "durum.json")
        return d


def main():
    a = argumanlar()
    os.makedirs(a.kayit, exist_ok=True)
    # SIGTERM'i de Ctrl+C gibi ele al (tmux kill, systemd stop) -> finally'de sensör geri alınır
    def _sigterm(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _sigterm)

    kam = Kamera(a)
    kam.ac()
    det = Dedektor(a, kam)
    yeni = not os.path.exists("olaylar_v2.csv")
    det.csv_dosya = open("olaylar_v2.csv", "a", newline="")
    det.csv = csv.DictWriter(det.csv_dosya, fieldnames=CSV_ALANLAR)
    if yeni:
        det.csv.writeheader()
    try:
        det.kalibre_et()
        det.bas = time.time()
        son_durum, son_kare = time.time(), 0
        log("Dinleniyor... (Ctrl+C ile çık)")
        while True:
            g = kam.oku()
            if g is None:        # yeniden bağlandı: sensör/ışık değişmiş olabilir
                det.kalibre_et()
                continue
            det.isle(g)
            if time.time() - son_durum >= 60:
                fps = (det.kare - son_kare) / (time.time() - son_durum)
                d = det.durum_yaz(fps)
                log(f"... {d['canli_dk']:.1f} dk, {det.kare} kare, {fps:.1f} fps, "
                    f"{det.sayac} olay ({d['olay_dk']}/dk), ref={d['ref_ort']}, "
                    f"sigma={d['sigma_medyan']}, mod={d['mod']}")
                son_durum, son_kare = time.time(), det.kare
    except KeyboardInterrupt:
        pass
    finally:
        if det.ref is not None and hasattr(det, "bas"):
            det.durum_yaz(0)
            dk = det.canli_sure() / 60
            log(f"Bitti: {dk:.1f} dk, {det.sayac} olay ({det.sayac / max(dk, 1e-9):.2f}/dk), "
                f"{det.isik} ışık karesi, {kam.kopma} kopma")
        kam.kapat()
        det.csv_dosya.close()


if __name__ == "__main__":
    main()
