#!/usr/bin/env python3
"""Pazaryeri İlan Kiti: ürün görseli kontrolü (MIT, Redirhan Labs).

Her görseli ölçer ve seçilen pazaryerinin kurallarıyla (rules/platformlar.yaml) karşılaştırır:
  - çözünürlük (en/boy, en az / en çok / önerilen), en-boy oranı, dosya boyutu ve türü, renk modu, saydamlık
  - arka plan beyazlığı (kenar bandında saf beyaz % ve beyaza yakın %), ürün doluluğu (uzun kenar %, alan %),
    ortalama, ürünün kenara değmesi (kesik olabilir), ürün dışı ayrık öğeler (yazı/logo/filigran olabilir), netlik
  - görsel sayısı (en az / en çok)
İlk görsel "ana görsel" sayılır; beyaz zemin ve doluluk kuralları ona uygulanır.
Yazı/filigran tespiti sezgiseldir: şüpheli öğe bulursa "GÖZLE KONTROL" der; bulamazsa da gözle bakılmalıdır.

Kullanım:
  python3 gorsel_kontrol.py ana.jpg detay.jpg --platform trendyol
  python3 gorsel_kontrol.py klasor/ --platform hepsi --rapor gorsel_rapor.md --json gorsel_rapor.json
  python3 gorsel_kontrol.py ana.jpg --hazirla hazir/      # beyaz zeminli ana görseli her platformun önerilen
                                                          # boyutuna/oranına göre beyaz tuvale yerleştirir
Çıkış kodu: 0 = KALDI yok, 1 = en az bir KALDI, 2 = girdi hatası.
Gerekli: Pillow, numpy. Yerel çalışır; görseller hiçbir yere gönderilmez.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ortak import PLATFORMLAR, Kurallar  # noqa: E402

UZANTILAR = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif", ".heic"}
DURUM_AD = {"KALDI": "KALDI", "UYARI": "UYARI", "MANUEL": "GÖZLE KONTROL", "GECTI": "GEÇTİ", "BILGI": "BİLGİ"}
DURUM_SIRA = ["KALDI", "UYARI", "MANUEL", "BILGI", "GECTI"]

# eşikler (ölçüm yöntemi README'de)
SAF = 254          # JPEG toleransı: 254-255 saf beyaz sayılır
BEYAZA_YAKIN = 245
ON_PLAN_MIN = 235  # en küçük kanal bunun altındaysa ya da renkliyse ürün pikseli
RENKLI = 18


def _np():
    try:
        import numpy as np  # type: ignore
        from PIL import Image, ImageOps  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise SystemExit(f"Pillow ve numpy gerekli ({e}). Kurulum: pip install Pillow numpy") from e
    return np, Image, ImageOps


def gorselleri_topla(girdiler: list[str]) -> list[Path]:
    out: list[Path] = []
    for g in girdiler:
        p = Path(g).expanduser()
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if x.suffix.lower() in UZANTILAR and not x.name.startswith("."))
        elif p.is_file():
            out.append(p)
        else:
            raise FileNotFoundError(f"bulunamadı: {g}")
    return out


# ----------------------------------------------------------------- ölçüm
def _bilesenler(mask, np):
    """4-komşulu bağlı bileşenler (küçük ızgarada). [(alan, x0, y0, x1, y1), ...] büyükten küçüğe."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps = []
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        area, x0, y0, x1, y1 = 0, sx, sy, sx, sy
        while stack:
            y, x = stack.pop()
            area += 1
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        comps.append((area, x0, y0, x1, y1))
    comps.sort(reverse=True)
    return comps


def olc(path: Path) -> dict:
    np, Image, ImageOps = _np()
    path = Path(path)
    m: dict = {"dosya": str(path), "ad": path.name, "dosya_kb": round(path.stat().st_size / 1024, 1)}
    im = Image.open(path)
    m["tur"] = (im.format or path.suffix.lstrip(".")).upper()
    m["mod"] = im.mode
    dpi = im.info.get("dpi")
    m["dpi"] = round(float(dpi[0])) if dpi else None
    im = ImageOps.exif_transpose(im)
    W, H = im.size
    m["genislik"], m["yukseklik"] = W, H
    m["oran"] = round(W / H, 4)
    saydam = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    m["saydam"] = False
    if saydam:
        rgba = im.convert("RGBA")
        alpha = np.asarray(rgba.getchannel("A"))
        m["saydam"] = bool((alpha < 250).mean() > 0.001)
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, rgba)
    a = np.asarray(im.convert("RGB"), dtype=np.uint8)
    mn = a.min(axis=2)
    mx = a.max(axis=2)

    # kenar bandı: dört kenardan %2
    b = max(2, round(0.02 * min(W, H)))
    ring = np.zeros((H, W), dtype=bool)
    ring[:b, :] = ring[-b:, :] = True
    ring[:, :b] = ring[:, -b:] = True
    m["kenar_saf_beyaz_yuzde"] = round(float((mn[ring] >= SAF).mean() * 100), 1)
    m["kenar_beyaza_yakin_yuzde"] = round(float((mn[ring] >= BEYAZA_YAKIN).mean() * 100), 1)
    m["kenar_ortalama"] = [round(float(x)) for x in a[ring].mean(axis=0)]

    fg = (mn < ON_PLAN_MIN) | ((mx.astype(int) - mn.astype(int)) > RENKLI)
    m["on_plan_yuzde"] = round(float(fg.mean() * 100), 1)
    rows = fg.sum(axis=1)
    cols = fg.sum(axis=0)
    ry = np.nonzero(rows >= max(2, 0.003 * W))[0]
    cx = np.nonzero(cols >= max(2, 0.003 * H))[0]
    def kutu_olc(x0, y0, x1, y1):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        m["urun_kutusu"] = [x0, y0, x1, y1]
        m["doluluk_uzun_kenar_yuzde"] = round(max(bw / W, bh / H) * 100, 1)
        m["doluluk_alan_yuzde"] = round(bw * bh / (W * H) * 100, 1)
        m["merkez_kayma_yuzde"] = [round(((x0 + x1) / 2 - W / 2) / W * 100, 1), round(((y0 + y1) / 2 - H / 2) / H * 100, 1)]
        tol = max(1, round(0.004 * min(W, H)))
        m["kenara_degiyor"] = [k for k, v in (("sol", x0 <= tol), ("üst", y0 <= tol), ("sağ", x1 >= W - 1 - tol),
                                               ("alt", y1 >= H - 1 - tol)) if v]
        pad = round(0.01 * max(W, H))
        outside = np.ones((H, W), dtype=bool)
        outside[max(0, y0 - pad):y1 + pad + 1, max(0, x0 - pad):x1 + pad + 1] = False
        m["arka_plan_saf_beyaz_yuzde"] = round(float((mn[outside] >= SAF).mean() * 100), 1) if outside.any() else None

    if len(ry) and len(cx):
        kutu_olc(int(cx[0]), int(ry[0]), int(cx[-1]), int(ry[-1]))
    else:
        m["urun_kutusu"] = None
        m["doluluk_uzun_kenar_yuzde"] = m["doluluk_alan_yuzde"] = 0.0
        m["merkez_kayma_yuzde"] = [0.0, 0.0]
        m["kenara_degiyor"] = []
        m["arka_plan_saf_beyaz_yuzde"] = round(float((mn >= SAF).mean() * 100), 1)

    # ayrık öğeler: yalnız zemin beyazsa anlamlı (yaşam görselinde her şey ön plan)
    m["ayrik_ogeler"] = []
    if m["kenar_beyaza_yakin_yuzde"] >= 90 and m["urun_kutusu"]:
        step = max(1, round(max(W, H) / 320))
        hh, ww = H // step, W // step
        small = fg[: hh * step, : ww * step].reshape(hh, step, ww, step).any(axis=(1, 3))
        comps = _bilesenler(small, np)
        if comps:
            big = comps[0]
            gx = 0.04 * ww
            gy = 0.04 * hh
            for area, a0, b0, a1, b1 in comps[1:]:
                if area < 3:
                    continue
                ayrik = a1 < big[1] - gx or a0 > big[3] + gx or b1 < big[2] - gy or b0 > big[4] + gy
                if ayrik:
                    m["ayrik_ogeler"].append({"kutu": [a0 * step, b0 * step, (a1 + 1) * step, (b1 + 1) * step],
                                              "alan_yuzde": round(area / (ww * hh) * 100, 2)})
        m["ayrik_ogeler"] = m["ayrik_ogeler"][:10]
        if m["ayrik_ogeler"]:
            # ürün kutusu = en büyük bileşen (yazı/etiket doluluğu şişirmesin)
            big = comps[0]
            kutu_olc(big[1] * step, big[2] * step, min(W - 1, (big[3] + 1) * step - 1), min(H - 1, (big[4] + 1) * step - 1))

    # netlik: Laplace varyansı, uzun kenar 1000 px'e indirilmiş gri görüntüde, yalnız ürün piksellerinde
    s = min(1.0, 1000 / max(W, H))
    rgb_s = im.convert("RGB")
    if s < 1:
        rgb_s = rgb_s.resize((max(3, round(W * s)), max(3, round(H * s))), Image.BOX)
    sa = np.asarray(rgb_s, dtype=np.int16)
    smn, smx = sa.min(axis=2), sa.max(axis=2)
    sfg = (smn < ON_PLAN_MIN) | ((smx - smn) > RENKLI)
    ga = np.asarray(rgb_s.convert("L"), dtype=np.float32)
    lap = (-4 * ga[1:-1, 1:-1] + ga[:-2, 1:-1] + ga[2:, 1:-1] + ga[1:-1, :-2] + ga[1:-1, 2:])
    sel = sfg[1:-1, 1:-1]
    m["netlik"] = round(float(lap[sel].var() if sel.sum() > 100 else lap.var()), 1)
    return m


# ----------------------------------------------------------------- değerlendirme
def _oran_deger(s) -> float | None:
    if not s:
        return None
    s = str(s).replace("x", ":").replace("/", ":")
    try:
        a, b = s.split(":")
        return float(a) / float(b)
    except ValueError:
        return None


def _boyut(s):
    """'1200x1800' -> (1200, 1800)."""
    if not s:
        return None
    try:
        w, h = str(s).lower().replace("×", "x").split("x")
        return int(w), int(h)
    except ValueError:
        return None


def degerlendir(m: dict, plat: str, R: Kurallar, ana: bool) -> list[dict]:
    out: list[dict] = []

    def add(kontrol, durum, mesaj, key=None):
        k = R.kural(plat, key) if key else None
        if durum == "KALDI" and isinstance(k, dict) and k.get("guven") != "resmi":
            durum = "UYARI"  # ikincil/tahmin kurala dayanarak "kaldı" deme
        if key and durum in ("KALDI", "UYARI", "GECTI") and R.dogrula_mi(plat, key):
            mesaj += R.etiket(plat, key)
        out.append({"kontrol": kontrol, "durum": durum, "mesaj": mesaj})

    W, H = m["genislik"], m["yukseklik"]
    # çözünürlük
    mn_ = _boyut(R.deger(plat, "gorsel_min_px"))
    if mn_:
        ok = W >= mn_[0] and H >= mn_[1]
        add("En küçük boyut", "GECTI" if ok else "KALDI", f"{W}x{H}; en az {mn_[0]}x{mn_[1]}", "gorsel_min_px")
    uk = R.deger(plat, "gorsel_uzun_kenar_min")
    if uk:
        ok = max(W, H) >= int(uk)
        add("Uzun kenar", "GECTI" if ok else "KALDI", f"uzun kenar {max(W, H)} px; en az {uk} px", "gorsel_uzun_kenar_min")
    mx_ = _boyut(R.deger(plat, "gorsel_max_px"))
    if mx_:
        ok = W <= mx_[0] and H <= mx_[1]
        add("En büyük boyut", "GECTI" if ok else "KALDI", f"{W}x{H}; en çok {mx_[0]}x{mx_[1]}" +
            ("" if ok else " (küçült: --hazirla)"), "gorsel_max_px")
    onr = _boyut(R.deger(plat, "gorsel_onerilen_px"))
    if onr:
        ok = W >= onr[0] and H >= onr[1]
        tahmin = (R.kural(plat, "gorsel_onerilen_px") or {}).get("guven") == "tahmin"
        add("Önerilen boyut", "GECTI" if ok else ("BILGI" if tahmin else "UYARI"),
            f"{W}x{H}; önerilen {onr[0]}x{onr[1]}" + (" (bizim önerimiz)" if tahmin else ""), "gorsel_onerilen_px")
    zoom = R.deger(plat, "gorsel_zoom_px")
    if zoom:
        ok = max(W, H) >= int(zoom)
        add("Yakınlaştırma", "GECTI" if ok else "UYARI",
            f"uzun kenar {max(W, H)} px; yakınlaştırma için {zoom}+ px önerilir", "gorsel_zoom_px")
    oran = _oran_deger(R.deger(plat, "gorsel_oran"))
    if oran:
        fark = abs(m["oran"] - oran) / oran
        add("En-boy oranı", "GECTI" if fark <= 0.02 else "UYARI",
            f"{W}:{H} = {m['oran']:.3f}; beklenen {R.deger(plat, 'gorsel_oran')} = {oran:.3f}" +
            ("" if fark <= 0.02 else (" (beyaz tuvale yerleştir: --hazirla)" if m["kenar_beyaza_yakin_yuzde"] >= 90
                                      else " (kırp ya da yeniden çek)")), "gorsel_oran")
    # dosya
    mb = R.deger(plat, "gorsel_dosya_mb_max")
    if mb:
        ok = m["dosya_kb"] <= float(mb) * 1024
        add("Dosya boyutu", "GECTI" if ok else "KALDI", f"{m['dosya_kb']:.0f} KB; en çok {mb} MB", "gorsel_dosya_mb_max")
    turler = R.deger(plat, "gorsel_dosya_turleri")
    if turler:
        t = "JPEG" if m["tur"] in ("JPG", "JPEG", "MPO") else m["tur"]
        izin = {("JPEG" if x.upper() in ("JPG", "JPEG") else x.upper()) for x in turler}
        add("Dosya türü", "GECTI" if t in izin else "KALDI", f"{t}; izinli: {', '.join(sorted(izin))}", "gorsel_dosya_turleri")
    if m["mod"] in ("CMYK", "I;16", "I", "F"):
        add("Renk modu", "UYARI", f"{m['mod']}: sRGB JPEG olarak kaydet (renkler kayabilir)")
    if m["saydam"]:
        add("Saydamlık", "UYARI", "saydam arka plan: pazaryeri beyaz göstermeyebilir; beyaz zeminli JPEG kaydet")

    if ana:
        zemin = R.deger(plat, "gorsel_zemin")
        ks, ky = m["kenar_saf_beyaz_yuzde"], m["kenar_beyaza_yakin_yuzde"]
        bg = m.get("arka_plan_saf_beyaz_yuzde")
        bilgi = f"kenar bandı saf beyaz %{ks}, beyaza yakın %{ky}" + (f"; ürün dışı alan saf beyaz %{bg}" if bg is not None else "")
        if zemin == "saf_beyaz":
            d = "GECTI" if ks >= 98 and (bg is None or bg >= 95) else ("UYARI" if ky >= 90 else "KALDI")
            add("Beyaz zemin (saf 255)", d, bilgi, "gorsel_zemin")
        elif zemin in ("beyaz_tercih", "duz_temiz"):
            d = "GECTI" if ky >= 95 else "UYARI"
            add("Beyaz / açık zemin", d, bilgi + (" — zemin beyaz değil; ana görselde beyaz ya da açık düz zemin tercih edilir"
                                                   if d == "UYARI" else ""), "gorsel_zemin")
        dol = R.deger(plat, "gorsel_doluluk_min")
        dl = m["doluluk_uzun_kenar_yuzde"]
        beyaz_zemin = ky >= 90
        if dol and beyaz_zemin:
            d = "GECTI" if dl >= float(dol) else ("UYARI" if dl >= float(dol) - 15 else "KALDI")
            add("Ürün doluluğu", d, f"ürün uzun kenarda %{dl} (alan %{m['doluluk_alan_yuzde']}); en az %{dol}", "gorsel_doluluk_min")
        elif beyaz_zemin:
            d = "GECTI" if 70 <= dl <= 97 else "UYARI"
            add("Ürün doluluğu", d, f"ürün uzun kenarda %{dl}; önerimiz %80-90 (çok küçük ürün aramada kaybolur)")
        if beyaz_zemin and m["kenara_degiyor"]:
            add("Kesik ürün", "UYARI", f"ürün {', '.join(m['kenara_degiyor'])} kenara değiyor: kesik görünebilir, kenar payı bırak")
        if beyaz_zemin:
            kx, ky2 = m["merkez_kayma_yuzde"]
            if abs(kx) > 8 or abs(ky2) > 8:
                add("Ortalama", "UYARI", f"ürün merkezden kaymış (yatay %{kx}, dikey %{ky2})")
    if m["ayrik_ogeler"]:
        add("Yazı / logo / filigran", "MANUEL",
            f"üründen ayrık {len(m['ayrik_ogeler'])} öğe bulundu (ilk: {m['ayrik_ogeler'][0]['kutu']}); yazı, fiyat, logo, "
            "filigran ya da çerçeve olabilir. Gözle bak", "gorsel_yazi")
    else:
        add("Yazı / logo / filigran", "MANUEL", "ayrık öğe bulunmadı; ürünün üstündeki yazı/filigranı script göremez, gözle bak")
    if m.get("netlik") is not None and m["netlik"] < 15:
        add("Netlik", "UYARI", f"Laplace varyansı {m['netlik']}: bulanık olabilir, gözle bak")
    return out


def set_degerlendir(n: int, plat: str, R: Kurallar) -> list[dict]:
    out = []
    amin, amax = R.deger(plat, "gorsel_adet_min"), R.deger(plat, "gorsel_adet_max")
    if amax:
        d = "GECTI" if n <= int(amax) else ("KALDI" if (R.kural(plat, "gorsel_adet_max") or {}).get("guven") == "resmi" else "UYARI")
        out.append({"kontrol": "Görsel sayısı (en çok)", "durum": d,
                    "mesaj": f"{n} görsel; en çok {amax}" + R.etiket(plat, "gorsel_adet_max")})
    if amin:
        d = "GECTI" if n >= int(amin) else "UYARI"
        out.append({"kontrol": "Görsel sayısı (en az / önerilen)", "durum": d,
                    "mesaj": f"{n} görsel; en az {amin}" + R.etiket(plat, "gorsel_adet_min")})
    return out


def kontrol_et(gorseller: list[Path], platformlar: list[str], R: Kurallar) -> dict:
    olcumler = [olc(p) for p in gorseller]
    sonuc = {"gorseller": olcumler, "platformlar": {}}
    for plat in platformlar:
        pl = {"set": set_degerlendir(len(gorseller), plat, R), "gorsel": []}
        for i, m in enumerate(olcumler):
            pl["gorsel"].append({"ad": m["ad"], "ana": i == 0, "sonuclar": degerlendir(m, plat, R, ana=(i == 0))})
        sonuc["platformlar"][plat] = pl
    return sonuc


def en_kotu(sonuclar: list[dict]) -> str:
    for d in DURUM_SIRA:
        if any(s["durum"] == d for s in sonuclar):
            return d
    return "GECTI"


def platform_md(sonuc: dict, plat: str, R: Kurallar, baslik_seviye: str = "###") -> str:
    pl = sonuc["platformlar"][plat]
    lines = [f"{baslik_seviye} {R.ad(plat)}: görsel kontrolü", ""]
    for s in pl["set"]:
        lines.append(f"- **{DURUM_AD[s['durum']]}** · {s['kontrol']}: {s['mesaj']}")
    for g in pl["gorsel"]:
        lines += ["", f"**{g['ad']}**{' (ana görsel)' if g['ana'] else ''} → {DURUM_AD[en_kotu(g['sonuclar'])]}", "",
                  "| Kontrol | Durum | Ayrıntı |", "|---|---|---|"]
        for s in g["sonuclar"]:
            lines.append(f"| {s['kontrol']} | {DURUM_AD[s['durum']]} | {s['mesaj']} |")
    return "\n".join(lines) + "\n"


def rapor_md(sonuc: dict, R: Kurallar) -> str:
    lines = ["# Görsel kontrol raporu", "",
             "Ölçümler yerel, sezgisel ve yaklaşık. Yazı/filigran ve ürünün gerçeğe uygunluğu için her görsele gözle bak.",
             "\"satıcı panelinden doğrula\" işaretli kurallar ikincil kaynaktan; yüklemeden önce satıcı panelinde kontrol et.",
             "", "## Ölçümler", "",
             "| Görsel | Boyut | Oran | KB | Kenar saf beyaz % | Beyaza yakın % | Doluluk (uzun kenar) % | Ayrık öğe | Netlik |",
             "|---|---|---|---|---|---|---|---|---|"]
    for m in sonuc["gorseller"]:
        lines.append(f"| {m['ad']} | {m['genislik']}x{m['yukseklik']} | {m['oran']:.3f} | {m['dosya_kb']:.0f} | "
                     f"{m['kenar_saf_beyaz_yuzde']} | {m['kenar_beyaza_yakin_yuzde']} | {m['doluluk_uzun_kenar_yuzde']} | "
                     f"{len(m['ayrik_ogeler'])} | {m['netlik']} |")
    lines.append("")
    for plat in sonuc["platformlar"]:
        lines.append(platform_md(sonuc, plat, R, "##"))
    return "\n".join(lines)


# ----------------------------------------------------------------- hazırlama
def hazirla(path: Path, platformlar: list[str], R: Kurallar, cikti: Path, doluluk: float = 0.85) -> list[str]:
    """Beyaz zeminli ana görseli her platformun önerilen boyutuna yerleştirir (saf beyaz tuval, ürün ortada)."""
    np, Image, ImageOps = _np()
    m = olc(path)
    notlar = []
    if m["kenar_beyaza_yakin_yuzde"] < 90 or not m["urun_kutusu"]:
        return [f"{path.name}: zemin beyaz değil (kenar beyaza yakın %{m['kenar_beyaza_yakin_yuzde']}); otomatik "
                "yerleştirme yapılmadı. Önce dekupe (arka plan temizleme) gerekir."]
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    x0, y0, x1, y1 = m["urun_kutusu"]
    pad = round(0.01 * max(im.size))
    crop = im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad + 1), min(im.height, y1 + pad + 1)))
    # kırpıntının kenarındaki beyaza yakın pikselleri saf beyaza çek (zemin 250-254 ise)
    arr = np.asarray(crop).copy()
    near = arr.min(axis=2) >= 250
    arr[near] = 255
    crop = Image.fromarray(arr)
    cikti.mkdir(parents=True, exist_ok=True)
    yapilan = set()
    for plat in platformlar:
        hedef = _boyut(R.deger(plat, "gorsel_onerilen_px"))
        if not hedef:
            continue
        if hedef in yapilan:
            notlar.append(f"{R.ad(plat)}: {hedef[0]}x{hedef[1]} zaten üretildi")
            continue
        yapilan.add(hedef)
        TW, TH = hedef
        s = min(TW * doluluk / crop.width, TH * doluluk / crop.height)
        nw, nh = max(1, round(crop.width * s)), max(1, round(crop.height * s))
        urun = crop.resize((nw, nh), Image.LANCZOS)
        tuval = Image.new("RGB", (TW, TH), (255, 255, 255))
        tuval.paste(urun, ((TW - nw) // 2, (TH - nh) // 2))
        out = cikti / f"{path.stem}_{TW}x{TH}.jpg"
        tuval.save(out, "JPEG", quality=92, optimize=True, dpi=(96, 96))
        n = f"{out.name}: {TW}x{TH}, ürün uzun kenarda %{round(doluluk * 100)}"
        if s > 1.6:
            n += f" (görsel {s:.1f} kat büyütüldü: netlik düşebilir, daha büyük kaynak fotoğraf kullan)"
        notlar.append(n)
    return notlar


# ----------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pazaryeri ürün görseli kontrolü (yerel).")
    ap.add_argument("gorseller", nargs="+", help="görsel dosyaları ya da klasör (ilk görsel = ana görsel)")
    ap.add_argument("--platform", default="hepsi", help="trendyol | hepsiburada | n11 | amazon | hepsi (virgülle birden çok)")
    ap.add_argument("--rapor", help="Markdown rapor dosyası")
    ap.add_argument("--json", help="JSON çıktı dosyası")
    ap.add_argument("--hazirla", metavar="KLASOR", help="ana görseli platformların önerilen boyutuna yerleştir")
    ap.add_argument("--doluluk", type=float, default=0.85, help="--hazirla için ürün doluluğu (0.5-0.95, varsayılan 0.85)")
    ap.add_argument("--kurallar", default=None, help="farklı kural dosyası")
    a = ap.parse_args(argv)
    R = Kurallar(a.kurallar) if a.kurallar else Kurallar()
    plats = PLATFORMLAR if a.platform == "hepsi" else [p.strip() for p in a.platform.split(",")]
    for p in plats:
        if p not in PLATFORMLAR:
            print(f"bilinmeyen platform: {p}", file=sys.stderr)
            return 2
    try:
        gorseller = gorselleri_topla(a.gorseller)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if not gorseller:
        print("görsel bulunamadı", file=sys.stderr)
        return 2
    sonuc = kontrol_et(gorseller, plats, R)
    md = rapor_md(sonuc, R)
    for out in (a.rapor, a.json):
        if out:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
    if a.rapor:
        Path(a.rapor).write_text(md, encoding="utf-8")
        print(f"rapor: {a.rapor}")
    else:
        print(md)
    if a.json:
        Path(a.json).write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.hazirla:
        for n in hazirla(gorseller[0], plats, R, Path(a.hazirla), max(0.5, min(0.95, a.doluluk))):
            print("hazırla:", n)
    kaldi = any(s["durum"] == "KALDI" for pl in sonuc["platformlar"].values()
                for s in pl["set"] + [x for g in pl["gorsel"] for x in g["sonuclar"]])
    ozet = []
    for plat, pl in sonuc["platformlar"].items():
        tum = pl["set"] + [x for g in pl["gorsel"] for x in g["sonuclar"]]
        ozet.append(f"{R.ad(plat)}: {DURUM_AD[en_kotu([s for s in tum if s['durum'] != 'MANUEL'] or tum)]}")
    print("GÖRSEL ÖZETİ: " + " · ".join(ozet))
    return 1 if kaldi else 0


if __name__ == "__main__":
    sys.exit(main())
