#!/usr/bin/env python3
"""
Kozmik ışın / radyasyon dedektörü - Aveo AV318S USB kamera (OV7725, sensör siyah bantla kapalı)

Kurulum:  sudo apt install -y python3-opencv python3-numpy python3-usb
Çalıştır: python3 kozmik.py                       # sensör otomatik (AGC/AEC açık)
          sudo python3 kozmik.py --mod manuel     # AGC/AEC kapalı, sabit kazanç, DSP kapalı (ham)
                                                  # (pyusb root ister; --no-ham = DSP açık)
          python3 kozmik.py --help
Durdur:   Ctrl+C (ya da SIGTERM)

Mantık:
  1) Isınma kareleri atlanır, KALIBRASYON karede piksel başına karanlık referans (medyan) ve
     gürültü (sigma) çıkarılır. Sıcak pikseller maskelenir (maske.npy'de saklanır).
  2) Her karede işaretli fark = kare - referans. İki eşik: alt (küme pikseli) ve tepe.
  3) Alt eşiği aşan pikseller 8-komşulukla kümelenir; >= --min-piksel pikselli ve tepesi eşiği
     aşan küme olaydır. Önceki karede aynı yerdeki küme "devam" sayılır.
  4) Geçmiş olayların (olaylar_v2.csv, yeniden başlatmalarda da) --tekrar-r piksel yakınında
     yeni olay = kusurlu piksel: satır 'tekrar' sütunuyla işaretlenir; o noktada toplam olay
     --tekrar'a ulaşınca kalıcı maskeye eklenir. (Eski 4x4 hücre sınırı aynı pikseli bölebiliyordu.)
     Gürültü hızı: her pikselin alt eşiği kaç kez aştığı sayılır; dakikada --gurultu-hiz'dan sık
     aşan (RTS / kalın kuyruklu) piksel içeren küme reddedilir. İlk --ogrenme saniye sadece sayılır.
  5) Olaysız kareler referansı ve sigma'yı yavaşça günceller (sıcaklık kayması).
  6) Kamera koparsa bekler, yeniden açar, sensör ayarlarını yeniden uygular.

Çıktılar (çalışma dizininde):
  olaylar_v2.csv        her olay bir satır (başlıklı)
  olaylar/olay_*.png    olay çevresi kırpma, kontrastlı ve 4x büyütülmüş
  olaylar/olay_*.npz    ham kırpma (Y, uint8) + işaretli fark (float32) + sigma + meta
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
               "x0", "y0", "w", "h", "mod", "kazanc", "tekrar"]
CSV_YOL = "olaylar_v2.csv"


def argumanlar():
    p = argparse.ArgumentParser(description="Aveo/OV7725 kozmik ışın dedektörü")
    p.add_argument("--cihaz", default=BY_ID if os.path.exists(BY_ID) else "/dev/video0")
    p.add_argument("--mod", choices=["oto", "manuel"], default="oto",
                   help="sensör modu: oto = AGC/AEC açık, manuel = sabit kazanç/pozlama")
    p.add_argument("--kazanc", type=lambda s: int(s, 0), default=0xFF, help="manuel kazanç 0-255")
    p.add_argument("--pozlama", type=lambda s: int(s, 0), default=None,
                   help="manuel pozlama (satır, ör. 0x1f0). Verilmezse dokunulmaz")
    p.add_argument("--ham", action=argparse.BooleanOptionalAction, default=True,
                   help="manuel modda OV7725 DSP işlemesini (denoise, piksel düzeltme, gamma, "
                        "interpolasyon...) kapat -> piksel başına bağımsız ham veri")
    p.add_argument("--brightness", type=int, default=85)
    p.add_argument("--isinma", type=int, default=30, help="atlanacak ilk kare sayısı")
    p.add_argument("--kalibrasyon", type=int, default=300)
    p.add_argument("--esik", type=float, default=40.0,
                   help="küme tepe eşiği (mutlak, Y birimi); piksel başına max(bu, --k * sigma)")
    p.add_argument("--k", type=float, default=8.0, help="tepe eşiği sigma katsayısı")
    p.add_argument("--alt-esik", type=float, default=20.0,
                   help="küme piksel eşiği (mutlak); piksel başına max(bu, --alt-k * sigma)")
    p.add_argument("--alt-k", type=float, default=6.0)
    p.add_argument("--min-piksel", type=int, default=2,
                   help="kümede en az kaç komşu piksel (ham modda tek piksel gürültüden ayrılamaz)")
    p.add_argument("--kenar", type=int, default=2,
                   help="maskelenecek sol/sağ kenar sütun sayısı (yüksek kazançta gürültülü)")
    p.add_argument("--isik-limit", type=int, default=2000,
                   help="bir karede bu kadar piksel aşarsa ışık sızıntısı say, olay değil")
    p.add_argument("--tekrar", type=int, default=2,
                   help="aynı noktada (--tekrar-r içinde) kaç olay = kusurlu piksel -> maskele")
    p.add_argument("--tekrar-r", type=float, default=3.0, help="tekrar yarıçapı (piksel)")
    p.add_argument("--gurultu-hiz", type=float, default=3.0,
                   help="alt eşiği dakikada bu kadardan sık aşan piksel 'gürültülü': içeren küme reddedilir")
    p.add_argument("--gurultu-min", type=int, default=3, help="gürültülü sayılmak için en az aşım")
    p.add_argument("--ogrenme", type=float, default=120,
                   help="kalibrasyondan sonra kaç saniye sadece gürültü istatistiği toplansın")
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
                aveo_sensor.manuel_ayarla(self.a.cihaz, self.a.kazanc, self.a.pozlama, self.a.ham)
                self.sensor_manuel = True
                pz = "değişmedi" if self.a.pozlama is None else f"0x{self.a.pozlama:x} satır"
                log(f"Sensör MANUEL: AGC/AEC kapalı, kazanç=0x{self.a.kazanc:02x}, pozlama {pz}"
                    + (", HAM (DSP kapalı)" if self.a.ham else ""))
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
                cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)   # ham YUYV: Y doğrudan, dönüşüm yok
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
        if ok and f.ndim == 3 and f.shape[2] == 2:
            return f[:, :, 0].astype(np.float32)          # Y kanalı (siyah ~16-23, kırpılmaz)
        if ok:
            log(f"UYARI: beklenmeyen kare biçimi {f.shape}")
        self.kopma += 1
        log("Kare okunamadı -> kamera yeniden açılıyor")
        self.kapat(sensoru_geri_al=False)
        time.sleep(2)
        self.ac()
        return None

    def mod_adi(self):
        if not self.sensor_manuel:
            return "oto"
        return "manuel-ham" if self.a.ham else "manuel"

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
        self.ref = self.var = self.esik = self.alt_esik = None
        self.sayim = None         # piksel başına alt eşik aşım sayısı (gürültü hızı)
        self.kalib_zaman = time.time()
        self.veto = self.ogrenme_atlanan = 0
        self.rastlanti = 0.0      # beklenen rastlantısal küme sayısı (bağımsız gürültü varsayımı)
        self.maske = None
        self.gecmis = []          # (cx, cy) tüm geçmiş olaylar (CSV'den + bu çalışma)
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
        del k
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
        for x, y in self.tekrar_noktalari():
            self._maskele(int(round(x)), int(round(y)))
        for x, y in BILINEN_SICAK:
            self._maskele(x, y)
        if self.a.kenar > 0:
            self.maske[:, :self.a.kenar] = True
            self.maske[:, -self.a.kenar:] = True
        self.sayim = np.zeros(self.ref.shape, np.uint32)
        self.kalib_zaman = time.time()
        self._esik_guncelle()
        self._maske_kaydet()
        log(f"Referans hazır: ort={self.ref.mean():.2f}, medyan sigma={np.median(sig):.2f}, "
            f"maskeli piksel={int(self.maske.sum())}; {self.a.ogrenme:.0f} sn gürültü öğrenme")

    def _esik_guncelle(self):
        sd = np.sqrt(self.var)
        self.esik = np.maximum(self.a.esik, self.a.k * sd).astype(np.float32)
        self.alt_esik = np.maximum(self.a.alt_esik, self.a.alt_k * sd).astype(np.float32)

    def _maskele(self, x, y, r=2):
        h, w = self.maske.shape
        self.maske[max(0, y - r):min(h, y + r + 1), max(0, x - r):min(w, x + r + 1)] = True

    def _maske_kaydet(self):
        tmp = self.a.maske + ".tmp.npy"
        np.save(tmp, self.maske)
        os.replace(tmp, self.a.maske)

    # --- ana döngü ---
    def gurultu_limiti(self):
        dk = (time.time() - self.kalib_zaman) / 60
        return max(self.a.gurultu_min, self.a.gurultu_hiz * dk)

    def isle(self, g):
        """Olay = alt eşiği aşan >= --min-piksel komşu pikselden oluşan, tepesi eşiği aşan,
        gürültülü piksel içermeyen küme (ölçüm: docs/firmware.md, 'Event selection')."""
        self.kare += 1
        fark = g - self.ref
        fark[self.maske] = 0
        alt = fark > self.alt_esik
        parlak = fark > self.esik
        n = int(np.count_nonzero(parlak))
        if n:
            # bağımsız gürültüde bir tepe pikselinin 8 komşusundan birinin alt eşiği aşma olasılığı
            self.rastlanti += n * 8 * np.count_nonzero(alt) / alt.size

        if n > self.a.isik_limit:
            self.isik += 1
            if self.isik % 30 == 1:
                log(f"UYARI: {n} piksel eşik üstü -> ışık sızıntısı? (bant/kapak kontrol et)")
            return
        if n == 0:
            np.add(self.sayim, alt, out=self.sayim, casting="unsafe")
            self._referans_guncelle(g, fark)
            self.onceki = []
            return

        adet, etiket, stat, _ = cv2.connectedComponentsWithStats(alt.astype(np.uint8), connectivity=8)
        tohum = np.unique(etiket[parlak])
        limit = self.gurultu_limiti()
        ogrenme = time.time() - self.kalib_zaman < self.a.ogrenme
        merkezler = []
        for i in tohum[tohum > 0]:
            if stat[i, cv2.CC_STAT_AREA] < self.a.min_piksel:
                continue
            x0, y0 = stat[i, cv2.CC_STAT_LEFT], stat[i, cv2.CC_STAT_TOP]
            w, h = stat[i, cv2.CC_STAT_WIDTH], stat[i, cv2.CC_STAT_HEIGHT]
            ys, xs = np.nonzero(etiket[y0:y0 + h, x0:x0 + w] == i)
            ys, xs = ys + y0, xs + x0
            wt = fark[ys, xs]
            cx, cy = float((xs * wt).sum() / wt.sum()), float((ys * wt).sum() / wt.sum())
            merkezler.append((cx, cy))
            if self.sayim[ys, xs].max() >= limit:     # sık sıçrayan (RTS) piksel içeriyor
                self.veto += 1
                continue
            if ogrenme:
                self.ogrenme_atlanan += 1
                continue
            if any(abs(cx - px) < 4 and abs(cy - py) < 4 for px, py in self.onceki):
                self.devam += 1          # önceki karedeki izin devamı (afterglow)
                continue
            onceki_olay = self.yakindaki(cx, cy)
            self._olay(g, fark, xs, ys, cx, cy, len(onceki_olay))
            if len(onceki_olay) + 1 >= self.a.tekrar:
                for px, py in onceki_olay + [(cx, cy)]:
                    self._maskele(int(round(px)), int(round(py)))
                self._maske_kaydet()
                log(f"  -> ({cx:.0f},{cy:.0f}) {len(onceki_olay) + 1}. kez: kusurlu piksel, maskelendi")
        np.add(self.sayim, alt, out=self.sayim, casting="unsafe")
        self.onceki = merkezler

    def yakindaki(self, cx, cy):
        r = self.a.tekrar_r
        return [(x, y) for x, y in self.gecmis if abs(x - cx) <= r and abs(y - cy) <= r]

    def tekrar_noktalari(self):
        """Geçmişte >= --tekrar olay görülen noktalar (her olay kendi yakınını sayar)."""
        return [(x, y) for x, y in self.gecmis if len(self.yakindaki(x, y)) >= self.a.tekrar]

    def _referans_guncelle(self, g, fark):
        a = self.a.ema
        self.ref += a * fark * (~self.maske)
        self.var += a * (fark * fark - self.var)
        np.maximum(self.var, 0.25, out=self.var)
        if self.kare % 300 == 0:
            self._esik_guncelle()

    def _olay(self, g, fark, xs, ys, cx, cy, tekrar=0):
        self.sayac += 1
        z = zaman_damgasi()
        tepe = float(fark[ys, xs].max())
        toplam = float(fark[ys, xs].sum())
        x0, y0 = int(xs.min()), int(ys.min())
        w, h = int(xs.max()) - x0 + 1, int(ys.max()) - y0 + 1
        kaz = f"0x{self.a.kazanc:02x}" if self.kam.sensor_manuel else "oto"
        mod = self.kam.mod_adi()
        self.csv.writerow({"zaman": z, "kare": self.kare, "piksel": len(xs),
                           "tepe": round(tepe, 1), "toplam": round(toplam, 1),
                           "cx": round(cx, 1), "cy": round(cy, 1), "x0": x0, "y0": y0,
                           "w": w, "h": h, "mod": mod, "kazanc": kaz, "tekrar": tekrar})
        self.csv_dosya.flush()
        self.gecmis.append((cx, cy))
        self._kaydet(z, g, fark, int(cx), int(cy), tepe, len(xs))
        dk = self.canli_sure() / 60
        log(f"OLAY #{self.sayac}: {len(xs)} piksel, tepe={tepe:.0f}, toplam={toplam:.0f}, "
            f"konum=({cx:.0f},{cy:.0f}) {w}x{h}" + (f" [TEKRAR x{tekrar}]" if tekrar else "") +
            f" | {self.sayac / max(dk, 1e-9):.2f}/dk")

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
                            mod=self.kam.mod_adi(), kazanc=self.a.kazanc)
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
             "sigma_medyan": round(float(np.median(np.sqrt(self.var[~self.maske]))), 3),
             "maskeli": int(self.maske.sum()), "veto": self.veto,
             "gurultulu_piksel": int(np.count_nonzero(self.sayim >= self.gurultu_limiti())),
             "ogrenme_atlanan": self.ogrenme_atlanan,
             "rastlanti_dk_ust_sinir": round(self.rastlanti / max(self.canli_sure() / 60, 1e-9), 3),
             "mod": self.kam.mod_adi(),
             "kazanc": self.a.kazanc if self.kam.sensor_manuel else None}
        with open("durum.json.tmp", "w") as f:
            json.dump(d, f, indent=1)
        os.replace("durum.json.tmp", "durum.json")
        return d


def csv_hazirla(r):
    """Eski CSV'yi okur, geçmiş olay konumlarını döndürür. 'tekrar' sütunu yoksa (eski sürüm)
    dosyayı sütun geriye dönük hesaplanmış olarak yeniden yazar (yedek: .bak)."""
    if not os.path.exists(CSV_YOL):
        return []
    with open(CSV_YOL, newline="") as f:
        okuyucu = csv.DictReader(f)
        satirlar, alanlar = list(okuyucu), okuyucu.fieldnames or []
    gecmis = []
    for s in satirlar:
        cx, cy = float(s["cx"]), float(s["cy"])
        if "tekrar" not in alanlar:
            s["tekrar"] = sum(abs(x - cx) <= r and abs(y - cy) <= r for x, y in gecmis)
        gecmis.append((cx, cy))
    if alanlar and "tekrar" not in alanlar:
        os.replace(CSV_YOL, CSV_YOL + ".bak")
        with open(CSV_YOL, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_ALANLAR, extrasaction="ignore")
            w.writeheader()
            w.writerows(satirlar)
        log(f"{CSV_YOL}: 'tekrar' sütunu eklendi (eski dosya {CSV_YOL}.bak)")
    log(f"Geçmiş: {len(gecmis)} olay okundu")
    return gecmis


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
    det.gecmis = csv_hazirla(a.tekrar_r)
    det.csv_dosya = open(CSV_YOL, "a", newline="")
    det.csv = csv.DictWriter(det.csv_dosya, fieldnames=CSV_ALANLAR)
    if not det.gecmis and os.path.getsize(CSV_YOL) == 0:
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
                    f"{det.sayac} olay ({d['olay_dk']}/dk, rastlantı<={d['rastlanti_dk_ust_sinir']}/dk), "
                    f"veto={d['veto']}, ref={d['ref_ort']}, "
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
