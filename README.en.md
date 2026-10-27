# Marketplace Listing Kit for Turkey (Claude Code skill)

Give it your product details (and photos, if you have them); Claude drafts listings for **Trendyol, Hepsiburada, n11 and
Amazon.com.tr**: a title within each platform's limit, bullet features, a description, an attribute table, search
keywords, an image checklist and a bulk-upload prep sheet. An image checker measures every photo: white background,
product fill, resolution, aspect ratio, file size and possible text/logo overlays.

Free, MIT licensed, by Redirhan Labs. Runs fully locally: no publishing, no accounts, no paid APIs, no browser.
It never uploads anything to a marketplace; you do the upload. Output is in Turkish.

## What it does

- **Per-platform titles.** Brand + product + key attributes; Trendyol 100, Hepsiburada 150, n11 65, Amazon 200
  characters. If a title is too long, the least important attribute is dropped and reported. Correct Turkish casing
  (İ/ı), duplicate words removed. n11 subtitle; Amazon banned characters and word-repeat check.
- **Bullets and description.** 3-5 bullets; HTML description (Trendyol, Hepsiburada, n11) or list-free plain text
  (Amazon), plus attribute table, usage, care, package contents and warnings.
- **Keywords.** Amazon backend search terms are counted in UTF-8 bytes (Turkish letters take 2 bytes) and skip words
  already in the title. For the other platforms, a coverage table shows which keywords appear in title and description.
- **Image check.** `gorsel_kontrol.py` compares each photo with the platform rules: min/max size, recommended size and
  ratio, file type and size, pure-white share of the border band, product fill of the frame, cropped product, centering,
  sharpness, and objects detached from the product (text, price stickers, logos, watermarks). `--hazirla` places a
  white-background photo on a pure-white canvas at each platform's recommended size.
- **Checks.** Promo/shipping wording, phone numbers, e-mails, links, @handles, other marketplace names, emoji,
  ALL CAPS, claims that need proof ("natural", "organic", "antibacterial"…), superlatives ("cheapest"), barcode check
  digits, duplicate variant barcodes, missing category attributes.
- **Discount warning.** If there is a strike-through price or discount, the previous price is compared with the
  **lowest price of the last 10 days** (Turkish advertising regulation, Official Gazette 33297, in force 1 Aug 2026,
  art. 14) and the real discount rate is computed. Writes an input file for the free
  [reklam-etiketi](https://github.com/redirhan/reklam-etiketi) checker and runs it if installed.
- **Sourced rules.** Every rule in `rules/platformlar.yaml` carries a source URL, read date and confidence level
  (official / secondary / estimate). Rules confirmed only by secondary sources are flagged
  **"satıcı panelinden doğrula"** (verify in the seller panel).

## Install

```bash
cp -R pazaryeri-ilan ~/.claude/skills/
python3 -m venv ~/.venvs/pazaryeri-ilan
~/.venvs/pazaryeri-ilan/bin/pip install -r ~/.claude/skills/pazaryeri-ilan/requirements.txt   # Pillow + numpy for images
~/.venvs/pazaryeri-ilan/bin/python ~/.claude/skills/pazaryeri-ilan/scripts/ilan.py doctor
```

Listing generation needs only Python 3.8+; Pillow + numpy are needed for the image checker.

## Use

Ask Claude Code (in Turkish or English), e.g. *"Write Trendyol and Amazon listings for my handmade olive-oil soap,
100 g, unscented; photos are in ~/Desktop/soap/."* Or by hand:

```bash
PY=~/.venvs/pazaryeri-ilan/bin/python; S=~/.claude/skills/pazaryeri-ilan/scripts
$PY $S/ilan.py yeni > urun.yaml
$PY $S/ilan.py uret urun.yaml --cikti ilan/
$PY $S/gorsel_kontrol.py main.jpg detail.jpg --platform hepsi --rapor image_report.md
```

## Examples

Fictional brands, barcodes and prices: handmade soap (discount fix + ad-rule report), ceramic mug (clean listing,
a deliberately faulty third image, `--hazirla` output), men's t-shirt (S-XL variants), and a faulty-image check.
Example photos are edited from CC-licensed Wikimedia Commons images (not MIT): mug © ArAr'Hani, CC BY-SA 4.0;
soap © Malene Thyssen, CC BY 2.5. The soap lifestyle image is an AI-generated scene and is labelled as such.
See `examples/gorseller/LISANS.md`.

## Limits

- Marketplace rules change. Rules were read on 27 Oct 2026; logged-in seller panels were not read. Hepsiburada's
  official title and image rules were not publicly available; those values come from secondary sources and are flagged.
- It does not know category trees or category-specific required attributes; it warns about common ones.
- The CSV is a prep sheet: download the platform's own category template and paste the values there.
- Image checks are heuristic. Text or watermarks on top of the product and fidelity to the real product need a human look.
- The discount warning is information, not legal advice.

## Licence

Code and rules: MIT (`LICENSE`), © 2026 Redirhan Labs. Example images: their own CC licences.
