#!/usr/bin/env python3
"""Pazaryeri İlan Kiti (MIT, Redirhan Labs).

Ürün bilgisi (urun.yaml) → Trendyol, Hepsiburada, n11 ve Amazon.com.tr için ilan taslağı:
başlık (platform sınırı ve kalıbıyla), öne çıkan maddeler, açıklama (düz + HTML), özellik tablosu, arama kelimeleri,
görsel kontrol listesi (+ görsel varsa otomatik ölçüm) ve toplu yükleme hazırlık CSV'si.
İndirim / üstün iddia görürse uyarır ve Reklam Etiketi Kontrolü (github.com/redirhan/reklam-etiketi) girdisini yazar.

Yerel çalışır: yayın yok, hesap yok, ücretli API yok, tarayıcı yok. Python 3.8+ standart kütüphanesi
(görsel ölçümü için Pillow + numpy; PyYAML isteğe bağlı).

Kullanım:
  python3 ilan.py doctor
  python3 ilan.py yeni > urun.yaml                 # boş ürün dosyası
  python3 ilan.py kontrol urun.yaml                # yalnız denetim
  python3 ilan.py uret urun.yaml --cikti ilan/     # tüm platformlar
  python3 ilan.py uret urun.yaml --cikti ilan/ --platform trendyol,amazon
  python3 ilan.py kurallar [--platform n11]        # kurallar + kaynaklar + doğrulama işaretleri
Çıkış kodu: 0 = DÜZELT yok, 1 = en az bir DÜZELT (ya da görselde KALDI), 2 = girdi hatası.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ortak import (DOGRULA_NOTU, EMOJI_RE, PLATFORMLAR, RULES_PATH, SKILL_DIR, Kurallar, fold, load_yaml,  # noqa: E402
                   tr_lower, tr_sentence, tr_title)

VERSION = (SKILL_DIR / "VERSION").read_text().strip() if (SKILL_DIR / "VERSION").exists() else "dev"
REKLAM_ETIKETI_URL = "https://github.com/redirhan/reklam-etiketi"
SEVIYE_SIRA = ["DUZELT", "UYARI", "DOGRULA", "BILGI"]
SEVIYE_AD = {"DUZELT": "DÜZELT", "UYARI": "UYARI", "DOGRULA": "DOĞRULA", "BILGI": "BİLGİ"}

SABLON = """\
# Pazaryeri İlan Kiti: ürün dosyası. Bilmediğin alanı boş bırak; uydurma.
# Başlık, açıklama ve CSV bu dosyadan üretilir: python3 ilan.py uret urun.yaml --cikti ilan/
marka: ""                     # tescilli/kayıtlı marka adı, yazıldığı gibi kalır
urun_tipi: ""                 # ürünün adı (isim): "zeytinyağlı sabun", "seramik kupa", "tişört"
model: ""                     # seri / model adı (isteğe bağlı)
kategori: ""                  # ör. "Kozmetik > Banyo & Duş > Katı Sabun" (panelde platform kategorisini seç)
kategori_grubu: diger         # kozmetik | giyim | ev_mutfak | taki_aksesuar | gida | diger (eksik özellik uyarısı için)
cinsiyet: ""                  # giyimde: Erkek | Kadın | Unisex | Çocuk
temel_ozellikler:             # başlığa ÖNEM SIRASIYLA girer; sığmayan sondan düşer
  - ""
renk: ""
miktar: ""                    # "100 g", "350 ml", "2'li"
beden: ""                     # tek beden ürünlerde; bedenler için varyantlar bölümünü kullan
model_kodu: ""                # varyantları bağlayan ortak kod
barkod: ""                    # GTIN/EAN (tırnak içinde yaz)
stok_kodu: ""
stok:
fiyat:
  satis:                      # KDV dahil satış fiyatı
  liste:                      # üstü çizili / piyasa fiyatı (doluysa indirim sayılır, 10 gün kuralı)
  kdv: 20
  para_birimi: TRY
indirim:                      # indirim yoksa bu bloğu silin
  onceki_fiyat:
  indirimli_fiyat:
  son_10_gun_en_dusuk:        # indirimden önceki 10 günde AYNI kanaldaki en düşük fiyat
  baslangic: ""
  bitis: ""
  kanal: ""                   # trendyol | hepsiburada | n11 | amazon | web
desi:
hazirlik_gunu:
ozellikler:                   # özellik tablosu: "Ad: değer"
  Materyal: ""
one_cikanlar:                 # 3-5 madde, her biri tek fayda + somut bilgi
  - ""
aciklama: |
  Ürünü 2-4 kısa paragrafta anlat: ne, kimin için, neden bu ürün.
kullanim: ""
bakim: ""
paket_icerigi:
  - ""
uyarilar: ""
anahtar_kelimeler:            # alıcının arayacağı kelimeler (eş anlamlılar dahil)
  - ""
varyantlar: []                # ör. her beden için: - beden: "M" / barkod: "..." / stok: 10
gorseller: []                 # ilk görsel = ana görsel (beyaz zemin)
platformlar: [trendyol, hepsiburada, n11, amazon]
"""


# ----------------------------------------------------------------- yardımcılar
def s(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


def liste(x) -> list[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return [s(v) for v in x if s(v)]
    return [s(x)] if s(x) else []


def para(x) -> float | None:
    if x in (None, ""):
        return None
    try:
        return float(str(x).replace(".", "").replace(",", ".")) if isinstance(x, str) and "," in x else float(x)
    except ValueError:
        return None


def tl(x: float | None) -> str:
    if x is None:
        return "?"
    t = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return t + " TL"


def gtin_gecerli(kod: str) -> bool:
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", kod):
        return False
    digits = [int(c) for c in kod]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def kelime_var(metin: str, ifade: str) -> bool:
    """Türkçe-duyarsız ifade arama. Sonu $ = tam kelime, r: = düzenli ifade."""
    f = fold(metin)
    if ifade.startswith("r:"):
        return re.search(ifade[2:], f) is not None
    tam = ifade.endswith("$")
    ifade = fold(ifade.rstrip("$"))
    if tam:
        return re.search(rf"(?<![a-z0-9]){re.escape(ifade)}(?![a-z0-9])", f) is not None
    return re.search(rf"(?<![a-z0-9]){re.escape(ifade)}", f) is not None


def bulunanlar(metin: str, ifadeler) -> list[str]:
    out = []
    for i in ifadeler or []:
        if kelime_var(metin, i):
            ad = i[2:] if i.startswith("r:") else i.rstrip("$")
            if ad not in out:
                out.append(ad)
    return out


def kirp_kelime(metin: str, limit: int) -> str:
    if len(metin) <= limit:
        return metin
    cut = metin[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;-")


# ----------------------------------------------------------------- ürün
class Urun:
    def __init__(self, d: dict, yol: Path):
        if not isinstance(d, dict):
            raise ValueError("ürün dosyası bir sözlük (anahtar: değer) olmalı")
        self.d = d
        self.yol = yol
        g = d.get
        self.marka = s(g("marka"))
        self.urun_tipi = s(g("urun_tipi"))
        self.model = s(g("model"))
        self.kategori = s(g("kategori"))
        self.kategori_grubu = s(g("kategori_grubu")) or "diger"
        self.cinsiyet = s(g("cinsiyet"))
        self.temel = liste(g("temel_ozellikler"))
        self.renk = s(g("renk"))
        self.miktar = s(g("miktar"))
        self.beden = s(g("beden"))
        self.model_kodu = s(g("model_kodu"))
        self.barkod = s(g("barkod"))
        self.stok_kodu = s(g("stok_kodu"))
        self.stok = s(g("stok"))
        f = g("fiyat") or {}
        self.satis = para(f.get("satis"))
        self.liste_fiyat = para(f.get("liste"))
        self.kdv = s(f.get("kdv")) or "20"
        self.para_birimi = s(f.get("para_birimi")) or "TRY"
        self.indirim = g("indirim") if isinstance(g("indirim"), dict) else None
        self.desi = s(g("desi"))
        self.hazirlik = s(g("hazirlik_gunu"))
        oz = g("ozellikler") or {}
        self.ozellikler = {s(k): s(v) for k, v in oz.items()} if isinstance(oz, dict) else {}
        self.one_cikanlar = liste(g("one_cikanlar"))
        self.aciklama = s(g("aciklama"))
        self.kullanim = s(g("kullanim"))
        self.bakim = s(g("bakim"))
        self.paket = liste(g("paket_icerigi"))
        self.uyarilar = s(g("uyarilar"))
        self.anahtar = liste(g("anahtar_kelimeler"))
        self.varyantlar = [v for v in (g("varyantlar") or []) if isinstance(v, dict)]
        self.gorseller = [self._yol(p) for p in liste(g("gorseller"))]
        pl = liste(g("platformlar")) or PLATFORMLAR
        self.platformlar = [p for p in PLATFORMLAR if p in [x.lower() for x in pl]]

    def _yol(self, p: str) -> Path:
        q = Path(p).expanduser()
        return q if q.is_absolute() else (self.yol.parent / q)

    def metinler(self) -> dict[str, str]:
        """Denetlenecek tüm serbest metinler."""
        return {
            "temel_ozellikler": " | ".join(self.temel),
            "urun_tipi": self.urun_tipi,
            "model": self.model,
            "one_cikanlar": "\n".join(self.one_cikanlar),
            "aciklama": self.aciklama,
            "kullanim": self.kullanim,
            "bakim": self.bakim,
            "paket_icerigi": "\n".join(self.paket),
            "uyarilar": self.uyarilar,
            "ozellikler": "\n".join(f"{k}: {v}" for k, v in self.ozellikler.items()),
            "anahtar_kelimeler": " | ".join(self.anahtar),
        }


# ----------------------------------------------------------------- başlık
def _parca(u: Urun, tok: str, varyant: dict | None) -> list[tuple[str, str, bool]]:
    """(tür, metin, düşürülebilir mi)"""
    v = varyant or {}
    if tok == "marka":
        return [("marka", u.marka, False)] if u.marka else []
    if tok == "model":
        return [("model", u.model, True)] if u.model else []
    if tok == "cinsiyet":
        return [("cinsiyet", u.cinsiyet, False)] if u.cinsiyet else []
    if tok == "urun_tipi":
        return [("urun_tipi", tr_title(u.urun_tipi), False)] if u.urun_tipi else []
    if tok == "temel_ozellikler":
        return [("temel", tr_title(t), True) for t in u.temel]
    if tok == "renk":
        r = s(v.get("renk")) or u.renk
        return [("renk", tr_title(r), True)] if r else []
    if tok == "miktar":
        return [("miktar", u.miktar, True)] if u.miktar else []
    if tok == "beden":
        b = s(v.get("beden")) or u.beden
        return [("beden", f"{b} Beden" if b and len(b) <= 4 else b, True)] if b else []
    if tok in (",", "-", "|"):
        return [("ayrac", tok, False)]
    return []


def _birlestir(parcalar: list[tuple[str, str, bool]], marka: str) -> str:
    out: list[str] = []
    gorulen: set[str] = set()
    for tur, metin, _ in parcalar:
        if tur == "ayrac":
            if out and not out[-1].endswith(("," , "-", "|")):
                out[-1] = out[-1] + "," if metin == "," else out[-1] + f" {metin}"
            continue
        kelimeler = []
        for w in metin.split():
            f = fold(w).strip(",.")
            tekrar_serbest = any(ch.isdigit() for ch in w) or f in {"ve", "ile", "icin"} or len(f) <= 1
            if tur == "marka":
                gorulen.add(f)
                kelimeler.append(w)
            elif f in gorulen and not tekrar_serbest:
                continue
            else:
                gorulen.add(f)
                kelimeler.append(w)
        if kelimeler:
            out.append(" ".join(kelimeler))
    t = " ".join(out).strip().rstrip(",-| ")
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",(?=\S)", ", ", t)
    return re.sub(r"\s{2,}", " ", t)


def baslik_uret(u: Urun, plat: str, R: Kurallar, varyant: dict | None = None) -> tuple[str, list[str]]:
    kalip = R.deger(plat, "baslik_kalip") or ["marka", "temel_ozellikler", "urun_tipi", "renk", "miktar"]
    mx = int(R.deger(plat, "baslik_max", 100))
    parcalar = [p for tok in kalip for p in _parca(u, tok, varyant)]
    dusen: list[str] = []
    t = _birlestir(parcalar, u.marka)
    # sığmazsa: önce en az önemli temel özellik (listenin sonu), sonra model, renk, miktar, beden
    sira = ["temel", "model", "beden", "renk", "miktar"]
    while len(t) > mx:
        aday = None
        for tur in sira:
            idx = [i for i, p in enumerate(parcalar) if p[0] == tur and p[2]]
            if idx:
                aday = idx[-1]
                break
        if aday is None:
            break
        dusen.append(parcalar[aday][1])
        parcalar.pop(aday)
        t = _birlestir(parcalar, u.marka)
    return t, dusen


# ----------------------------------------------------------------- açıklama
def aciklama_bloklari(u: Urun, maddeler: list[str]) -> list[tuple[str, object]]:
    bloklar: list[tuple[str, object]] = []
    paragraflar = [p.strip() for p in re.split(r"\n\s*\n", u.aciklama) if p.strip()]
    if paragraflar:
        bloklar.append(("paragraflar", [" ".join(p.split()) for p in paragraflar]))
    if maddeler:
        bloklar.append(("Öne çıkan özellikler", maddeler))
    oz = ozellik_satirlari(u)
    if oz:
        bloklar.append(("Ürün özellikleri", [f"{k}: {v}" for k, v in oz]))
    if u.kullanim:
        bloklar.append(("Kullanım", [u.kullanim]))
    if u.bakim:
        bloklar.append(("Bakım", [u.bakim]))
    if u.paket:
        bloklar.append(("Paket içeriği", u.paket))
    if u.uyarilar:
        bloklar.append(("Uyarılar", [u.uyarilar]))
    return bloklar


def aciklama_cumle(bloklar) -> str:
    """Liste kullanmayan düz metin (Amazon: tam cümleler, liste yok). Maddeler ayrı alanda olduğu için atlanır."""
    out = []
    for ad, icerik in bloklar:
        if ad == "paragraflar":
            out += list(icerik)
        elif ad == "Öne çıkan özellikler":
            continue
        elif ad == "Ürün özellikleri":
            oz = [x for x in icerik if not x.startswith(("Marka:", "Cinsiyet:", "Renk:"))]
            if oz:
                out.append("Ürün özellikleri: " + "; ".join(oz) + ".")
        elif ad == "Paket içeriği":
            out.append("Paket içeriği: " + ", ".join(icerik) + ".")
        else:
            out.append(f"{ad}: " + " ".join(icerik))
    return "\n\n".join(x.replace("..", ".") for x in out).strip() + "\n"


def aciklama_duz(bloklar) -> str:
    out = []
    for ad, icerik in bloklar:
        if ad == "paragraflar":
            for par in icerik:
                out += [par, ""]
        elif ad in ("Öne çıkan özellikler", "Ürün özellikleri", "Paket içeriği"):
            out += [ad, *[f"- {x}" for x in icerik], ""]
        else:
            out += [ad, *icerik, ""]
    return "\n".join(out).strip() + "\n"


def aciklama_html(bloklar) -> str:
    e = html.escape
    out = []
    for ad, icerik in bloklar:
        if ad == "paragraflar":
            out += [f"<p>{e(p)}</p>" for p in icerik]
        elif ad in ("Öne çıkan özellikler", "Paket içeriği"):
            out.append(f"<h3>{e(ad)}</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in icerik) + "</ul>")
        elif ad == "Ürün özellikleri":
            li = []
            for x in icerik:
                k, _, v = x.partition(": ")
                li.append(f"<li><strong>{e(k)}:</strong> {e(v)}</li>")
            out.append(f"<h3>{e(ad)}</h3><ul>" + "".join(li) + "</ul>")
        else:
            out.append(f"<h3>{e(ad)}</h3>" + "".join(f"<p>{e(x)}</p>" for x in icerik))
    return "\n".join(out) + "\n"


def ozellik_satirlari(u: Urun) -> list[tuple[str, str]]:
    satir = [("Marka", u.marka)]
    if u.model:
        satir.append(("Model", u.model))
    if u.cinsiyet:
        satir.append(("Cinsiyet", u.cinsiyet))
    if u.renk:
        satir.append(("Renk", tr_title(u.renk)))
    if u.miktar and fold(u.miktar) not in {fold(v) for v in u.ozellikler.values()}:
        satir.append(("Miktar", u.miktar))
    mevcut = {fold(k) for k, _ in satir}
    for k, v in u.ozellikler.items():
        if v and fold(k) not in mevcut:
            satir.append((k, v))
            mevcut.add(fold(k))
    return [(k, v) for k, v in satir if v]


def maddeler_uret(u: Urun, plat: str, R: Kurallar) -> tuple[list[str], list[str]]:
    adet = int(R.deger(plat, "madde_adet", 5))
    mx = R.deger(plat, "madde_max")
    notlar = []
    out = []
    for m in u.one_cikanlar[:adet]:
        m = tr_sentence(" ".join(m.split())).rstrip(".")
        if mx and len(m) > int(mx):
            notlar.append(f"madde {len(out) + 1} {len(m)} karakter; {mx} sınırına kırpıldı")
            m = kirp_kelime(m, int(mx))
        out.append(m)
    if len(u.one_cikanlar) > adet:
        notlar.append(f"{len(u.one_cikanlar)} madde verildi; {R.ad(plat)} için ilk {adet} madde kullanıldı")
    return out, notlar


# ----------------------------------------------------------------- arama kelimeleri
def amazon_arama_terimi(u: Urun, baslik: str, limit_bayt: int) -> tuple[str, list[str]]:
    baslik_k = {fold(w).strip(",.") for w in baslik.split()}
    marka_k = {fold(w) for w in u.marka.split()}
    yasak = {"ve", "ile", "icin", "bir", "en", "cok"}
    kelimeler: list[str] = []
    gorulen: set[str] = set()
    for ifade in u.anahtar:
        for w in tr_lower(ifade).replace(",", " ").split():
            f = fold(w)
            kok = f if len(f) <= 4 else f[: max(4, len(f) - 2)]
            if (f in baslik_k or f in marka_k or f in yasak or f in gorulen
                    or any(b.startswith(kok) or f.startswith(b) for b in baslik_k if len(b) > 3)):
                continue
            gorulen.add(f)
            kelimeler.append(w)
    out, dusen = [], []
    for w in kelimeler:
        aday = " ".join(out + [w])
        if len(aday.encode("utf-8")) < limit_bayt:
            out.append(w)
        else:
            dusen.append(w)
    return " ".join(out), dusen


def kelimeler_geciyor(metin: str, ifade: str) -> bool:
    """İfadenin her kelimesi metinde (Türkçe ekleri tolere ederek, sıra fark etmeden) geçiyor mu?"""
    kel = [fold(w) for w in re.findall(r"[\w%'-]+", metin)]
    for w in re.findall(r"[\w%'-]+", ifade):
        f = fold(w)
        kok = f if len(f) <= 4 else f[: max(4, len(f) - 2)]
        if not any(k.startswith(kok) for k in kel):
            return False
    return True


def anahtar_kapsam(u: Urun, baslik: str, aciklama: str) -> list[tuple[str, bool, bool]]:
    return [(k, kelimeler_geciyor(baslik, k), kelimeler_geciyor(aciklama, k)) for k in u.anahtar]


# ----------------------------------------------------------------- denetim
class Bulgular:
    def __init__(self):
        self.items: list[dict] = []

    def ekle(self, seviye, alan, mesaj, platform=None):
        self.items.append({"seviye": seviye, "alan": alan, "mesaj": mesaj, "platform": platform})

    def say(self, seviye) -> int:
        return sum(1 for i in self.items if i["seviye"] == seviye)

    def platform_icin(self, plat):
        return [i for i in self.items if i["platform"] in (None, plat)]


def indirim_bilgisi(u: Urun) -> dict | None:
    ind = dict(u.indirim or {})
    onceki = para(ind.get("onceki_fiyat")) or u.liste_fiyat
    indirimli = para(ind.get("indirimli_fiyat")) or u.satis
    if not u.indirim and not (u.liste_fiyat and u.satis and u.liste_fiyat > u.satis):
        return None
    return {
        "onceki": onceki, "indirimli": indirimli, "son10": para(ind.get("son_10_gun_en_dusuk")),
        "baslangic": s(ind.get("baslangic")), "bitis": s(ind.get("bitis")), "kanal": s(ind.get("kanal")),
        "stok": s(ind.get("stok_adedi")),
    }


def denetle(u: Urun, R: Kurallar) -> tuple[Bulgular, dict]:
    B = Bulgular()
    o = R.ortak
    yasak_promo = R.ortak_deger("yasak_baslik_ifadeleri", [])
    iletisim = R.ortak_deger("yasak_iletisim_ifadeleri", [])
    diger_platform = R.ortak_deger("diger_platform_adlari", [])
    belgeli = R.ortak_deger("belge_gerektiren_iddialar", [])
    ustunluk = R.ortak_deger("ustunluk_iddialari", [])
    indirim_kel = R.ortak_deger("indirim_ifadeleri", [])
    _ = o

    if not u.marka:
        B.ekle("DUZELT", "marka", "Marka boş. Pazaryerleri marka ister (markasızsa platformun 'markasız/özel üretim' seçeneğini panelde seç).")
    if not u.urun_tipi:
        B.ekle("DUZELT", "urun_tipi", "Ürün tipi boş (ör. \"zeytinyağlı sabun\").")
    if not u.temel:
        B.ekle("UYARI", "temel_ozellikler", "Temel özellik yok; başlık zayıf kalır (malzeme, koku/renk, kullanım alanı, ölçü).")
    if not u.kategori:
        B.ekle("UYARI", "kategori", "Kategori boş. Doğru kategori zorunlu özellikleri belirler.")

    # TODO / yer tutucu
    for alan, metin in [("marka", u.marka), ("urun_tipi", u.urun_tipi), *u.metinler().items()]:
        if re.search(r"\bTODO\b|\?\?\?|XXX|<doldur>", metin):
            B.ekle("DUZELT", alan, "Doldurulmamış yer tutucu (TODO/???/XXX).")

    # başlığa girecek alanlarda yasaklı ifadeler
    baslik_metni = " ".join([u.model, u.urun_tipi, *u.temel, u.renk, u.miktar])
    for f in bulunanlar(baslik_metni, yasak_promo):
        B.ekle("DUZELT", "başlık", f"Başlığa girecek alanda \"{f}\": kampanya/kargo/fiyat ifadeleri başlıkta yasak ya da ret sebebi.")
    if EMOJI_RE.search(baslik_metni):
        B.ekle("DUZELT", "başlık", "Başlık alanlarında emoji var.")
    for w in baslik_metni.split():
        if len(w) >= 5 and w.isalpha() and w.isupper():
            B.ekle("UYARI", "başlık", f"Tamamı büyük harf kelime: \"{w}\" (marka adı değilse normal yaz).")

    # tüm metinler: iletişim, link, başka platform
    for alan, metin in u.metinler().items():
        if not metin:
            continue
        if re.search(r"https?://|www\.|\.com\b|\.com\.tr\b|\.net\b", metin, re.I):
            B.ekle("DUZELT", alan, "Bağlantı (URL) var: ilan metinlerinde dış bağlantı yasak / ret sebebi.")
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", metin):
            B.ekle("DUZELT", alan, "E-posta adresi var: ilanda iletişim bilgisi yasak.")
        if re.search(r"(?<!\d)(\+?90[\s-]?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)", metin):
            B.ekle("DUZELT", alan, "Telefon numarası var: ilanda iletişim bilgisi yasak.")
        if re.search(r"(?<![\w.])@[A-Za-z0-9_.]{3,}", metin):
            B.ekle("DUZELT", alan, "Sosyal medya kullanıcı adı (@...) var: ilanda dış yönlendirme yasak.")
        for f in bulunanlar(metin, iletisim):
            B.ekle("DUZELT", alan, f"\"{f}\": platform dışı iletişim/yönlendirme ifadesi.")
        for f in bulunanlar(metin, diger_platform):
            B.ekle("DUZELT", alan, f"\"{f}\": ilanda başka satış platformu/kanalı anılmamalı.")
        if alan != "temel_ozellikler" and EMOJI_RE.search(metin):
            B.ekle("UYARI", alan, "Emoji var: açıklama/madde alanlarında çoğu platform göstermez ya da reddeder.")
        for f in bulunanlar(metin, belgeli):
            B.ekle("UYARI", alan, f"\"{f}\": belge gerektiren iddia. Belgen (sertifika, test raporu) yoksa yazma; "
                                 "kozmetik/gıdada sağlık iddiası ayrıca yasak olabilir.")
        for f in bulunanlar(metin, ustunluk):
            B.ekle("UYARI", alan, f"\"{f}\": üstünlük iddiası ispat ister (Reklam Etiketi Kontrolü KRS-03).")
        if alan in ("aciklama", "one_cikanlar"):
            for f in bulunanlar(metin, yasak_promo):
                B.ekle("UYARI", alan, f"\"{f}\": kampanya/kargo ifadesi açıklamada da çoğu platformda istenmez; kampanyayı panelden tanımla.")

    # barkod
    kodlar = [u.barkod] + [s(v.get("barkod")) for v in u.varyantlar]
    gecersiz = [k for k in kodlar if k and not gtin_gecerli(k)]
    ic_kod = [k for k in kodlar if k and gtin_gecerli(k) and k[:1] == "2" and len(k) == 13]
    if gecersiz:
        B.ekle("UYARI", "barkod", f"{', '.join(gecersiz)}: geçerli GTIN/EAN değil (8/12/13/14 hane + kontrol hanesi). Trendyol "
                                  "satıcı barkoduna izin verir; n11 yalnız ulusal barkodu kaydeder; Amazon GTIN ister.")
    if ic_kod:
        B.ekle("UYARI", "barkod", f"{', '.join(ic_kod)}: 20-29 ile başlayan EAN-13 mağaza içi (GS1 kısıtlı) koddur; Amazon kabul "
                                  "etmez, GS1 Türkiye barkodu ya da GTIN muafiyeti gerekir.", "amazon")
    if not u.barkod and not any(s(v.get("barkod")) for v in u.varyantlar):
        B.ekle("UYARI", "barkod", "Barkod yok: tüm platformlar ürün başına benzersiz barkod ister.")
    if len(set(k for k in kodlar if k)) < len([k for k in kodlar if k]):
        B.ekle("DUZELT", "barkod", "Aynı barkod birden çok varyantta: her varyantın barkodu farklı olmalı.")
    if u.varyantlar and not u.model_kodu:
        B.ekle("DUZELT", "model_kodu", "Varyantlı üründe model kodu yok: bedenler/renkler aynı model koduyla gruplanır.")

    # kategoriye göre özellik ipuçları
    ipucu = (R.ortak_deger("kategori_ozellikleri", {}) or {}).get(u.kategori_grubu) or []
    mevcut = {fold(k) for k in u.ozellikler} | {fold(x) for x in ("Marka", "Renk" if u.renk else "", "Cinsiyet" if u.cinsiyet else "")}
    eksik = [k for k in ipucu if not any(fold(x.strip()) in mevcut for x in k.split("/"))
             and not (fold(k) == "beden" and (u.varyantlar or u.beden))]
    if eksik:
        B.ekle("UYARI", "ozellikler", f"{u.kategori_grubu} ürünlerinde sık zorunlu/önemli alanlar eksik: {', '.join(eksik)} "
                                      "(kategoriye göre değişir; panelde zorunlu alanları kontrol et).")
    if len(u.aciklama) < 250:
        B.ekle("UYARI", "aciklama", f"Açıklama kısa ({len(u.aciklama)} karakter). 2-4 paragraf: ne, kimin için, neden, ölçü/malzeme.")
    if len(u.one_cikanlar) < 3:
        B.ekle("UYARI", "one_cikanlar", "3-5 öne çıkan madde yaz (Amazon'da 5 madde alanı var).")
    if not u.anahtar:
        B.ekle("UYARI", "anahtar_kelimeler", "Anahtar kelime yok: alıcının arayacağı 5-15 kelime/ifade yaz.")

    # fiyat ve indirim
    ind = indirim_bilgisi(u)
    tum_metin = " ".join([baslik_metni, *u.metinler().values()])
    metin_indirim = bulunanlar(tum_metin, indirim_kel)
    if metin_indirim and not ind:
        B.ekle("UYARI", "indirim", f"Metinde indirim ifadesi var ({', '.join(metin_indirim[:3])}) ama fiyat/indirim bilgisi yok. "
                                   "İndirim varsa önceki fiyatı, tarihleri ve son 10 günün en düşük fiyatını yaz; yoksa ifadeyi çıkar.")
    if ind:
        if ind["onceki"] and ind["indirimli"] and ind["onceki"] <= ind["indirimli"]:
            B.ekle("DUZELT", "fiyat", f"Önceki fiyat ({tl(ind['onceki'])}) indirimli fiyattan ({tl(ind['indirimli'])}) büyük değil.")
        if ind["son10"] is None:
            B.ekle("UYARI", "indirim", "Üstü çizili/önceki fiyat var ama son_10_gun_en_dusuk yok. İndirimden önceki fiyat, indirimin "
                                       "başlangıcından önceki 10 günde AYNI kanalda uygulanan en düşük fiyattır (RG 33297, md.14/3, 14/5). "
                                       "Bu sayıyı bilmeden üstü çizili fiyat gösterme.")
        elif ind["onceki"] and ind["onceki"] > ind["son10"] + 0.001:
            dogru = ((ind["son10"] - ind["indirimli"]) / ind["son10"] * 100) if ind["indirimli"] else None
            B.ekle("DUZELT", "indirim", f"Önceki fiyat {tl(ind['onceki'])} gösteriliyor ama son 10 günün en düşüğü {tl(ind['son10'])}. "
                                        f"Referans {tl(ind['son10'])} olmalı" + (f"; gerçek indirim %{int(dogru)}" if dogru is not None else "") +
                                        " (RG 33297, md.14/3).")
        if not (ind["baslangic"] and ind["bitis"]):
            B.ekle("UYARI", "indirim", "İndirimin başlangıç ve bitiş tarihi yok (reklamda/kampanyada yazılması gerekir, md.14/1). "
                                       "Pazaryeri kampanya aracını kullanıyorsan tarihleri orada gir.")
        if ind["kanal"] and fold(ind["kanal"]) in PLATFORMLAR:
            for p in u.platformlar:
                if p != fold(ind["kanal"]):
                    B.ekle("UYARI", "indirim", f"Önceki fiyat {ind['kanal']} kanalına ait; {R.ad(p)} için o platformdaki son 10 gün "
                                               "fiyatı esas alınır (md.14/5).", p)
        B.ekle("BILGI", "indirim", "Pazaryerlerinde 'liste / piyasa satış fiyatı' alanı ürün sayfasında üstü çizili gösterilebilir; "
                                   "bu alan da indirimden önceki fiyat iddiası sayılır, aynı 10 gün kuralına uy.")
    hook = {"indirim": ind, "metin_indirim": metin_indirim,
            "ustunluk": bulunanlar(tum_metin, ustunluk), "gerekli": bool(ind or metin_indirim or bulunanlar(tum_metin, ustunluk))}
    return B, hook


# ----------------------------------------------------------------- platform çıktısı
def platform_uret(u: Urun, plat: str, R: Kurallar, B: Bulgular) -> dict:
    t, dusen = baslik_uret(u, plat, R)
    mx = int(R.deger(plat, "baslik_max", 100))
    mn = int(R.deger(plat, "baslik_min", 0) or 0)
    if dusen:
        B.ekle("BILGI", "başlık", f"{R.ad(plat)} sınırı ({mx}) için başlıktan çıkarılan: {', '.join(dusen)}", plat)
    if len(t) > mx:
        B.ekle("DUZELT", "başlık", f"{R.ad(plat)} başlığı {len(t)} karakter; sınır {mx}. Ürün tipini/markayı kısalt.", plat)
    if mn and len(t) < mn:
        B.ekle("UYARI", "başlık", f"{R.ad(plat)} başlığı {len(t)} karakter; en az {mn}. Temel özellik ekle.", plat)
    onr = int(R.deger(plat, "baslik_onerilen_min", 0) or 0)
    if onr and mn <= len(t) < onr:
        B.ekle("UYARI", "başlık", f"{R.ad(plat)} başlığı {len(t)} karakter; {onr} altı ilan kalite puanını düşürür"
                                 f"{R.etiket(plat, 'baslik_onerilen_min')}.", plat)
    alt = ""
    amx = R.deger(plat, "alt_baslik_max")
    if amx:
        t_k = {fold(w) for w in t.split()}
        kalan = [tr_title(x) for x in u.temel if not all(fold(w) in t_k for w in x.split())]
        alt = " · ".join(kalan) if kalan else (u.one_cikanlar[0] if u.one_cikanlar else "")
        alt = kirp_kelime(alt, int(amx)).rstrip(" ·")
        if alt and len(alt) < 15:
            alt = kirp_kelime(" · ".join([alt] + u.one_cikanlar[:1]), int(amx)).rstrip(" ·")
    if plat == "amazon":
        ozel = R.deger(plat, "baslik_yasak_karakterler") or []
        bad = [c for c in ozel if c in t]
        if bad:
            B.ekle("DUZELT", "başlık", f"Amazon başlığında yasak karakter: {' '.join(bad)}", plat)
        if "%" in t:
            B.ekle("UYARI", "başlık", "Amazon başlığında '%' var: TR giyim stil kılavuzu (2018) başlıkta ! * £ ? % işaretlerini "
                                     "istemiyor; '%100 Pamuk' yerine 'Pamuk' ya da 'Pamuklu' yaz ya da kategori kılavuzuna bak"
                                     + R.etiket(plat, "not_baslik_icerik") + ".", plat)
        tekrar = {}
        for w in t.split():
            f = fold(w).strip(",.")
            if len(f) > 2 and not any(ch.isdigit() for ch in f):
                tekrar[f] = tekrar.get(f, 0) + 1
        for w, n in tekrar.items():
            if n > 2:
                B.ekle("DUZELT", "başlık", f"Amazon başlığında \"{w}\" {n} kez geçiyor (en çok 2).", plat)
    maddeler, mnot = maddeler_uret(u, plat, R)
    for n in mnot:
        B.ekle("BILGI", "maddeler", f"{R.ad(plat)}: {n}", plat)
    bloklar = aciklama_bloklari(u, maddeler)
    duz = aciklama_duz(bloklar)
    htm = aciklama_html(bloklar)
    amax = R.deger(plat, "aciklama_max")
    html_izin = str(R.deger(plat, "aciklama_html", "evet"))
    if str(R.deger(plat, "aciklama_liste", "evet")) == "hayir":
        duz = aciklama_cumle(bloklar)
    aciklama_alan = htm if html_izin == "evet" else duz
    if amax and len(aciklama_alan) > int(amax):
        B.ekle("DUZELT", "açıklama", f"{R.ad(plat)} açıklaması {len(aciklama_alan)} karakter; sınır {amax}.", plat)
    arama, arama_dusen = "", []
    if plat == "amazon":
        limit = int(R.deger(plat, "arama_terimi_bayt", 250))
        arama, arama_dusen = amazon_arama_terimi(u, t, limit)
        if arama_dusen:
            B.ekle("BILGI", "arama", f"Amazon arama terimleri {limit} bayt sınırı için çıkarılan: {', '.join(arama_dusen)}", plat)
    varyant_basliklar = []
    for v in u.varyantlar:
        vt, _ = baslik_uret(u, plat, R, v)
        varyant_basliklar.append((v, vt))
    return {"platform": plat, "ad": R.ad(plat), "baslik": t, "baslik_uzunluk": len(t), "baslik_max": mx,
            "dusen": dusen, "alt_baslik": alt, "maddeler": maddeler, "aciklama_duz": duz, "aciklama_html": htm, "aciklama_alan": aciklama_alan,
            "html_izin": html_izin, "arama_terimleri": arama, "kapsam": anahtar_kapsam(u, t, duz),
            "varyantlar": varyant_basliklar}


def csv_degerleri(u: Urun, P: dict, varyant: dict | None, vt: str | None) -> dict:
    v = varyant or {}
    gorsel_adlari = [p.name for p in u.gorseller]
    d = {
        "baslik": vt or P["baslik"], "aciklama": P["aciklama_alan"], "aciklama_duz": P["aciklama_duz"].strip(),
        "aciklama_html": P["aciklama_html"].strip(), "marka": u.marka, "kategori": u.kategori,
        "barkod": s(v.get("barkod")) or u.barkod, "model_kodu": u.model_kodu,
        "stok_kodu": s(v.get("stok_kodu")) or u.stok_kodu, "stok": s(v.get("stok")) or u.stok,
        "satis_fiyati": f"{u.satis:.2f}" if u.satis is not None else "",
        "liste_fiyati": f"{(u.liste_fiyat or u.satis):.2f}" if (u.liste_fiyat or u.satis) is not None else "",
        "kdv": u.kdv, "para_birimi": u.para_birimi, "desi": u.desi, "hazirlik_gunu": u.hazirlik,
        "renk": s(v.get("renk")) or u.renk, "beden": s(v.get("beden")) or u.beden, "cinsiyet": u.cinsiyet,
        "miktar": u.miktar, "arama_terimleri": P["arama_terimleri"], "alt_baslik": P.get("alt_baslik", ""),
    }
    kod = d["barkod"]
    d["barkod_turu"] = ({8: "EAN", 12: "UPC", 13: "EAN", 14: "GTIN"}.get(len(kod), "") if kod.isdigit() else "")
    if P["platform"] == "n11" and d["para_birimi"] == "TRY":
        d["para_birimi"] = "TL"
    for i in range(1, 11):
        d[f"gorsel_{i}"] = gorsel_adlari[i - 1] if i <= len(gorsel_adlari) else ""
    for i in range(1, 6):
        d[f"madde_{i}"] = P["maddeler"][i - 1] if i <= len(P["maddeler"]) else ""
    for k, val in u.ozellikler.items():
        d[f"ozellik:{fold(k)}"] = val
    return d


def csv_yaz(u: Urun, P: dict, plat: str, R: Kurallar, yol: Path) -> int:
    kolonlar = R.deger(plat, "csv_kolonlar") or []
    if not kolonlar:
        return 0
    satirlar = [(None, None)] if not u.varyantlar else list(P["varyantlar"])
    with open(yol, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow([k["kolon"] for k in kolonlar])
        for v, vt in satirlar:
            d = csv_degerleri(u, P, v, vt)
            row = []
            for k in kolonlar:
                alan = k.get("alan", "")
                val = d.get(alan, "")
                if not val and alan.startswith("ozellik:"):
                    val = d.get("ozellik:" + fold(alan.split(":", 1)[1]), "")
                row.append(val)
            w.writerow(row)
    return len(satirlar)


def gorsel_listesi_md(plat: str, R: Kurallar) -> list[str]:
    def k(key, fmt):
        val = R.deger(plat, key)
        if val in (None, "", []):
            return None
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        return f"- [ ] {fmt.format(val)}{R.etiket(plat, key)}"

    zemin_ad = {"saf_beyaz": "saf beyaz (RGB 255,255,255)", "beyaz_tercih": "beyaz ya da açık renk düz zemin tercih edilir",
                "duz_temiz": "düz ve temiz zemin"}
    items = [
        k("gorsel_adet_max", "En çok {} görsel"),
        k("gorsel_adet_min", "En az {} görsel (önerilen)"),
        k("gorsel_min_px", "En küçük boyut {} px"),
        k("gorsel_uzun_kenar_min", "Uzun kenar en az {} px"),
        k("gorsel_max_px", "En büyük boyut {} px"),
        k("gorsel_onerilen_px", "Önerilen boyut {} px"),
        k("gorsel_zoom_px", "Yakınlaştırma için uzun kenar {}+ px"),
        k("gorsel_oran", "En-boy oranı {}"),
        k("gorsel_dosya_turleri", "Dosya türü: {}"),
        k("gorsel_dosya_mb_max", "Dosya en çok {} MB"),
    ]
    z = R.deger(plat, "gorsel_zemin")
    if z:
        items.append(f"- [ ] Ana görsel zemini: {zemin_ad.get(z, z)}{R.etiket(plat, 'gorsel_zemin')}")
    items.append(k("gorsel_doluluk_min", "Ana görselde ürün karenin en az %{}'ini doldurur"))
    items.append(k("gorsel_yazi", "{}"))
    items += ["- [ ] Ürün net, kesik değil, ortada; gerçek rengi ve etiketi değişmemiş",
              "- [ ] Başkasının görseli değil (görsel hakkı ihlali bildirimi riski)"]
    return [i for i in items if i]


def platform_md(u: Urun, P: dict, plat: str, R: Kurallar, B: Bulgular, gorsel_sonuc: dict | None, csv_satir: int) -> str:
    L = [f"# {P['ad']} ilan taslağı: {u.marka} {tr_title(u.urun_tipi)}", "",
         f"> Pazaryeri İlan Kiti v{VERSION} · {dt.date.today().strftime('%d.%m.%Y')} · Taslak: yüklemeden önce oku, "
         f"\"{DOGRULA_NOTU}\" işaretli kuralları panelde kontrol et.", ""]
    L += ["## Başlık", "", "```text", P["baslik"], "```", "",
          f"{P['baslik_uzunluk']} / {P['baslik_max']} karakter{R.etiket(plat, 'baslik_max')}. Kalıp: "
          f"{' + '.join(x for x in (R.deger(plat, 'baslik_kalip') or []) if x not in (',', '-', '|'))}"
          f"{R.etiket(plat, 'baslik_kalip')}."]
    if P["dusen"]:
        L.append(f"Sığmadığı için çıkarılan: {', '.join(P['dusen'])}.")
    if P.get("alt_baslik"):
        L += ["", f"Alt başlık ({len(P['alt_baslik'])} / {R.deger(plat, 'alt_baslik_max')}){R.etiket(plat, 'alt_baslik_max')}:",
              "", "```text", P["alt_baslik"], "```"]
    nb = R.kural(plat, "baslik_marka_notu")
    if nb:
        L.append(f"Not: {nb['deger']}{R.etiket(plat, 'baslik_marka_notu')}")
    if P["varyantlar"]:
        L += ["", "Varyant başlıkları:", ""]
        for v, vt in P["varyantlar"]:
            etiket = ", ".join(f"{k}={s(val)}" for k, val in v.items() if k in ("beden", "renk"))
            L.append(f"- {etiket}: `{vt}` ({len(vt)})")
    L += ["", "## Öne çıkan maddeler", ""]
    madde_notu = R.kural(plat, "madde_alani")
    if madde_notu:
        L += [f"{madde_notu['deger']}{R.etiket(plat, 'madde_alani')}", ""]
    L += [f"{i}. {m}" for i, m in enumerate(P["maddeler"], 1)] or ["(madde yok)"]
    L += ["", "## Açıklama", ""]
    hn = R.kural(plat, "aciklama_html")
    L.append(f"Alan biçimi: {'HTML' if P['html_izin'] == 'evet' else 'düz metin'} · {len(P['aciklama_alan'])} karakter"
             + (f" / en çok {R.deger(plat, 'aciklama_max')}" if R.deger(plat, "aciklama_max") else "")
             + (R.etiket(plat, "aciklama_html") if hn else "") + ".")
    L += ["", "```text" if P["html_izin"] != "evet" else "```html", P["aciklama_alan"].rstrip(), "```", ""]
    if P["html_izin"] == "evet":
        L += ["<details><summary>Düz metin hali</summary>", "", "```text", P["aciklama_duz"].rstrip(), "```", "", "</details>", ""]
    L += ["## Özellik tablosu", "", "| Özellik | Değer |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in ozellik_satirlari(u)]
    if u.barkod:
        L.append(f"| Barkod | {u.barkod} |")
    if u.model_kodu:
        L.append(f"| Model kodu | {u.model_kodu} |")
    L += ["", "Kategoriye göre zorunlu özellikler panelde değişir; tabloda olmayan zorunlu alanı uydurma, ürüne bakıp doldur.", ""]
    L += ["## Arama kelimeleri", ""]
    if plat == "amazon":
        b = len(P["arama_terimleri"].encode("utf-8"))
        L += [f"Arka plan arama terimleri ({b} / {R.deger(plat, 'arama_terimi_bayt', 250)} bayt; Türkçe harfler 2 bayt sayılır)"
              f"{R.etiket(plat, 'arama_terimi_bayt')}:", "", "```text", P["arama_terimleri"], "```", "",
              "Başlıktaki kelimeler ve marka tekrar edilmedi; virgül gerekmez, boşluk yeter.", ""]
    else:
        an = R.kural(plat, "arama_alani")
        if an:
            L += [f"{an['deger']}{R.etiket(plat, 'arama_alani')}", ""]
    if P["kapsam"]:
        L += ["Kelimeler ek ve sıra fark etmeden arandı (\"hassas cilt sabunu\" = \"hassas ciltler için sabun\").", "",
              "| Kelime | Başlıkta | Açıklamada |", "|---|---|---|"]
        L += [f"| {k} | {'evet' if a else '-'} | {'evet' if b_ else '-'} |" for k, a, b_ in P["kapsam"]]
        eksik = [k for k, a, b_ in P["kapsam"] if not a and not b_]
        if eksik and plat != "amazon":
            L += ["", f"Hiçbir yerde geçmeyen: {', '.join(eksik)}. Doğal bir cümleyle açıklamaya ya da özelliklere ekle; "
                      "kelime yığını yapma."]
        L.append("")
    notlar = [(key, k) for key, k in ((R.p.get(plat) or {}).get("kurallar") or {}).items() if key.startswith("not_")]
    if notlar:
        L += ["## Platform notları", ""]
        L += [f"- {k['deger']}{R.etiket(plat, key)}" for key, k in notlar]
        L.append("")
    L += ["## Görsel kontrol listesi", ""] + gorsel_listesi_md(plat, R) + [""]
    if gorsel_sonuc and plat in gorsel_sonuc.get("platformlar", {}):
        sys.path.insert(0, str(HERE))
        import gorsel_kontrol as G

        L.append(G.platform_md(gorsel_sonuc, plat, R, "###"))
    elif u.gorseller:
        L += ["Görsel ölçümü yapılamadı (Pillow/numpy yok ya da dosya okunamadı). `gorsel_kontrol.py` ile ayrıca çalıştır.", ""]
    else:
        L += ["Görsel verilmedi. Görselleri `gorseller:` alanına ekle ya da `gorsel_kontrol.py` ile ayrıca ölç.", ""]
    if csv_satir:
        ck = R.kural(plat, "csv_kolonlar") or {}
        L += ["## Toplu yükleme hazırlık tablosu", "",
              f"`{plat}.csv` ({csv_satir} satır, UTF-8, `;` ayraçlı: Excel'de açılır). Sütun adları "
              f"{'platformun ' if ck.get('guven') == 'resmi' else 'yaygın '}şablon adlarına göre"
              f"{R.etiket(plat, 'csv_kolonlar')}. Platformun kendi kategori şablonunu panelden indir, değerleri oraya "
              "kopyala; kategoriye özel zorunlu sütunlar bu tabloda yoktur.", ""]
        if ck.get("not"):
            L += [f"Not: {ck['not']}", ""]
    bul = B.platform_icin(plat)
    L += ["## Denetim", ""]
    if not bul:
        L.append("Sorun bulunmadı.")
    for sev in SEVIYE_SIRA:
        for i in bul:
            if i["seviye"] == sev:
                L.append(f"- **{SEVIYE_AD[sev]}** · {i['alan']}: {i['mesaj']}")
    L += ["", "## Bu platformun kuralları ve kaynakları", "", "| Kural | Değer | Kaynak | Güven |", "|---|---|---|---|"]
    for key, k in ((R.p.get(plat) or {}).get("kurallar") or {}).items():
        val = k.get("deger")
        if isinstance(val, list):
            val = ", ".join(str(x.get("kolon", x)) if isinstance(x, dict) else str(x) for x in val)
        val = str(val).replace("|", "/").replace("\n", " ")
        if len(val) > 90:
            val = val[:87] + "..."
        guv = k.get("guven") + (f" · {DOGRULA_NOTU}" if R.dogrula_mi(plat, key) else "")
        L.append(f"| {key} | {val} | {k.get('kaynak')} ({k.get('tarih')}) | {guv} |")
    return "\n".join(L).rstrip() + "\n"


# ----------------------------------------------------------------- reklam etiketi kancası
def reklam_girdisi(u: Urun, hook: dict, P: dict | None) -> str:
    ind = hook.get("indirim") or {}
    kat = {"kozmetik": "kozmetik", "giyim": "giyim", "gida": "gida"}.get(u.kategori_grubu, "diger")
    metin = (P["baslik"] + "\n" + P["aciklama_duz"]) if P else u.aciklama

    def q(x):
        return json.dumps(s(x), ensure_ascii=False)

    def n(x):
        return "" if x is None else (f"{x:.2f}".rstrip("0").rstrip("."))

    L = ["# Reklam Etiketi Kontrolü girdisi: Pazaryeri İlan Kiti üretti.",
         f"# Çalıştır: python3 ~/.claude/skills/reklam-etiketi/scripts/kontrol.py reklam_kontrol.yaml  ({REKLAM_ETIKETI_URL})",
         "# Not: satıcının kendi pazaryeri ilanı. Etiket (ETK-*) maddeleri etkileyici reklamları içindir; burada indirim (FYT-*)",
         "# ve üstünlük/karşılaştırma (KRS-*) maddelerine bak. Bu bir hukuki görüş değildir.",
         "platform: diger", "bicim: gonderi", "hesap_turu: marka_kendi",
         f"yayin_tarihi: {q(ind.get('baslangic') or dt.date.today().isoformat())}",
         "ticari_iliski: hayir", f"reklam_veren: {q(u.marka)}", f"urun_kategorisi: {kat}",
         "aciklama: |"] + ["  " + x for x in (metin.strip().splitlines() or [""])] + [
         "ekran_yazilari: []", "yapay_zeka:", "  kullanildi: hayir", "  neler: []", "  gercek_kisi_kopyasi: hayir"]
    if ind:
        L += ["indirim:", f"  indirimli_fiyat: {n(ind.get('indirimli'))}", f"  onceki_fiyat: {n(ind.get('onceki'))}",
              f"  son_10_gun_en_dusuk: {n(ind.get('son10'))}", f"  baslangic: {q(ind.get('baslangic'))}",
              f"  bitis: {q(ind.get('bitis'))}", f"  stok_adedi: {ind.get('stok') or ''}", "  urun_turu: mal",
              f"  satis_kanali: {q(ind.get('kanal') or 'pazaryeri')}", f"  onceki_fiyat_kanali: {q(ind.get('kanal') or 'pazaryeri')}"]
    return "\n".join(L) + "\n"


def reklam_etiketi_bul() -> Path | None:
    for p in (Path.home() / ".claude/skills/reklam-etiketi/scripts/kontrol.py", SKILL_DIR.parent / "reklam-etiketi/scripts/kontrol.py"):
        if p.is_file():
            return p
    return None


# ----------------------------------------------------------------- komutlar
def cmd_doctor(a) -> int:
    ok = True
    print(f"Pazaryeri İlan Kiti v{VERSION}")
    v = sys.version_info
    print(f"{'ok ' if v >= (3, 8) else 'HATA'} Python {v.major}.{v.minor}.{v.micro}")
    ok &= v >= (3, 8)
    try:
        import yaml  # noqa: F401

        print("ok  PyYAML (isteğe bağlı)")
    except ImportError:
        print("ok  PyYAML yok: dahili YAML okuyucu kullanılacak")
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401

        print("ok  Pillow + numpy (görsel kontrolü)")
    except ImportError:
        print("UYARI Pillow/numpy yok: ilan üretimi çalışır, görsel kontrolü çalışmaz (pip install -r requirements.txt)")
    try:
        R = Kurallar()
        hatalar = R.dogrula()
        toplam, dog = R.say()
        if hatalar:
            ok = False
            print(f"HATA kural dosyası: {len(hatalar)} sorun")
            for h in hatalar[:20]:
                print("     -", h)
        else:
            print(f"ok  kural dosyası {RULES_PATH.name} (sürüm {R.d.get('surum')}, kurallar {R.d.get('kural_tarihi')}): "
                  f"{toplam} kural, hepsinde kaynak + tarih + güven; {dog} tanesi \"{DOGRULA_NOTU}\"")
            eski = (dt.date.today() - dt.date.fromisoformat(str(R.d.get("kural_tarihi")))).days
            if eski > 120:
                print(f"UYARI kurallar {eski} gün önce kontrol edildi: pazaryeri kuralları değişir, kaynakları yeniden oku")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"HATA kural dosyası okunamadı: {e}")
    # Türkçe testleri
    t = tr_title("el yapımı ılık ışık 100 g")
    print(f"{'ok ' if t == 'El Yapımı Ilık Işık 100 g' else 'HATA'} Türkçe başlık düzeni: {t}")
    ok &= t == "El Yapımı Ilık Işık 100 g"
    g_ok = gtin_gecerli("4006381333931") and not gtin_gecerli("4006381333932")
    print(f"{'ok ' if g_ok else 'HATA'} GTIN kontrol hanesi testi")
    ok &= g_ok
    re_yol = reklam_etiketi_bul()
    print(f"ok  Reklam Etiketi Kontrolü {'bulundu: ' + str(re_yol.parent.parent.name) if re_yol else 'kurulu değil (isteğe bağlı): ' + REKLAM_ETIKETI_URL}")
    print("DOCTOR OK" if ok else "DOCTOR: sorun var")
    return 0 if ok else 1


def cmd_yeni(a) -> int:
    sys.stdout.write(SABLON)
    return 0


def _yukle(path: str) -> Urun:
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"ürün dosyası yok: {path}")
    return Urun(load_yaml(p), p.resolve())


def _bulgu_yaz(B: Bulgular, plat_ad=None):
    for sev in SEVIYE_SIRA:
        for i in B.items:
            if i["seviye"] == sev:
                pl = f"[{plat_ad(i['platform'])}] " if i["platform"] and plat_ad else ""
                print(f"  {SEVIYE_AD[sev]:8} {pl}{i['alan']}: {i['mesaj']}")


def cmd_kontrol(a) -> int:
    R = Kurallar()
    try:
        u = _yukle(a.urun)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    B, hook = denetle(u, R)
    for plat in u.platformlar:
        platform_uret(u, plat, R, B)
    _bulgu_yaz(B, R.ad)
    if hook["gerekli"]:
        print(f"  REKLAM   indirim/üstünlük ifadesi var: `uret` reklam_kontrol.yaml yazar → {REKLAM_ETIKETI_URL}")
    print(f"KONTROL: DÜZELT {B.say('DUZELT')} · UYARI {B.say('UYARI')} · BİLGİ {B.say('BILGI')}")
    return 1 if B.say("DUZELT") else 0


def cmd_uret(a) -> int:
    R = Kurallar()
    try:
        u = _yukle(a.urun)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if a.platform:
        istek = [p.strip().lower() for p in a.platform.split(",")]
        bad = [p for p in istek if p not in PLATFORMLAR]
        if bad:
            print(f"bilinmeyen platform: {', '.join(bad)}", file=sys.stderr)
            return 2
        u.platformlar = [p for p in PLATFORMLAR if p in istek]
    out = Path(a.cikti).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    B, hook = denetle(u, R)

    gorsel_sonuc = None
    eksik_gorsel = [str(p) for p in u.gorseller if not p.is_file()]
    if eksik_gorsel:
        B.ekle("DUZELT", "gorseller", f"Görsel bulunamadı: {', '.join(eksik_gorsel)}")
    mevcut = [p for p in u.gorseller if p.is_file()]
    if mevcut and not a.gorsel_yok:
        try:
            import gorsel_kontrol as G

            gorsel_sonuc = G.kontrol_et(mevcut, u.platformlar, R)
            (out / "gorsel_rapor.md").write_text(G.rapor_md(gorsel_sonuc, R), encoding="utf-8")
        except SystemExit as e:
            B.ekle("BILGI", "gorseller", f"Görsel ölçümü atlandı: {e}")

    P_all = {}
    for plat in u.platformlar:
        P = platform_uret(u, plat, R, B)
        P_all[plat] = P
    satirlar = {}
    for plat, P in P_all.items():
        satirlar[plat] = csv_yaz(u, P, plat, R, out / f"{plat}.csv")
    for plat, P in P_all.items():
        (out / f"{plat}.md").write_text(platform_md(u, P, plat, R, B, gorsel_sonuc, satirlar[plat]), encoding="utf-8")

    # reklam etiketi kancası
    re_rapor = None
    if hook["gerekli"]:
        first = P_all[u.platformlar[0]] if u.platformlar else None
        (out / "reklam_kontrol.yaml").write_text(reklam_girdisi(u, hook, first), encoding="utf-8")
        yol = reklam_etiketi_bul()
        if yol and not a.reklam_yok:
            r = subprocess.run([sys.executable, str(yol), str(out / "reklam_kontrol.yaml"), "--cikti", str(out / "reklam_raporu.md")],
                               capture_output=True, text=True)
            re_rapor = out / "reklam_raporu.md" if (out / "reklam_raporu.md").exists() else None
            if r.returncode not in (0, 1):
                B.ekle("BILGI", "reklam", f"Reklam Etiketi Kontrolü çalışmadı: {r.stderr.strip()[:200]}")

    # görsel KALDI → özet bulgusu
    gorsel_kaldi = False
    if gorsel_sonuc:
        for plat, pl in gorsel_sonuc["platformlar"].items():
            tum = pl["set"] + [x for g in pl["gorsel"] for x in g["sonuclar"]]
            kal = [x for x in tum if x["durum"] == "KALDI"]
            if kal:
                gorsel_kaldi = True
                B.ekle("DUZELT", "görsel", f"{len(kal)} görsel kuralı KALDI ({', '.join(sorted({x['kontrol'] for x in kal}))}); "
                                           "ayrıntı platform dosyasında ve gorsel_rapor.md'de.", plat)

    ozet = ozet_md(u, P_all, R, B, hook, re_rapor, gorsel_sonuc, satirlar)
    (out / "ozet.md").write_text(ozet, encoding="utf-8")
    rapor = {"surum": VERSION, "tarih": dt.date.today().isoformat(), "urun": Path(a.urun).name,
             "platformlar": {p: {**{k: v for k, v in P.items() if k not in ("aciklama_alan", "kapsam", "varyantlar")},
                                 "varyant_basliklari": [vt for _, vt in P["varyantlar"]]} for p, P in P_all.items()},
             "bulgular": B.items, "reklam_kancasi": {"gerekli": hook["gerekli"], "metin_indirim": hook["metin_indirim"],
                                                       "ustunluk": hook["ustunluk"]}}
    (out / "rapor.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    for plat, P in P_all.items():
        print(f"{R.ad(plat):12} {P['baslik_uzunluk']:3}/{P['baslik_max']:<3} {P['baslik']}")
    _bulgu_yaz(B, R.ad)
    if hook["gerekli"]:
        print(f"REKLAM: indirim/üstünlük ifadesi → {out / 'reklam_kontrol.yaml'}"
              + (f" · rapor: {re_rapor}" if re_rapor else f" · Reklam Etiketi Kontrolü ile çalıştır: {REKLAM_ETIKETI_URL}"))
    print(f"ÇIKTI: {out} · DÜZELT {B.say('DUZELT')} · UYARI {B.say('UYARI')} · BİLGİ {B.say('BILGI')}")
    return 1 if (B.say("DUZELT") or gorsel_kaldi) else 0


def ozet_md(u, P_all, R, B, hook, re_rapor, gorsel_sonuc, satirlar) -> str:
    L = [f"# İlan özeti: {u.marka} {tr_title(u.urun_tipi)}", "",
         f"Pazaryeri İlan Kiti v{VERSION} · {dt.date.today().strftime('%d.%m.%Y')} · kurallar {R.d.get('kural_tarihi')} tarihli. "
         "Bu bir taslaktır; yükleme ve yayın satıcıya aittir.", "",
         "| Platform | Başlık | Karakter | Dosyalar |", "|---|---|---|---|"]
    for plat, P in P_all.items():
        dos = f"`{plat}.md`" + (f", `{plat}.csv`" if satirlar.get(plat) else "")
        L.append(f"| {P['ad']} | {P['baslik']} | {P['baslik_uzunluk']}/{P['baslik_max']} | {dos} |")
    L += ["", f"Sonuç: **DÜZELT {B.say('DUZELT')} · UYARI {B.say('UYARI')} · BİLGİ {B.say('BILGI')}**", ""]
    for sev in SEVIYE_SIRA:
        for i in B.items:
            if i["seviye"] == sev:
                pl = f"[{R.ad(i['platform'])}] " if i["platform"] else ""
                L.append(f"- **{SEVIYE_AD[sev]}** · {pl}{i['alan']}: {i['mesaj']}")
    if gorsel_sonuc:
        sys.path.insert(0, str(HERE))
        import gorsel_kontrol as G

        L += ["", "## Görseller", "", "| Platform | Sonuç (gözle kontrol hariç) |", "|---|---|"]
        for plat, pl in gorsel_sonuc["platformlar"].items():
            tum = pl["set"] + [x for g in pl["gorsel"] for x in g["sonuclar"]]
            L.append(f"| {R.ad(plat)} | {G.DURUM_AD[G.en_kotu([x for x in tum if x['durum'] != 'MANUEL'] or tum)]} |")
        L += ["", "Ayrıntı: `gorsel_rapor.md`. Yazı/filigran ve ürünün gerçeğe uygunluğunu gözle kontrol et."]
    if hook["gerekli"]:
        L += ["", "## İndirim / reklam uyarısı", "",
              "İlanda indirim (üstü çizili fiyat, yüzde, \"yerine\") ya da üstünlük iddiası var. 01.08.2026'dan beri indirimden "
              "önceki fiyat = indirimden önceki 10 günde aynı kanaldaki en düşük fiyat (Ticari Reklam ve Haksız Ticari "
              "Uygulamalar Yönetmeliği, RG 01.07.2026 / 33297, md.14/3 ve 14/5).",
              f"`reklam_kontrol.yaml` yazıldı: ücretsiz Reklam Etiketi Kontrolü ile denetle → {REKLAM_ETIKETI_URL}"
              + (f" · rapor: `{re_rapor.name}`" if re_rapor else ""), "Bu bir hukuki görüş değildir."]
    L += ["", "## Yüklemeden önce", "",
          f"- [ ] \"{DOGRULA_NOTU}\" işaretli kuralları satıcı panelinde kontrol et (kurallar ikincil kaynaktan).",
          "- [ ] Kategoriyi panelde seç; kategoriye özel zorunlu özellikleri ürüne bakarak doldur.",
          "- [ ] Barkodların gerçek ve benzersiz olduğundan emin ol.",
          "- [ ] Her görsele gözle bak: ürün, renk ve etiket gerçeğiyle aynı mı; yazı/filigran yok mu.",
          "- [ ] Fiyat ve indirim bilgisini kampanya tarihleriyle birlikte panelde gir."]
    return "\n".join(L) + "\n"


def cmd_kurallar(a) -> int:
    R = Kurallar()
    plats = [a.platform] if a.platform else PLATFORMLAR
    for plat in plats:
        if plat not in PLATFORMLAR:
            print(f"bilinmeyen platform: {plat}", file=sys.stderr)
            return 2
        print(f"\n== {R.ad(plat)} ==")
        for key, k in ((R.p.get(plat) or {}).get("kurallar") or {}).items():
            val = k.get("deger")
            if isinstance(val, list):
                val = ", ".join(str(x.get("kolon", x)) if isinstance(x, dict) else str(x) for x in val)
            flag = f"  [{DOGRULA_NOTU}]" if R.dogrula_mi(plat, key) else ""
            print(f"- {key}: {str(val)[:110]}{flag}\n    {k.get('kaynak')} · {k.get('guven')} · {k.get('tarih')}")
            if k.get("not") and a.ayrinti:
                print(f"    not: {k['not']}")
    hatalar = R.dogrula()
    toplam, dog = R.say()
    print(f"\n{toplam} kural · {dog} doğrulanacak · kural dosyası {'GEÇERLİ' if not hatalar else 'SORUNLU: ' + '; '.join(hatalar[:5])}")
    return 0 if not hatalar else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pazaryeri İlan Kiti: ürün bilgisinden Trendyol/Hepsiburada/n11/Amazon TR ilan taslağı.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="ortam ve kural dosyası kontrolü").set_defaults(fn=cmd_doctor)
    sub.add_parser("yeni", help="boş ürün dosyası (stdout)").set_defaults(fn=cmd_yeni)
    k = sub.add_parser("kontrol", help="ürün dosyasını denetle")
    k.add_argument("urun")
    k.set_defaults(fn=cmd_kontrol)
    u = sub.add_parser("uret", help="ilan taslaklarını üret")
    u.add_argument("urun")
    u.add_argument("--cikti", default="ilan_cikti")
    u.add_argument("--platform", help="virgülle: trendyol,hepsiburada,n11,amazon (varsayılan: dosyadaki liste)")
    u.add_argument("--gorsel-yok", action="store_true", help="görsel ölçümünü atla")
    u.add_argument("--reklam-yok", action="store_true", help="Reklam Etiketi Kontrolü'nü otomatik çalıştırma")
    u.set_defaults(fn=cmd_uret)
    r = sub.add_parser("kurallar", help="platform kuralları ve kaynakları")
    r.add_argument("--platform")
    r.add_argument("--ayrinti", action="store_true")
    r.set_defaults(fn=cmd_kurallar)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
