---
name: maa-bedrock-model-catalog
description: "Skill ini dipakai saat pengguna bertanya soal pemilihan model Bedrock, harga, atau kemampuan (vision/reasoning/tool)."
---

# AWS Bedrock Models Expert
Skill ini dipakai saat pengguna bertanya soal pemilihan model Bedrock, harga, atau kemampuan (vision/reasoning/tool).

## Panduan pemilihan (MAA)
- FAST default: amazon.nova-micro-v1:0 (murah, cepat, tool-compatible).
- DEEP default: openai.gpt-oss-120b-1:0 (reasoning kuat, tool-compatible).
- Vision/lampiran gambar: amazon.nova-lite-v1:0.
- Anthropic Claude (Haiku/Sonnet/Opus 3.x-4.x) ada di katalog MANUAL (88 model); sonnet/opus terbaru via inference profile us.* / global.*.
- Model text-only (tanpa vision): nova-micro, gpt-oss, deepseek-r1, qwen-coder, llama text. Model tool-compatible ditandai di katalog /models.
- Katalog lengkap diambil dari list_foundation_models (modalitas TEXT/IMAGE) + inference profiles; selalu cek katalog MAA (MANUAL dropdown) sebelum menyarankan modelId spesifik.

## Aturan
1. Jelaskan trade-off harga vs kemampuan singkat (tabel bila perlu).
2. Untuk tugas: kode -> coder models; analisis data -> DEEP/analyst; chat ringan -> FAST.
3. Jangan mengarang modelId; gunakan yang ada di katalog atau inference profile resmi.
