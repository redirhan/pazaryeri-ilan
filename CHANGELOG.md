# Değişiklik günlüğü

## 1.0 — 2026-10-27
İlk sürüm.
- Ürün dosyası (YAML/JSON) → Trendyol, Hepsiburada, n11, Amazon.com.tr ilan taslağı: platform sınırına göre başlık
  (kalıp + sığmayan özelliği düşürme + Türkçe başlık düzeni + tekrar atma), n11 alt başlığı, öne çıkan maddeler,
  açıklama (HTML ya da Amazon için listesiz düz metin), özellik tablosu, arama kelimeleri (Amazon bayt sayımı,
  diğerlerinde kapsam tablosu), platform notları, görsel kontrol listesi, toplu yükleme hazırlık CSV'si (varyant başına satır).
- `rules/platformlar.yaml`: 79 kural; her birinde kaynak URL, okunma tarihi, güven (resmi / ikincil / tahmin).
  İkincil ya da arama özetinden okunan kurallar "satıcı panelinden doğrula" işaretli; ikincil kurala dayanarak
  görsel "KALDI" verilmez (UYARI olur).
- Denetim: yasak kampanya/kargo ifadeleri, iletişim bilgisi ve link, başka platform adı, emoji, büyük harf, belge isteyen
  iddia, üstünlük iddiası, GTIN kontrol hanesi, mağaza içi (20-29) barkod uyarısı, varyant barkod tekrarı, eksik özellik.
- İndirim kancası: önceki fiyat = son 10 günün en düşük fiyatı (RG 33297, md.14/3, 14/5) kontrolü ve gerçek indirim oranı;
  Reklam Etiketi Kontrolü için `reklam_kontrol.yaml` (kuruluysa otomatik rapor).
- `gorsel_kontrol.py`: çözünürlük, oran, dosya türü/boyutu, saydamlık, renk modu, kenar bandı beyazlığı, ürün doluluğu,
  kesik ürün, ortalama, netlik, ayrık öğe (yazı/logo/filigran şüphesi), görsel sayısı; `--hazirla` ile beyaz tuvale yerleştirme.
- `doctor`, `yeni`, `kontrol`, `uret`, `kurallar`; 3 kurgusal örnek + hatalı görsel örneği; unittest testleri.
