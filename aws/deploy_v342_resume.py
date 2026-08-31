#!/usr/bin/env python3
"""Resume deploy v3.4.2 dari step edge (runtime sudah READY di step 1)."""
import json
import os
import sys
import time

import boto3
from botocore.config import Config

HERE = os.path.dirname(os.path.abspath(__file__))
st_path = os.path.join(HERE, "state.json")
with open(st_path) as f:
    st = json.load(f)
REGION = st.get("region", "us-east-1")
cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, read_timeout=300)
lam = boto3.client("lambda", region_name=REGION, config=cfg)
s3 = boto3.client("s3", region_name=REGION, config=cfg)
ART = st["art_bucket"]


def log(m):
    print(f"[v342-resume] {m}", flush=True)


# ---------- 2. EDGE ----------
log("=== 2/4 Edge Lambda update (resume) ===")
import io
import zipfile
for attempt in range(12):
    try:
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(HERE, "lambda_edge", "handler.py"), "handler.py")
        lam.update_function_code(FunctionName="maa-agent-edge", ZipFile=zbuf.getvalue())
        break
    except lam.exceptions.ResourceConflictException:
        log(f"  code update conflict, tunggu 10s ({attempt + 1}/12)")
        time.sleep(10)
time.sleep(2)
for attempt in range(12):
    try:
        lam.update_function_configuration(
            FunctionName="maa-agent-edge",
            Environment={"Variables": {
                "RUNTIME_ARN": st["agent_runtime_arn"],
                "SESSIONS_TABLE": st["sessions_table"],
                "CONF_TABLE": st["confirm_table"],
                "KB_BUCKET": st["kb_bucket"],
                "ART_BUCKET": ART,
                "KB_ID": st.get("kb_id", ""),
                "USER_POOL_ID": st["user_pool_id"],
                "KMS_KEY_ID": st["kms_key_id"],
                "TRACE_LOG_GROUP": st.get("trace_log_group", "/maa/agent/trace"),
            }},
            Timeout=290,
        )
        break
    except lam.exceptions.ResourceConflictException:
        log(f"  config update conflict, tunggu 10s ({attempt + 1}/12)")
        time.sleep(10)
time.sleep(3)
log("  edge lambda code+config updated")
log(f"  RUNTIME_ARN -> {st['agent_runtime_arn']}")

# ---------- 3. DOCS + KB ----------
log("=== 3/4 Seed docs + KB kapabilitas ===")
sys.path.insert(0, HERE)
# seed via deploy_v342 tanpa menjalankan step runtime: duplikasi logika ringkas
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
for name, content in KB_DOCS.items():
    s3.put_object(Bucket=st["kb_bucket"], Key=f"docs/{name}", Body=content.encode(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="text/markdown; charset=utf-8")
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
log("  KB kapabilitas diunggah")

with open(st_path, "w") as f:
    json.dump(st, f, indent=2)
log("=== step 2-3 COMPLETE; lanjut step 4 frontend via deploy_v342.py --skip-deploy-backend? ===")
log("(frontend deploy dijalankan terpisah)")
