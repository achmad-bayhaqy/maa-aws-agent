---
name: maa-deep-research
description: "Muat skill ini untuk mode RESEARCH / permintaan riset menyeluruh."
---

# Deep Research Method
Muat skill ini untuk mode RESEARCH / permintaan riset menyeluruh.

## Prosedur (wajib berurutan)
1. **Pecah topik** menjadi 3-6 sub-pertanyaan; buat task_plan.
2. **Riset iteratif**: web_search per sub-pertanyaan (kueri EN + ID bila relevan), lalu web_fetch untuk membaca 2-4 halaman terbaik. Minimal 4-8 sumber independen.
3. **Validasi silang**: angka/klaim penting harus didukung >= 2 sumber; tandai yang tidak terkonfirmasi.
4. **Ekstraksi data**: gunakan code_interpreter untuk tabel/perhitungan/grafik bila datanya kuantitatif.
5. **Sintesis**: laporan dengan struktur: Ringkasan Eksekutif (3-5 bullet) -> Temuan Utama (dengan angka + sitasi [n]) -> Analisis -> Risiko/Keterbatasan -> Rekomendasi -> Daftar Sumber (URL).
6. **Sitasi**: format [n] ke daftar sumber di akhir; sebutkan tanggal akses bila data berubah cepat.

## Gaya
- Netral, berbasis bukti, tanpa klaim tanpa sumber. Bahasa pengguna.
- Bila sumber kontradiktif, tampilkan kedua versi + indikasi mana yang lebih kredibel.
