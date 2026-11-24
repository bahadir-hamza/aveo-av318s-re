# Gürültü korelasyonu: ham_kare.py çıktısında komşu piksel korelasyonu (0 = bağımsız piksel)
# Kullanım: python3 gurultu_kor.py ham_<ad>.npy ...
import numpy as np, sys
for f in sys.argv[1:]:
    a=np.load(f).astype(np.float32); b=a.reshape(a.shape[0],480,1280); n=b-b.mean(0)
    raw = "raw" in f
    if not raw: n=n[:,:,0::2]
    def kor(x,y): return (x*y).mean()/np.sqrt((x*x).mean()*(y*y).mean())
    W=n.shape[2]; ks=(1,2,3,4) if not raw else (1,2,4,8)
    print(f"{f:28s} std={n.std():.2f} yatay", " ".join(f"{k}:{kor(n[:,:,:W-k],n[:,:,k:]):.2f}" for k in ks),
          "| dikey", " ".join(f"{r}:{kor(n[:,:480-r],n[:,r:]):.2f}" for r in (1,2,3,4)))
