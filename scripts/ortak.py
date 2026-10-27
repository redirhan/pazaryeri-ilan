"""Pazaryeri İlan Kiti: ortak yardımcılar (MIT, Redirhan Labs).

YAML okuma (PyYAML yoksa dahili okuyucu), kural dosyası erişimi ve Türkçe harf işlemleri.
Yalnız Python standart kütüphanesi.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
RULES_PATH = SKILL_DIR / "rules" / "platformlar.yaml"
PLATFORMLAR = ["trendyol", "hepsiburada", "n11", "amazon"]
GUVEN = {"resmi", "ikincil", "tahmin"}
DOGRULA_NOTU = "satıcı panelinden doğrula"


# ----------------------------------------------------------------- YAML
def load_yaml(path):
    path = Path(path)
    try:
        import yaml  # type: ignore

        with open(path, encoding="utf-8") as fh:
            return _stringify_dates(yaml.safe_load(fh))
    except ImportError:
        sys.path.insert(0, str(HERE))
        import mini_yaml  # type: ignore

        return mini_yaml.load(path)


def _stringify_dates(obj):
    import datetime as _dt

    if isinstance(obj, dict):
        return {k: _stringify_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_dates(v) for v in obj]
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    return obj


# ----------------------------------------------------------------- kurallar
class Kurallar:
    """rules/platformlar.yaml erişimi. Her kural: deger + kaynak + tarih + guven (+ not, dogrula)."""

    def __init__(self, path: Path | str = RULES_PATH):
        self.path = Path(path)
        self.d = load_yaml(self.path)
        self.p = self.d.get("platformlar") or {}
        self.ortak = self.d.get("ortak") or {}

    def ad(self, plat: str) -> str:
        return (self.p.get(plat) or {}).get("ad", plat)

    def kural(self, plat: str, key: str):
        return ((self.p.get(plat) or {}).get("kurallar") or {}).get(key)

    def deger(self, plat: str, key: str, default=None):
        k = self.kural(plat, key)
        if not isinstance(k, dict) or k.get("deger") is None:
            return default
        return k["deger"]

    def dogrula_mi(self, plat: str, key: str) -> bool:
        k = self.kural(plat, key)
        if not isinstance(k, dict):
            return True
        return k.get("guven") != "resmi" or str(k.get("dogrula", "")).lower() in ("evet", "true", "1")

    def etiket(self, plat: str, key: str) -> str:
        """Kuralın güven etiketi: '' (resmi) ya da ' [satıcı panelinden doğrula]'."""
        k = self.kural(plat, key)
        if not isinstance(k, dict):
            return ""
        return f" [{DOGRULA_NOTU}]" if self.dogrula_mi(plat, key) else ""

    def kaynak(self, plat: str, key: str) -> str:
        k = self.kural(plat, key) or {}
        return f"{k.get('kaynak', '?')} ({k.get('guven', '?')}, {k.get('tarih', '?')})"

    def ortak_deger(self, key: str, default=None):
        k = self.ortak.get(key)
        if isinstance(k, dict) and "deger" in k:
            return k["deger"]
        return default if k is None else k

    def dogrula(self) -> list[str]:
        """Kural dosyası denetimi: her kural kaynak + tarih + güven taşımalı."""
        hatalar = []
        if not self.p:
            return ["platformlar bölümü yok"]
        for plat in PLATFORMLAR:
            if plat not in self.p:
                hatalar.append(f"{plat}: platform yok")
                continue
            for key, k in ((self.p[plat] or {}).get("kurallar") or {}).items():
                yer = f"{plat}.{key}"
                if not isinstance(k, dict):
                    hatalar.append(f"{yer}: sözlük değil")
                    continue
                for alan in ("deger", "kaynak", "tarih", "guven"):
                    if k.get(alan) in (None, ""):
                        hatalar.append(f"{yer}: '{alan}' eksik")
                if k.get("guven") not in GUVEN:
                    hatalar.append(f"{yer}: guven '{k.get('guven')}' (resmi | ikincil | tahmin olmalı)")
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(k.get("tarih", ""))):
                    hatalar.append(f"{yer}: tarih YYYY-AA-GG olmalı")
                src = str(k.get("kaynak", ""))
                if not (src.startswith("http") or src.startswith("yok:")):
                    hatalar.append(f"{yer}: kaynak URL değil (kaynak yoksa 'yok: açıklama' yaz)")
        for key, k in self.ortak.items():
            if isinstance(k, dict) and "deger" in k:
                for alan in ("kaynak", "tarih", "guven"):
                    if k.get(alan) in (None, ""):
                        hatalar.append(f"ortak.{key}: '{alan}' eksik")
        return hatalar

    def say(self) -> tuple[int, int]:
        toplam = dogrulanacak = 0
        for plat in PLATFORMLAR:
            for key in ((self.p.get(plat) or {}).get("kurallar") or {}):
                toplam += 1
                dogrulanacak += self.dogrula_mi(plat, key)
        return toplam, dogrulanacak


# ----------------------------------------------------------------- Türkçe harf
_UP = str.maketrans({"i": "İ", "ı": "I"})
_LO = str.maketrans({"I": "ı", "İ": "i"})


def tr_upper(s: str) -> str:
    return s.translate(_UP).upper()


def tr_lower(s: str) -> str:
    return s.translate(_LO).lower()


def fold(s: str) -> str:
    """Karşılaştırma anahtarı: küçük harf, Türkçe işaretsiz."""
    s = tr_lower(s)
    s = s.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


KUCUK_KELIMELER = {"ve", "ile", "için", "veya", "ya", "da", "de", "ki"}
BIRIMLER = {"g", "gr", "kg", "mg", "ml", "cl", "lt", "l", "cm", "mm", "m", "mt", "adet", "li", "lı", "lu", "lü",
            "x", "w", "v", "mah", "gb", "tb", "oz"}


def _cap_word(w: str) -> str:
    if not w:
        return w
    # kesme işaretinden sonrası küçük kalır: Türkiye'nin
    m = re.match(r"^([^'’]+)(['’].*)?$", w)
    head, tail = (m.group(1), m.group(2) or "") if m else (w, "")
    if "-" in head:
        return "-".join(_cap_word(x) for x in head.split("-")) + tr_lower(tail)
    return tr_upper(head[:1]) + tr_lower(head[1:]) + tr_lower(tail)


def tr_title(s: str, koru: set[str] | None = None) -> str:
    """Türkçe başlık düzeni: her kelimenin ilk harfi büyük (İ/ı doğru), bağlaçlar ve birimler küçük,
    rakam içeren ve kısa kısaltma (XL, LED, USB) kelimeleri olduğu gibi kalır. koru: dokunulmayacak kelimeler."""
    koru = {fold(k) for k in (koru or set())}
    out = []
    for i, w in enumerate(s.split()):
        f = fold(w)
        if f in koru:
            out.append(w)
        elif any(ch.isdigit() for ch in w):
            out.append(w)
        elif w.isupper() and len(w) <= 4 and w.isalpha():
            out.append(w)
        elif i > 0 and f.strip(".,") in {fold(x) for x in KUCUK_KELIMELER}:
            out.append(tr_lower(w))
        elif f in BIRIMLER and i > 0:
            out.append(tr_lower(w))
        else:
            out.append(_cap_word(w))
    return " ".join(out)


def tr_sentence(s: str) -> str:
    s = s.strip()
    return tr_upper(s[:1]) + s[1:] if s else s


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF⭐⬆↔-↪️]")
