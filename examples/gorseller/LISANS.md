# Örnek görseller: lisans ve kaynak

Bu klasördeki görseller **MIT lisansının kapsamında değildir**. Yalnız görsel kontrol örneği için konmuştur.
Kaynak fotoğraflar Wikimedia Commons'tan, Creative Commons lisanslı. Redirhan Labs düzenledi
(arka plan temizleme, beyaz zemin, gölge, kırpma). Örneklerdeki marka adları uydurmadır; ürünler o markalara ait değildir.

| Dosya | Kaynak fotoğraf | Yazar | Lisans | Ne yapıldı |
|---|---|---|---|---|
| `kupa_1_beyaz_fon.jpg` | [Ceramic a mug.jpg](https://commons.wikimedia.org/wiki/File:Ceramic_a_mug.jpg) | ArAr'Hani | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Arka plan temizlendi, saf beyaz zemin 1200x1800, gölge. Üretken model kullanılmadı. |
| `kupa_2_kare_2000.jpg` | aynı | ArAr'Hani | CC BY-SA 4.0 | Aynı işlem, kare 2000x2000. |
| `kupa_3_hatali_ornek.jpg` | aynı | ArAr'Hani | CC BY-SA 4.0 | **Bilerek hatalı örnek:** 560x840'a küçültüldü, üstüne "%50 İNDİRİM" etiketi ve uydurma bir kullanıcı adı yazıldı. |
| `sabun_1_beyaz_fon.jpg` | [Handmade soap.jpg](https://commons.wikimedia.org/wiki/File:Handmade_soap.jpg) | Malene Thyssen | [CC BY 2.5](https://creativecommons.org/licenses/by/2.5/) | Arka plan temizlendi, saf beyaz zemin 1200x1800. Üretken model kullanılmadı. |
| `sabun_2_kare_2000.jpg` | aynı | Malene Thyssen | CC BY 2.5 | Aynı işlem, kare 2000x2000. |
| `sabun_3_yasam.jpg` | aynı | Malene Thyssen | CC BY 2.5 | **Yapay zekâ ile üretilmiş sahne** (Google Gemini görüntü modeli) + gerçek sabun pikselleri sahneye geri konuldu. Dosyanın XMP verisinde `DigitalSourceType = compositeWithTrainedAlgorithmicMedia` yazar. |

Paylaşırken: yazar adını ve lisansı belirt. CC BY-SA 4.0 görsellerin türevleri aynı lisansla paylaşılmalıdır.

`examples/seramik-kupa/cikti/hazir/*.jpg`: `kupa_2_kare_2000.jpg` dosyasından `gorsel_kontrol.py --hazirla` ile üretildi
(yalnız beyaz tuvale yerleştirme); lisans CC BY-SA 4.0, yazar ArAr'Hani.
