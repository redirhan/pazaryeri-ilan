"""Pazaryeri İlan Kiti testleri (stdlib unittest). Çalıştır: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ilan  # noqa: E402
from ortak import Kurallar, load_yaml, tr_title, tr_upper  # noqa: E402

R = Kurallar()


def urun(**kw):
    d = {"marka": "Deneme Marka", "urun_tipi": "kupa", "temel_ozellikler": ["el yapımı", "seramik"], "miktar": "350 ml"}
    d.update(kw)
    return ilan.Urun(d, ROOT / "tests" / "x.yaml")


class TurkceTest(unittest.TestCase):
    def test_title(self):
        self.assertEqual(tr_title("ılık işlem için 100 g"), "Ilık İşlem için 100 g")
        self.assertEqual(tr_title("bisiklet yaka XL"), "Bisiklet Yaka XL")
        self.assertEqual(tr_upper("istanbul"), "İSTANBUL")

    def test_gtin(self):
        self.assertTrue(ilan.gtin_gecerli("4006381333931"))
        self.assertFalse(ilan.gtin_gecerli("4006381333932"))
        self.assertFalse(ilan.gtin_gecerli("ABC123"))


class KuralTest(unittest.TestCase):
    def test_kural_dosyasi(self):
        self.assertEqual(R.dogrula(), [])

    def test_her_platformda_baslik_sinir(self):
        for p in ilan.PLATFORMLAR:
            self.assertIsInstance(R.deger(p, "baslik_max"), int, p)


class BaslikTest(unittest.TestCase):
    def test_sinira_sigar_ve_dusurur(self):
        u = urun(temel_ozellikler=[f"özellik{i} renkli{i} desenli{i}" for i in range(12)])
        for p in ilan.PLATFORMLAR:
            t, dusen = ilan.baslik_uret(u, p, R)
            self.assertLessEqual(len(t), R.deger(p, "baslik_max"), p)
            self.assertTrue(dusen, p)
            self.assertIn("Kupa", t)

    def test_tekrar_atilir(self):
        u = urun(temel_ozellikler=["seramik", "seramik kupa"])
        t, _ = ilan.baslik_uret(u, "hepsiburada", R)
        self.assertEqual(t.lower().count("seramik"), 1)
        self.assertEqual(t.lower().count("kupa"), 1)

    def test_amazon_bayt(self):
        u = urun(anahtar_kelimeler=["şık çay bardağı ığdır öğütücü " * 20])
        s, _ = ilan.amazon_arama_terimi(u, "Deneme Marka Kupa", 250)
        self.assertLess(len(s.encode("utf-8")), 250)


class DenetimTest(unittest.TestCase):
    def test_on_gun_kurali(self):
        u = urun(fiyat={"satis": 80, "liste": 120},
                 indirim={"onceki_fiyat": 120, "indirimli_fiyat": 80, "son_10_gun_en_dusuk": 100,
                          "baslangic": "2026-11-01", "bitis": "2026-11-07"})
        B, hook = ilan.denetle(u, R)
        self.assertTrue(hook["gerekli"])
        msg = [i["mesaj"] for i in B.items if i["seviye"] == "DUZELT" and i["alan"] == "indirim"]
        self.assertTrue(msg and "%20" in msg[0], msg)

    def test_iletisim_ve_promo(self):
        u = urun(aciklama="Sipariş için WhatsApp 0532 123 45 67 ya da www.ornek.com", temel_ozellikler=["ücretsiz kargo"])
        B, _ = ilan.denetle(u, R)
        duzelt = " ".join(i["mesaj"] for i in B.items if i["seviye"] == "DUZELT")
        for parca in ("Telefon", "URL", "whatsapp", "ücretsiz kargo"):
            self.assertIn(parca.lower(), duzelt.lower())

    def test_ornekler_yuklenir(self):
        for f in sorted((ROOT / "examples").glob("*/urun.yaml")):
            u = ilan.Urun(load_yaml(f), f)
            self.assertTrue(u.marka and u.urun_tipi, f)


if __name__ == "__main__":
    unittest.main()
