# Pazaryeri İlan Kiti (Claude Code skill)

Ürün bilgisini ver (istersen fotoğraflarını da); Claude **Trendyol, Hepsiburada, n11 ve Amazon.com.tr** için ilan taslağını
hazırlasın: her platformun sınırına uygun başlık, öne çıkan maddeler, açıklama, özellik tablosu, arama kelimeleri,
görsel kontrol listesi ve toplu yükleme hazırlık tablosu. Görsel kontrol script'i fotoğraflarını ölçer: beyaz zemin,
ürün doluluğu, çözünürlük, oran, dosya boyutu, yazı/logo şüphesi.

Ücretsiz, MIT lisanslı. Redirhan Studio tarafından hazırlandı. Tamamen yerel çalışır: yayın yok, hesap yok,
ücretli API yok, tarayıcı yok. Hiçbir şeyi pazaryerine yüklemez; yüklemeyi sen yaparsın.

## Ne yapar?

- **Platforma göre başlık.** Marka + ürün + temel özellikler kalıbı; Trendyol 100, Hepsiburada 150, n11 65,
  Amazon 200 karakter. Sığmazsa en az önemli özelliği düşürür ve söyler. Türkçe büyük harf doğru (İ/ı), tekrar eden
  kelime atılır. n11 için alt başlık, Amazon için yasak karakter ve kelime tekrarı denetimi.
- **Maddeler ve açıklama.** 3-5 öne çıkan madde; açıklama HTML (Trendyol, Hepsiburada, n11) ya da listesiz düz metin
  (Amazon). Özellik tablosu, kullanım, bakım, paket içeriği, uyarılar.
- **Arama kelimeleri.** Amazon arka plan arama terimleri bayt olarak sayılır (ş, ğ, ı, ö, ü, ç = 2 bayt), başlıktaki
  kelimeler tekrar edilmez. Diğer platformlarda her kelimenin başlıkta ve açıklamada geçip geçmediği tablo halinde.
- **Görsel kontrolü.** `gorsel_kontrol.py` her fotoğrafı ölçer ve platform kurallarıyla karşılaştırır: en küçük/büyük
  boyut, önerilen boyut ve oran, dosya türü ve boyutu, kenar bandında saf beyaz %, ürünün kareyi doldurma oranı,
  kesik ürün, ortalama, netlik, üründen ayrık öğeler (yazı, fiyat etiketi, logo, filigran olabilir). Beyaz zeminli
  görseli `--hazirla` ile platform ölçüsüne yerleştirir (saf beyaz tuval, ürün ortada, %85).
- **Denetim.** Kampanya/kargo ifadesi, telefon, e-posta, link, @kullanıcı adı, başka platform adı, emoji, tamamı büyük
  harf, belge isteyen iddia ("doğal", "organik", "antibakteriyel"…), üstünlük iddiası ("en ucuz"), barkod kontrol hanesi,
  varyantlarda aynı barkod, kategoriye göre eksik özellik.
- **İndirim uyarısı.** Üstü çizili fiyat ya da indirim varsa önceki fiyatı **son 10 günün en düşük fiyatıyla**
  karşılaştırır (Ticari Reklam ve Haksız Ticari Uygulamalar Yönetmeliği, RG 01.07.2026 / 33297, md.14) ve gerçek indirim
  oranını hesaplar. Ücretsiz [Reklam Etiketi Kontrolü](https://github.com/redirhan/reklam-etiketi) için girdi dosyası yazar;
  kuruluysa onu da çalıştırır.
- **Kaynaklı kurallar.** `rules/platformlar.yaml` içindeki her kural kaynak URL'si, okunma tarihi ve güven düzeyi
  (resmi / ikincil / tahmin) taşır. Yalnız ikincil kaynaktan bulunabilen kurallar çıktıda **"satıcı panelinden doğrula"**
  diye işaretlenir.

## Kurulum

1. Klasörü Claude Code skill dizinine kopyala:
   ```bash
   cp -R pazaryeri-ilan ~/.claude/skills/
   ```
2. İlan üretimi yalnız Python 3.8+ ister. Görsel kontrolü için Pillow + numpy:
   ```bash
   python3 -m venv ~/.venvs/pazaryeri-ilan
   ~/.venvs/pazaryeri-ilan/bin/pip install -r ~/.claude/skills/pazaryeri-ilan/requirements.txt
   ```
3. Kontrol:
   ```bash
   ~/.venvs/pazaryeri-ilan/bin/python ~/.claude/skills/pazaryeri-ilan/scripts/ilan.py doctor
   ```
4. İsteğe bağlı: indirim denetimi için [Reklam Etiketi Kontrolü](https://github.com/redirhan/reklam-etiketi)'nü de
   `~/.claude/skills/` içine kopyala.

## Kullanım

Claude Code'a yazman yeterli:

> El yapımı zeytinyağlı sabunum için Trendyol ve Amazon ilanı yaz. 100 g, kokusuz, soğuk işlem. Fotoğraflar masaüstünde
> `sabun/` klasöründe.

Claude eksik bilgiyi sorar, ürün dosyasını yazar, denetler, ilanları üretir, fotoğraflara bakar ve sonucu söyler. Elle:

```bash
PY=~/.venvs/pazaryeri-ilan/bin/python
S=~/.claude/skills/pazaryeri-ilan/scripts
$PY $S/ilan.py yeni > urun.yaml                  # doldur (örnekler: examples/*/urun.yaml)
$PY $S/ilan.py kontrol urun.yaml
$PY $S/ilan.py uret urun.yaml --cikti ilan/      # --platform trendyol,amazon ile daralt
$PY $S/gorsel_kontrol.py ana.jpg detay.jpg --platform hepsi --rapor gorsel_rapor.md
$PY $S/gorsel_kontrol.py ana.jpg --platform trendyol --hazirla hazir/
$PY $S/ilan.py kurallar --platform n11           # kurallar, kaynaklar, doğrulama işaretleri
```

Çıktı klasörü: `trendyol.md`, `hepsiburada.md`, `n11.md`, `amazon.md` (başlık, maddeler, açıklama, özellik tablosu,
arama kelimeleri, platform notları, görsel kontrol listesi ve ölçümü, denetim, kaynaklar), aynı adlı `.csv` dosyaları
(UTF-8, `;` ayraçlı, varyant başına bir satır), `ozet.md`, `rapor.json`, `gorsel_rapor.md`
(+ indirim varsa `reklam_kontrol.yaml`, `reklam_raporu.md`).

## Örnekler

Marka adları, barkodlar ve fiyatlar uydurmadır.

| Klasör | Ürün | Ne gösterir |
|---|---|---|
| `examples/el-yapimi-sabun/` | El yapımı zeytinyağlı sabun | İndirim: üstü çizili fiyat son 10 günün en düşüğü değil → düzeltme ve gerçek oran; reklam kontrolü raporu; beyaz zemin + yaşam görseli ölçümü |
| `examples/seramik-kupa/` | Seramik kupa | İndirimsiz temiz ilan; bilerek hatalı 3. görsel (küçük, üstünde "%50 İNDİRİM"); `cikti/hazir/` içinde `--hazirla` sonucu |
| `examples/erkek-tisort/` | Erkek tişört (S-XL) | Varyantlı ürün: beden başına CSV satırı, Amazon'da beden başlıkları; maddede kargo ifadesi uyarısı |
| `examples/gorsel-kontrol/` | Hatalı görsel ana görsel olarak | Ayrık öğe (yazı/etiket) şüphesi, en küçük boyut, zemin ölçümü |

Örnek görseller Wikimedia Commons'taki CC lisanslı fotoğraflardan düzenlendi (MIT kapsamında değil):
kupa © ArAr'Hani, CC BY-SA 4.0; sabun © Malene Thyssen, CC BY 2.5. Ayrıntı: `examples/gorseller/LISANS.md`.
Sabun yaşam görseli yapay zekâ ile üretilmiş bir sahnedir ve dosyasında bu bilgi yazılıdır.

## Sınırlar

- **Kurallar değişir.** Dosyadaki kurallar 27.10.2026'da okundu. Satıcı panelleri (giriş gerektiren sayfalar) okunmadı.
  Hepsiburada'nın resmi başlık ve görsel kuralları açık sayfalarda bulunamadı; bu değerler ikincil kaynaktan ve
  "satıcı panelinden doğrula" işaretli. Kaynaklar çelişirse daha sıkı değer kullanıldı.
- Kategori ağacını ve kategoriye özel zorunlu özellikleri bilmez; sık alanlar için uyarır.
- CSV bir hazırlık tablosudur; platformun kendi kategori şablonunu panelden indirip değerleri oraya kopyala.
- Görsel ölçümü sezgiseldir. Ürünün üstündeki yazıyı ya da filigranı göremez, ürünün gerçeğe uygunluğunu bilemez:
  her görsele gözle bak.
- İndirim uyarısı bilgilendirme amaçlıdır, hukuki görüş değildir.

## Ürün görseli hizmeti

Fotoğrafların beyaz zemin kontrolünden geçmiyor mu? Telefonla çektiğin ürün fotoğrafını pazaryerine uygun beyaz zemin
ve sahne görsellerine biz dönüştürelim; ürün, renk ve etiket değişmeden. Instagram: **@redirhanstudio**

## Lisans

Kod ve kural dosyası: MIT (`LICENSE`), © 2026 Redirhan Studio. Örnek görseller: kendi CC lisansları
(`examples/gorseller/LISANS.md`).
