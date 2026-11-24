# seyrek_kayit.py çıktısında komşu-küme olay hızı: eşik (T2 küme pikseli, T1 tepe) ve gürültülü piksel vetosuna göre
# Kullanım: python3 seyrek_analiz.py ham_ff dsp_ff   (seyrek_<ad>.npz dosyaları çalışma dizininde)
import numpy as np, sys
def analiz(ad, T2s=(15,20,25), T1s=(25,30,40,60), vetolar=(None,30,10)):
    z=np.load(f"seyrek_{ad}.npz"); f,y,x,d=[z[k].astype(np.int64) for k in "fyxd"]
    N=int(z["kare"]); dk=N/float(z["fps"])/60
    pid=y*640+x; tot15=np.bincount(pid[d>15],minlength=307200)
    print(f"== {ad} ({dk:.1f} dk)")
    for veto in vetolar:
        ok = np.ones(len(d),bool) if veto is None else tot15[pid]<veto
        for T2 in T2s:
            m=(d>T2)&ok; F,Y,X,D=f[m],y[m],x[m],d[m]
            key=F*400000+Y*640+X; ks=np.sort(key)
            nb=np.zeros(len(key),np.int32)
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    if dy==0 and dx==0: continue
                    k2=key+dy*640+dx
                    i=np.searchsorted(ks,k2); i=np.minimum(i,len(ks)-1)
                    nb+= (ks[i]==k2)&(X+dx>=0)&(X+dx<640)
            row=[]
            for T1 in T1s:
                s=(D>T1)&(nb>0)
                # kare+kaba konum ile tekilleştir
                u=np.unique(F[s]*10000+(Y[s]//4)*160+X[s]//4)
                row.append(f"T1>{T1}:{len(u)/dk:7.2f}")
            print(f"  veto={str(veto):4s} T2>{T2}: komşulu küme/dk  "+"  ".join(row))
for ad in sys.argv[1:]: analiz(ad)
