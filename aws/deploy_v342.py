#!/usr/bin/env python3
"""MAA AWS Agent - Deploy v3.4.2 (satu perintah, idempotent).

Perubahan v3.4.2 (feedback pengguna):
  1. Runtime AgentCore: rebuild (mode TUGAS terpisah dari mode MODEL,
     bypass guardrail utk superadmin via userRole, format DDB atts native
     list - akar bug crash upload gambar, system prompt pengetahuan
     terkini + kapabilitas, prompt mode TODO & MULTI).
  2. Edge Lambda: parse_modes (kompat klien lama), userRole -> runtime,
     sanitize_messages di /chat/status (atts string JSON -> array).
  3. Seed dokumentasi diperbarui (mode baru) + dokumen Kapabilitas ke
     Knowledge Base + ingestion job.
  4. Frontend: build + deploy Amplify (--skip-frontend utk lewati).

Jalankan:  python3 aws/deploy_v342.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

import boto3
from botocore.config import Config

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STAGE = "v1"
STATE_PATH = os.path.join(HERE, "state.json")


def log(m):
    print(f"[v342] {m}", flush=True)


def load_state():
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(st):
    with open(STATE_PATH, "w") as f:
        json.dump(st, f, indent=2)


st = load_state()
REGION = st.get("region", "us-east-1")
cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, read_timeout=300)
s3 = boto3.client("s3", region_name=REGION, config=cfg)
ART = st["art_bucket"]

# ================================================================ 1. RUNTIME
log("=== 1/4 Runtime rebuild (v3.4.2) ===")
RT_ROOT = os.path.join(HERE, "agent_runtime")
PKG = os.path.join(RT_ROOT, "pkg")
ZIP_PATH = os.path.join(RT_ROOT, "maa-agent-runtime.zip")
S3_KEY = f"runtime/maa-agent-runtime-{uuid.uuid4().hex[:8]}.zip"

if not os.path.exists(os.path.join(PKG, "boto3")):
    log("  vendoring boto3 (deps)...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                    "boto3", "botocore", "s3transfer", "jmespath", "python-dateutil",
                    "urllib3", "six"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                "pypdf"], check=False)
subprocess.run(["find", PKG, "-name", "__pycache__", "-type", "d",
                "-exec", "rm", "-rf", "{}", "+"], check=False)

if os.path.exists(ZIP_PATH):
    os.remove(ZIP_PATH)
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(RT_ROOT, "main.py"), "main.py")
    for base, _, files in os.walk(PKG):
        for f in files:
            full = os.path.join(base, f)
            z.write(full, os.path.relpath(full, PKG))
log(f"  zip built: {os.path.getsize(ZIP_PATH) / 1e6:.1f} MB")

r = s3.put_object(Bucket=ART, Key=S3_KEY, Body=open(ZIP_PATH, "rb").read(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="application/zip")
version_id = r["VersionId"]

bac = boto3.client("bedrock-agentcore-control", region_name=REGION, config=cfg)
env = {
    "SESSIONS_TABLE": st["sessions_table"],
    "CONF_TABLE": st["confirm_table"],
    "KB_BUCKET": st["kb_bucket"],
    "ART_BUCKET": ART,
    "GUARDRAIL_ID": st.get("guardrail_id", ""),
    "GUARDRAIL_VERSION": st.get("guardrail_version", "DRAFT"),
    "KB_ID": st.get("kb_id", ""),
    "EXEC_ROLE_ARN": st["exec_role_arn"],
    "MODELS_KEY": "models/allowed-chat-models.json",
    "VECTOR_BUCKET": st["vector_bucket"],
    "VECTOR_INDEX": st["vector_index"],
    "MEMORY_ID": st.get("memory_id", ""),
    "GW_URL": st.get("gateway_url", ""),
    "CI_ID": st.get("ci_id", ""),
    "TRACE_LOG_GROUP": st.get("trace_log_group", "/maa/agent/trace"),
}
RUNTIME_NAME = "maa_agent_runtime"
if st.get("agent_runtime_arn"):
    log(f"  delete runtime lama: {st['agent_runtime_id']}")
    try:
        bac.delete_agent_runtime(agentRuntimeId=st["agent_runtime_id"])
    except Exception:
        pass
    time.sleep(5)

resp = None
for attempt in range(15):
    try:
        resp = bac.create_agent_runtime(
            agentRuntimeName=RUNTIME_NAME,
            roleArn=st["runtime_role_arn"],
            agentRuntimeArtifact={
                "codeConfiguration": {
                    "code": {"s3": {"bucket": ART, "prefix": S3_KEY, "versionId": version_id}},
                    "runtime": "PYTHON_3_12",
                    "entryPoint": ["main.py"],
                }
            },
            networkConfiguration={"networkMode": "PUBLIC"},
            protocolConfiguration={"serverProtocol": "HTTP"},
            lifecycleConfiguration={"idleRuntimeSessionTimeout": 900},
            environmentVariables=env,
            description="MAA AWS Agent v3.4.2 - agent-mode split, superadmin guardrail bypass, atts fix, knowledge update",
            tags={"Project": "maa-agent", "MAA": "true"},
        )
        break
    except bac.exceptions.ConflictException:
        log(f"  name reserved, retry 30s ({attempt + 1}/15)")
        time.sleep(30)
if resp is None:
    raise SystemExit("runtime create timeout")
rt_id = resp["agentRuntimeId"]
st["agent_runtime_arn"] = resp["agentRuntimeArn"]
st["agent_runtime_id"] = rt_id
save_state(st)
log(f"  runtime baru: {rt_id}")
for i in range(40):
    d = bac.get_agent_runtime(agentRuntimeId=rt_id)
    if d["status"] in ("ACTIVE", "READY", "FAILED"):
        log(f"  runtime status: {d['status']}")
        if d["status"] == "FAILED":
            print(json.dumps(d, default=str)[:600])
            raise SystemExit(1)
        break
    time.sleep(10)

# ================================================================ 2. EDGE LAMBDA
log("=== 2/4 Edge Lambda update ===")
lam = boto3.client("lambda", region_name=REGION, config=cfg)
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(HERE, "lambda_edge", "handler.py"), "handler.py")
lam.update_function_code(FunctionName="maa-agent-edge", ZipFile=zbuf.getvalue())
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
time.sleep(3)
log("  edge lambda code+config updated")

# ================================================================ 3. DOCS + KB
log("=== 3/4 Seed docs + KB kapabilitas ===")
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

# ================================================================ 4. FRONTEND
if "--skip-frontend" not in sys.argv:
    log("=== 4/4 Frontend build + Amplify deploy ===")
    BUILD = os.path.join(HERE, "amplify-build")
    if os.path.exists(BUILD):
        shutil.rmtree(BUILD)
    os.makedirs(BUILD)
    shutil.copytree(os.path.join(ROOT, "src"), os.path.join(BUILD, "src"),
                    ignore=shutil.ignore_patterns("api"))
    shutil.copytree(os.path.join(ROOT, "public"), os.path.join(BUILD, "public"),
                    dirs_exist_ok=True)
    for f in ["package.json", "tsconfig.json", "postcss.config.mjs", "bun.lock",
              "components.json", "eslint.config.mjs"]:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            shutil.copy2(p, BUILD)
    try:
        os.symlink(os.path.join(ROOT, "node_modules"), os.path.join(BUILD, "node_modules"))
    except Exception:
        pass
    with open(os.path.join(BUILD, "next.config.mjs"), "w") as f:
        f.write("""/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  typescript: { ignoreBuildErrors: true },
  reactStrictMode: false,
  eslint: { ignoreDuringBuilds: true },
};
export default nextConfig;
""")
    with open(os.path.join(BUILD, ".env.production"), "w") as f:
        f.write(f"""NEXT_PUBLIC_REGION={REGION}
NEXT_PUBLIC_COGNITO_POOL_ID={st['user_pool_id']}
NEXT_PUBLIC_COGNITO_CLIENT_ID={st['app_client_id']}
NEXT_PUBLIC_API_URL={st['api_url']}
""")
    log("  next build (static export)...")
    r = subprocess.run(["bunx", "next", "build"], cwd=BUILD,
                       capture_output=True, text=True, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 or not os.path.exists(os.path.join(BUILD, "out", "index.html")):
        log("  BUILD FAIL:")
        print(out[-3000:])
        raise SystemExit(1)
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(os.path.join(BUILD, "out")):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, os.path.join(BUILD, "out")))
    amp = boto3.client("amplify", region_name=REGION, config=cfg)
    app_id = st["amplify_app_id"]
    for j in amp.list_jobs(appId=app_id, branchName="main", maxResults=10)["jobSummaries"]:
        if j["status"] in ("PENDING", "RUNNING", "WAITING_TO_APPROVE"):
            try:
                amp.stop_job(appId=app_id, branchName="main", jobId=j["jobId"])
                time.sleep(3)
            except Exception:
                pass
    job = amp.create_deployment(appId=app_id, branchName="main")
    upload_url = job.get("zipUploadUrl") or list(job.get("fileUploadUrls", {}).values())[0]
    req = urllib.request.Request(upload_url, data=zbuf.getvalue(), method="PUT",
                                 headers={"Content-Type": "application/zip"})
    urllib.request.urlopen(req)
    amp.start_deployment(appId=app_id, branchName="main", jobId=job["jobId"])
    for i in range(50):
        j = amp.get_job(appId=app_id, branchName="main", jobId=job["jobId"])["job"]["summary"]
        if j["status"] in ("SUCCEED", "FAIL", "CANCELLED"):
            if j["status"] != "SUCCEED":
                print(json.dumps(j, default=str)[:500])
                raise SystemExit(1)
            break
        time.sleep(6)
    log(f"  amplify deploy OK: {st.get('amplify_url', '')}")
else:
    log("=== 4/4 Frontend dilewati (--skip-frontend) ===")

save_state(st)
log("=== DEPLOY v3.4.2 COMPLETE ===")
