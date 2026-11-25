# Gece galerisi: olay kırpmaları + sensör haritası + zaman çizelgesi
# Kullanım: python3 gece_galeri.py <olaylar_v2.csv ve olaylar/ içeren klasör> <çıktı.png>
import csv, sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime
D = sys.argv[1]; OUT = sys.argv[2]
SURF, INK, INK2, GRID, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
seq = LinearSegmentedColormap.from_list("seq", [SURF, "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "figure.facecolor": SURF, "axes.facecolor": SURF})
rows = list(csv.DictReader(open(f"{D}/olaylar_v2.csv")))
t = [datetime.strptime(r["zaman"][:15], "%Y%m%d_%H%M%S") for r in rows]
not_ = {}
for i, r in enumerate(rows):
    if r["zaman"].startswith("20261125_0632") or r["zaman"].startswith("20261125_0633"):
        not_[i] = "aynı piksel ×2 → şüpheli"
    if float(r["tepe"]) > 200: not_[i] = "en güçlü aday"

fig = plt.figure(figsize=(16, 12.5))
gs = fig.add_gridspec(3, 6, height_ratios=[1, 1, 1.35], hspace=0.42, wspace=0.18,
                      left=0.04, right=0.98, top=0.90, bottom=0.05)
fig.suptitle("Kozmik dedektör — 24→25 Kasım gecesi: 11.3 saatte 11 olay", x=0.04, ha="left",
             fontsize=17, fontweight="bold")
fig.text(0.04, 0.925, "OV7725 ham mod, kazanç 0xFF, 30 fps · olay = ≥2 komşu piksel >20, tepe >40 · "
         "hücrelerdeki sayılar: karanlık referansın üstündeki fark (Y birimi)", fontsize=10.5, color=INK2)
R = 4
for i, r in enumerate(rows):
    ax = fig.add_subplot(gs[i // 6, i % 6])
    z = np.load(f"{D}/olaylar/olay_{r['zaman']}.npz"); d = z["fark"]; x0, y0 = z["konum"]
    cy, cx = np.unravel_index(d.argmax(), d.shape)
    c = d[max(cy - R, 0):cy + R + 1, max(cx - R, 0):cx + R + 1]
    tepe = float(d.max())
    ax.imshow(np.clip(c, 0, None), cmap=seq, vmin=0, vmax=tepe, interpolation="nearest")
    for (yy, xx), v in np.ndenumerate(c):
        if v >= 5:
            ax.text(xx, yy, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                    color=SURF if v > 0.55 * tepe else INK)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_color(GRID)
    ax.set_title(f"{t[i]:%H:%M:%S}   tepe {tepe:.0f}", fontsize=10.5, loc="left", pad=4)
    ax.text(0, 1.0, "", transform=ax.transAxes)
    ax.set_xlabel(f"x={int(cx + x0)}, y={int(cy + y0)}" + (f"\n{not_[i]}" if i in not_ else ""),
                  fontsize=9, color=INK if i in not_ else INK2, fontweight="bold" if i in not_ else "normal")
ax = fig.add_subplot(gs[1, 5]); ax.axis("off")
ax.text(0, 0.95, "Nasıl okunur", fontweight="bold", fontsize=11, va="top")
ax.text(0, 0.80, "Her kare olayın tepe pikseli\nçevresindeki 9×9 piksel.\nKoyu = referansın daha üstünde\n"
        "(her kare kendi tepesine göre).\n\nGürültü sıçramaları tek piksel\nkalıyor (442 sıçramanın hiçbirinde\n"
        "komşu >20 yok). Buradaki olayların\nhepsinde ikinci bir piksel var\n→ yük paylaşımı, gerçek isabet\nolması muhtemel.",
        fontsize=9.5, va="top", color=INK2, linespacing=1.35)

# sensör haritası
ax = fig.add_subplot(gs[2, :3])
ax.add_patch(plt.Rectangle((0, 0), 640, 480, fc=SURF, ec=INK2, lw=1))
for xs in (0, 638): ax.add_patch(plt.Rectangle((xs, 0), 2, 480, fc=GRID, ec="none"))
cxs = [float(r["cx"]) for r in rows]; cys = [float(r["cy"]) for r in rows]
ax.scatter(cxs, cys, s=70, c=BLUE, edgecolors=SURF, linewidths=2, zorder=3)
for i, (x, y) in enumerate(zip(cxs, cys)):
    dy = -14 if i == 6 else 12
    ax.annotate(f"{t[i]:%H:%M}", (x, y), xytext=(6, dy), textcoords="offset points", fontsize=8.5, color=INK2)
ax.set_xlim(-10, 650); ax.set_ylim(490, -10); ax.set_aspect("equal")
ax.set_title("Sensör üzerindeki konumlar (640×480)", loc="left", fontsize=12, fontweight="bold")
ax.set_xlabel("x (piksel)"); ax.set_ylabel("y (piksel)")
ax.tick_params(length=0)
for s in ax.spines.values(): s.set_visible(False)

# zaman çizelgesi
ax = fig.add_subplot(gs[2, 3:])
tp = [float(r["tepe"]) for r in rows]
ax.axhline(40, color=INK2, lw=1, ls=(0, (4, 3)))
ax.text(datetime(2026, 11, 25, 0, 0), 46, "tepe eşiği 40", fontsize=9, color=INK2)
ax.scatter(t, tp, s=70, c=BLUE, edgecolors=SURF, linewidths=2, zorder=3)
etik = {}
for i, m in not_.items():
    if m not in etik: etik[m] = i
for m, i in etik.items():
    ax.annotate(m, (t[i], tp[i]), xytext=(-10, 8), textcoords="offset points", fontsize=9, ha="right", color=INK)
ax.set_xlim(datetime(2026, 11, 24, 20, 25), datetime(2026, 11, 25, 7, 46))
ax.set_ylim(0, 260); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
ax.set_title("Zaman çizelgesi — her nokta bir olay", loc="left", fontsize=12, fontweight="bold")
ax.set_ylabel("tepe (Y birimi)"); ax.tick_params(length=0)
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
fig.savefig(OUT, dpi=110)
print("ok", OUT)
