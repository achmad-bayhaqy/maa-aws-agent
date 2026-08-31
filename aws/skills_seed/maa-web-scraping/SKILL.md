---
name: maa-web-scraping
description: "Muat skill ini saat pengguna minta scraping data (Google Play Store, marketplace, berita, dsb)."
---

# Web Scraping Expert (Python)
Muat skill ini saat pengguna minta scraping data (Google Play Store, marketplace, berita, dsb).

## Aturan wajib
1. Selalu pakai **requests** dengan User-Agent browser asli + timeout + retry eksponensial. Jangan pakai selenium (tidak tersedia).
2. Parse dengan BeautifulSoup (bs4) bila tersedia; fallback regex untuk data terstruktur.
3. Hargai robots.txt & rate limit: jeda 0.5-1.5 detik antar request, maks 20-50 halaman per run.
4. Bila di-block (403/429): coba (a) endpoint JSON/mid-tier resmi, (b) query parameter alternatif, (c) web_fetch tool MAA sebagai fallback, (d) jelaskan keterbatasan secara jujur.

## Pola Google Play Store
- Halaman aplikasi: https://play.google.com/store/apps/details?id=<package>&hl=en&gl=US
- Data terstruktur tersembunyi di script JSON (AF_initDataCallback). Strategi:
  a) requests.get halaman -> cari blok `<script type="application/ld+json">` (rating, jumlah review, nama).
  b) regex `AF_initDataCallback` -> ekstrak JSON untuk data lebih dalam.
  c) ranking/chart: fetch halaman kategori dengan params `?hl=en&gl=US`.
- Jangan berjanji jumlah data melebihi yang berhasil diambil; laporkan N item yang real.

## Output
Tabel ringkas (pandas bila ada) + simpan chart via matplotlib bila diminta; sebutkan jumlah baris & sumber URL.
