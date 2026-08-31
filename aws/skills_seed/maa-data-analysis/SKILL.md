---
name: maa-data-analysis
description: "Muat skill ini untuk analisis data, perhitungan, chart, atau CSV/lampiran data."
---

# Data Analysis Expert
Muat skill ini untuk analisis data, perhitungan, chart, atau CSV/lampiran data.

## Prosedur
1. Pahami pertanyaan bisnisnya dulu; tentukan metrik yang benar.
2. Pakai code_interpreter: tulis kode kecil-kecil (print per langkah), tangani error, jangan asumsi kolom — cek nama kolom dulu.
3. Chart: matplotlib tanpa seaborn; simpan sebagai PNG (otomatis tampil di chat). Beri judul, label sumbu, dan satuan.
4. Angka penting: bulatkan 2 desimal; sebutkan N sampel; tandai outlier.
5. Sintesis: insight (APA) -> penyebab (MENGAPA) -> rekomendasi (SOLUSI). Sertakan tabel ringkas bila informatif.

## Catatan MAA
- Sandbox punya internet (PUBLIC): boleh pip install package umum & fetch data publik.
- Untuk CSV besar dari lampiran user: streaming/chunk, jangan tampilkan seluruh data.
