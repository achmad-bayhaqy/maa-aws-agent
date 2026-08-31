#!/usr/bin/env python3
"""Seed dokumen site/docs + KB kapabilitas (diekstrak dari deploy_v342 step 3). Idempotent."""
import boto3
import json, sys
sys.path.insert(0, "/home/z/my-project/aws")
from lib_common import REGION, log, load_state
st = load_state()
cfg = None
s3 = boto3.client("s3")
ART = st["art_bucket"]
DOCS = {
    "panduan-cepat.md": """# Panduan Cepat MAA AWS Agent

## Mulai dalam 60 detik
1. Login dengan akun Anda + kode TOTP dari authenticator app.
2. Pilih **mode model** di atas kolom chat (cara model dipilih):
   - **AUTO** - agent memilih model sendiri sesuai kompleksitas.
   - **FAST** - jawaban cepat & hemat.
   - **DEEP** - reasoning mendalam untuk soal kompleks.
   - **MANUAL** - Anda pilih sendiri dari katalog 88 model.
3. Pilih **mode tugas agent** (ikon petir di kanan) bila perlu gaya kerja khusus:
   Standar, Tugas Panjang, Full-Stack, Presentasi, Todo List, Multi-Agent.
4. Ketik perintah. Agent Anda punya pengetahuan terkini sampai hari ini:
   browsing web real-time, code interpreter, generate gambar, memori lintas sesi.

## Upload file
Klik ikon klip di composer. Mendukung banyak file sekaligus, hingga 200 MB per file:
CSV/JSON/MD/TXT/kode diekstrak otomatis ke konteks; PNG/JPG dilihat langsung model;
PDF diekstrak teksnya. Minta agent "analisis CSV ini" setelah mengunggah.

## Keamanan
Operasi destruktif (terminate EC2, hapus bucket/table/stack) SELALU melewati
layar konfirmasi ganda: ketik string challenge 2x, jendela 5 menit.
Guardrail konten berlaku untuk user biasa; superadmin bebas bertanya apa pun.
""",
    "mode-agent.md": """# Mode & Kemampuan Agent

## Dua jenis mode (tidak boleh tertukar)
- **Mode model** (AUTO/FAST/DEEP/MANUAL) = cara pemilihan model bahasa.
- **Mode tugas agent** (Standar/Tugas Panjang/Full-Stack/Presentasi/Todo List/Multi-Agent) =
  gaya kerja agent. Mode tugas berat otomatis memakai model reasoning.

## Multi-agent (subagent)
Untuk pekerjaan berat, agent utama mendelegasikan ke agent spesialis:
researcher (riset web), analyst (data), architect (desain), coder (tulis+uji kode),
reviewer (audit), ops (inspeksi AWS). Pantau aktivitasnya di panel Live Trace.

## Todo list live
Tugas multi-langkah otomatis ditampilkan sebagai checklist di atas chat -
status berubah real-time saat agent bekerja (pending -> in_progress -> completed).

## Artefak
- **Deck presentasi**: tampil langsung di chat, bisa fullscreen & export print.
- **Web app**: agent membangun SPA lalu deploy ke preview URL yang bisa dibuka.

## Live Trace
Semua langkah agent (berpikir, tool call, hasil, subagent, konfirmasi) terekam
di panel trace kanan - transparan penuh, bisa diaudit.
""",
    "admin.md": """# Panduan Superadmin

## Undang user
Menu Admin -> Undang user baru. Pilih:
- **Email Cognito**: undangan resmi berisi password sementara (user wajib ganti password saat login pertama, lalu daftar MFA TOTP).
- **Password instan**: sistem membuat password kuat yang Anda salin & bagikan via kanal aman - user langsung login tanpa langkah ganti password.

## Kelola user
Cari/filter user, aktif/nonaktifkan, kirim ulang undangan, reset password,
atau hapus permanen. Semua aksi tervalog di CloudTrail.

## Kebijakan guardrail
Guardrail konten hanya berlaku untuk user di bawah superadmin.
Superadmin bebas mengajukan pertanyaan apa pun tanpa pembatasan guardrail.
Protokol konfirmasi ganda operasi destruktif tetap berlaku untuk semua level.

## Edit dokumentasi
Menu Dokumentasi -> tombol Edit (khusus superadmin). Format markdown dengan
preview langsung. Perubahan tersimpan terenkripsi KMS di S3.
""",
}
for name, content in DOCS.items():
    s3.put_object(Bucket=ART, Key=f"site/docs/{name}", Body=content.encode(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="text/markdown; charset=utf-8")
log(f"  {len(DOCS)} dokumen site/docs di-seed")

KB_DOCS = {
    "Kapabilitas-Agent-MAA.md": """# Kapabilitas Agent MAA (referensi internal)

Agent MAA adalah insinyur cloud otonom. Pengetahuannya dimutakhirkan terus,
termasuk lewat web_search saat menjawab, sehingga selalu terkini sampai hari ini.

## Kapabilitas inti
- Operasi AWS penuh: EC2, EKS, RDS, S3, VPC, Lambda, DynamoDB, ElastiCache,
  Route53, CloudWatch, Cost Explorer, CloudFormation (IaC tervalidasi).
- Browsing web real-time: web_search + web_fetch untuk harga, rilis, berita.
- Code Interpreter: Python/matplotlib untuk analisis data, chart, perhitungan.
- Generate gambar: Nova Canvas.
- Memori jangka panjang lintas sesi: AgentCore Memory.
- Multi-agent: subagent_run dengan peran researcher/analyst/architect/coder/reviewer/ops.
- Todo list live: task_plan untuk tugas multi-langkah.
- Artefak: deck presentasi (generate_presentation) dan web app (deploy_web_app).

## Kewajiban pengetahuan
- Saat menemukan update AWS penting (service baru, perubahan harga, deprecation),
  simpan ringkasannya ke KB ini via kb_upload_doc + kb_sync.
- Jawab pertanyaan "kamu bisa apa" dengan daftar kapabilitas di atas.
- Jawab selalu dalam bahasa pengguna (default Bahasa Indonesia).
""",
}
kb_bucket = st["kb_bucket"]
for name, content in KB_DOCS.items():
    s3.put_object(Bucket=kb_bucket, Key=f"docs/{name}", Body=content.encode(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="text/markdown; charset=utf-8")
log(f"  {len(KB_DOCS)} dokumen KB diunggah -> ingestion job...")
kb_id = st.get("kb_id", "")
if kb_id:
    try:
        ba = boto3.client("bedrock-agent", region_name=REGION, config=cfg)
        ds = ba.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
        job = ba.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds[0]["dataSourceId"],
                                     description="v3.4.2 capability knowledge update")
        log(f"  ingestion job: {job['ingestionJob']['ingestionJobId']} ({job['ingestionJob']['status']})")
    except Exception as e:
        log(f"  ingestion warn: {str(e)[:150]}")
else:
    log("  (kb_id kosong - lewati ingestion)")

