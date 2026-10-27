---
name: pazaryeri-ilan
description: Küçük e-ticaret satıcısı için ürün bilgisinden (isteğe bağlı fotoğraflarla) Trendyol, Hepsiburada, n11 ve Amazon.com.tr ilan taslağı hazırlar - platform sınırına ve kalıbına uygun başlık (marka + ürün + temel özellikler), öne çıkan maddeler, açıklama, özellik tablosu, arama kelimeleri, görsel kontrol listesi ve toplu yükleme hazırlık CSV'si. Görsel kontrol script'i fotoğrafları ölçer (beyaz zemin %, ürün doluluğu %, çözünürlük, oran, yazı/logo şüphesi) ve beyaz zeminli görseli platform ölçüsüne yerleştirir. İndirim ya da "en ucuz" gibi iddia görünce uyarır (referans fiyat = son 10 günün en düşüğü, RG 33297) ve Reklam Etiketi Kontrolü girdisini yazar. Her kural kaynak, tarih ve güven taşır; ikincil kaynaklılar "satıcı panelinden doğrula" işaretlidir. Kullanıcı "Trendyol ilanı yaz", "ürün açıklaması/başlığı", "Hepsiburada'ya ürün yükleyeceğim", "Amazon listing", "pazaryeri ilanı", "ürün görselim reddedildi", "görseller kurala uygun mu" dediğinde kullan. Tamamen yerel - yayın, hesap, ücretli API ve tarayıcı yok.
---

# Pazaryeri İlan Kiti

Ürün bilgisi → **ürün dosyası** (`urun.yaml`, sen yazarsın) → `ilan.py uret` → her platform için `<platform>.md`
(başlık, maddeler, açıklama, özellik tablosu, arama kelimeleri, görsel kontrol listesi, denetim, kaynaklar),
`<platform>.csv` (toplu yükleme hazırlık tablosu), `ozet.md`, `rapor.json`, görsel varsa `gorsel_rapor.md`,
indirim/iddia varsa `reklam_kontrol.yaml`. İçeriği sen yazarsın; sınırları, kalıbı, sayımı ve denetimi script yapar.

## Kurallar (değişmez)

- **Yerel kal.** Hiçbir şeyi yükleme, yayınlama, satıcı paneline/hesaba girme; ücretli API çağırma. Yüklemeyi satıcı yapar.
- **Tarayıcı açma.** Chrome/Chromium hiç başlatma. Kural araştırması gerekirse yalnız herkese açık sayfaları okuma amaçlı aç.
- **Uydurma yok.** Ölçü, malzeme, içerik, menşei, sertifika, barkod, fiyat yalnız kullanıcıdan ya da ürünün kendi
  etiketinden gelir. Bilinmeyen alanı boş bırak ve kullanıcıya sor. Fotoğraftan yalnız görüneni çıkar (renk, desen,
  biçim); "pamuk", "350 ml" gibi bilgiyi fotoğraftan tahmin etme.
- **Belge isteyen iddia yazma.** "Doğal", "organik", "antibakteriyel", "hipoalerjenik", "dermatolojik test edildi",
  "tedavi eder", "en iyi/en ucuz" gibi ifadeleri kullanıcının belgesi yoksa yazma. Script bunları işaretler.
- **Kural tarihli.** Pazaryeri kuralları değişir. `rules/platformlar.yaml` içindeki her kuralın kaynağı, okunma tarihi ve
  güveni var. `guven: ikincil` ya da `tahmin` olan her kural çıktıda **"satıcı panelinden doğrula"** diye işaretlenir;
  bunu kullanıcıya açıkça söyle, kesin kural gibi sunma.
- **Hukuki görüş değil.** İndirim uyarısı bilgilendirmedir; ayrıntı için Reklam Etiketi Kontrolü'ne yönlendir.

## Akış

`S=~/.claude/skills/pazaryeri-ilan/scripts`, `PY` = Python 3.8+ (görsel ölçümü için Pillow + numpy kurulu venv; README).

1. **Kontrol:** `$PY $S/ilan.py doctor` (eksik paket varsa tek satırla söyle; ilan üretimi Pillow olmadan da çalışır).
2. **Bilgiyi topla (kısa sor):** marka, ürün tipi, kategori, hangi platformlar, temel özellikler (önem sırasıyla),
   ölçü/miktar, renk, beden/varyantlar, malzeme ve etiket bilgileri, barkod, fiyat (indirim varsa önceki fiyat, son 10 günün
   en düşük fiyatı, kampanya tarihleri, hangi kanal), stok, fotoğraf yolları. Fotoğraf verdiyse Read ile **bak** ve yalnız
   görüneni not al.
3. **Ürün dosyasını yaz:** iskelet `$PY $S/ilan.py yeni > urun.yaml`; örnekler `examples/*/urun.yaml`.
   - `temel_ozellikler`: başlığa önem sırasıyla girer, sığmayan sondan düşer. En önemlisi başa (malzeme, ana fayda, ölçü).
   - `one_cikanlar`: 3-5 madde; her madde tek fayda + somut bilgi ("350 ml; kahve ve çay için"). Kampanya/kargo yazma.
   - `aciklama`: 2-4 kısa paragraf: ne, kimin için, neden bu ürün, nasıl kullanılır. Satıcının sesiyle, abartısız.
   - `anahtar_kelimeler`: alıcının arayacağı 6-15 ifade, eş anlamlılar dahil ("tişört", "t-shirt").
4. **Denetle:** `$PY $S/ilan.py kontrol urun.yaml` → DÜZELT'leri düzelt, UYARI'ları kullanıcıyla değerlendir.
5. **Üret:** `$PY $S/ilan.py uret urun.yaml --cikti ilan/` (`--platform trendyol,amazon` ile daralt).
   Çıkış kodu 1 = DÜZELT ya da görselde KALDI var.
6. **Görseller:** `gorseller:` doluysa ölçüm `uret` içinde yapılır. Ayrıca:
   `$PY $S/gorsel_kontrol.py foto1.jpg foto2.jpg --platform hepsi --rapor gorsel_rapor.md`.
   Beyaz zeminli ana görsel yanlış ölçü/oransa: `--hazirla hazir/` (saf beyaz tuvale ortalar, ürün %85).
   Zemin beyaz değilse script yerleştirmez: dekupe gerekir (bunu kullanıcıya söyle; görsel üretmeyi/yeniden çizmeyi önerme).
   **Gözle bak (zorunlu):** her görseli Read ile aç; yazı, fiyat, logo, filigran, çerçeve, kesik ürün, gerçek dışı renk var mı.
   Script yazıyı yalnız üründen ayrık öğe olarak sezer, ürünün üstündekini göremez.
7. **Sun:** her platformun başlığı (karakter sayısıyla), denetimdeki DÜZELT/UYARI'lar, görsel sonuçları, "satıcı panelinden
   doğrula" işaretli kurallar, dosya yolları. CSV'nin bir hazırlık tablosu olduğunu söyle: platformun kendi kategori
   şablonu panelden indirilir, değerler oraya kopyalanır.

## İndirim ve iddia kancası

Ürün dosyasında `fiyat.liste > fiyat.satis`, `indirim:` bloğu ya da metinde "indirim, %, yerine, kampanya, en ucuz"
gibi ifadeler varsa:
- Script önceki fiyatı **son 10 günün en düşük fiyatıyla** karşılaştırır (RG 01.07.2026 / 33297, md.14/3; aynı kanal md.14/5)
  ve yanlışsa doğru indirim oranıyla DÜZELT yazar. Son 10 gün fiyatı bilinmiyorsa kullanıcıya sor.
- Pazaryerinin "liste / piyasa satış fiyatı" alanı ürün sayfasında üstü çizili görünebilir; o alan da bu kurala tabidir.
- `reklam_kontrol.yaml` yazılır. Reklam Etiketi Kontrolü kuruluysa (`~/.claude/skills/reklam-etiketi`) otomatik çalışır ve
  `reklam_raporu.md` üretir; değilse kullanıcıya ücretsiz skill'i öner: github.com/redirhan/reklam-etiketi.
  Raporda etiket (ETK-*) maddeleri etkileyici reklamları içindir; satıcının kendi ilanında indirim (FYT-*) ve üstünlük
  (KRS-*) maddelerine bak.

## Ürün dosyası alanları

```yaml
marka: "Lavora Atölye"            # yazıldığı gibi kalır
urun_tipi: "zeytinyağlı sabun"     # isim; başlıkta Türkçe büyük harf kuralıyla yazılır (İ/ı doğru)
model: ""                          # seri/model adı (isteğe bağlı)
kategori: "Kozmetik > Banyo & Duş > Katı Sabun"
kategori_grubu: kozmetik           # kozmetik | giyim | ev_mutfak | taki_aksesuar | gida | diger
cinsiyet: ""                       # giyimde
temel_ozellikler: ["el yapımı", "soğuk işlem", "kokusuz"]
renk: ""
miktar: "100 g"
beden: ""                          # bedenler için varyantlar
model_kodu: "LVR-SBN-ZY100"
barkod: "..."                      # tırnak içinde
stok: 40
fiyat: {satis, liste, kdv, para_birimi}      # liste = üstü çizili fiyat
indirim: {onceki_fiyat, indirimli_fiyat, son_10_gun_en_dusuk, baslangic, bitis, kanal}
desi: 1
hazirlik_gunu: 2
ozellikler: {Ad: değer}            # özellik tablosu
one_cikanlar: ["...", "..."]
aciklama: |                        # paragraflar boş satırla ayrılır
kullanim: "" / bakim: "" / paket_icerigi: [] / uyarilar: ""
anahtar_kelimeler: ["...", "..."]
varyantlar: [{beden, renk, barkod, stok_kodu, stok}]   # her biri CSV'de ayrı satır
gorseller: ["ana.jpg", "detay.jpg"]                  # ilk görsel = ana görsel; yol dosyaya göre
platformlar: [trendyol, hepsiburada, n11, amazon]
```

(Örneklerde `{}` kısaltması yerine her alan ayrı satırda yazılır; dahili YAML okuyucu akış sözlüğü okumaz.)

## Başlık nasıl kurulur

`rules/platformlar.yaml` → `baslik_kalip` (ör. `marka, cinsiyet, temel_ozellikler, urun_tipi, renk, miktar`) ve
`baslik_max`. Script parçaları sırayla birleştirir, tekrar eden kelimeyi atar, Türkçe başlık düzenini uygular,
sınırı aşarsa önce listenin sonundaki temel özelliği düşürür ve neyi düşürdüğünü yazar. Amazon'da yasak karakter ve
aynı kelimenin 2'den fazla tekrarı denetlenir; arama terimleri UTF-8 bayt olarak sayılır (ş, ğ, ı, ö, ü, ç = 2 bayt).

## Alt komutlar

| Komut | İş |
|---|---|
| `ilan.py doctor` | Python, paketler, kural dosyası (her kuralda kaynak + tarih + güven), Türkçe harf testi |
| `ilan.py yeni` | boş ürün dosyası |
| `ilan.py kontrol URUN` | denetim: eksik alan, yasak ifade, iletişim/link, barkod, indirim, belge isteyen iddia |
| `ilan.py uret URUN --cikti DIR` | platform dosyaları + CSV + özet + görsel raporu + reklam kancası |
| `ilan.py kurallar [--platform P] [--ayrinti]` | kurallar, kaynakları, güven ve "doğrula" işaretleri |
| `gorsel_kontrol.py GORSEL... [--platform P] [--rapor] [--json] [--hazirla DIR]` | görsel ölçümü ve hazırlama |

## Sınırlar

- Kategori ağacını ve kategoriye özel zorunlu özellikleri bilmez (satıcı panelinde değişir); sık alanlar için uyarır.
- CSV sütunları platformun kategori şablonuyla birebir aynı olmayabilir; hazırlık tablosudur.
- Görsel ölçümü sezgiseldir: beyaz zemin ve doluluk sayısaldır, yazı/filigran ve ürünün gerçeğe uygunluğu gözle kontrol edilir.
- Görsel düzenleme/üretme yapmaz (yalnız beyaz zeminli görseli tuvale yerleştirir).
