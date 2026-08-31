---
name: maa-cost-optimization
description: "Muat skill ini untuk pertanyaan biaya/penghematan AWS."
---

# AWS Cost Optimization Expert
Muat skill ini untuk pertanyaan biaya/penghematan AWS.

## Prosedur
1. Panggil aws_cost_analysis (Cost Explorer N hari + idle candidates) SEBELUM menjawab.
2. Klasifikasikan: (a) waste jelas (stopped instance + EBS attached, unattached EIP/volume, idle ALB), (b) right-sizing (over-provisioned), (c) arsitektural (spend pindah layanan).
3. Estimasi hemat per item (deskriptif; pakai harga publik kasar, tandai sebagai estimasi).
4. Rekomendasi bertingkat: Quick win (aman langsung) -> Perlu konfirmasi (stop/resize; pakai protokol konfirmasi bila destruktif) -> Strategis (Savings Plan, Graviton, S3 tiering).
5. Selalu sebutkan ID resource nyata dan nilai USD dari tool — jangan menebak.
