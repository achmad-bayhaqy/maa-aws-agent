#!/usr/bin/env python3
"""Resume deploy v3.4 mulai step 3 (edge lambda) — runtime & guardrail sudah selesai.
Idempotent: aman dijalankan berulang."""
import io
import json
import os
import sys
import time
import urllib.request
import uuid
import zipfile

import boto3
from botocore.config import Config

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aws")
HERE = os.path.abspath(HERE)
ROOT = os.path.dirname(HERE)
STAGE = "v1"
STATE_PATH = os.path.join(HERE, "state.json")

with open(STATE_PATH) as f:
    st = json.load(f)
REGION = st["region"]
ACCOUNT_ID = st["account_id"]
cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, read_timeout=300)
lam = boto3.client("lambda", region_name=REGION, config=cfg)
apig = boto3.client("apigateway", region_name=REGION, config=cfg)
s3 = boto3.client("s3", region_name=REGION, config=cfg)
ART = st["art_bucket"]


def log(m):
    print(f"[v34r] {m}", flush=True)


# ================================================================ 3. EDGE LAMBDA
log("=== 3/6 Edge Lambda update ===")
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(HERE, "lambda_edge", "handler.py"), "handler.py")


def edge_status():
    return lam.get_function_configuration(FunctionName="maa-agent-edge")["LastUpdateStatus"]


# tunggu update in-progress selesai (jika ada)
for i in range(30):
    s = edge_status()
    if s in ("Successful", "Failed"):
        break
    log(f"  waiting edge settle ({s}) {i+1}/30")
    time.sleep(5)

lam.update_function_code(FunctionName="maa-agent-edge", ZipFile=zbuf.getvalue())
for i in range(30):
    s = edge_status()
    if s == "Successful":
        break
    if s == "Failed":
        raise SystemExit("edge code update FAILED")
    time.sleep(3)
log("  code updated")

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
for i in range(30):
    s = edge_status()
    if s == "Successful":
        break
    if s == "Failed":
        raise SystemExit("edge config update FAILED")
    time.sleep(3)
log("  config updated (RUNTIME_ARN -> %s)" % st["agent_runtime_id"])

# ================================================================ 4. API GW routes
log("=== 4/6 API Gateway routes + redeploy ===")
api_id = st["api_id"]
fn_arn = lam.get_function(FunctionName="maa-agent-edge")["Configuration"]["FunctionArn"]
auth_id = next(a["id"] for a in apig.get_authorizers(restApiId=api_id)["items"]
               if a["name"] == "maa-cognito-authorizer")
root_id = apig.get_resources(restApiId=api_id)["items"][0]["id"]

NEW_ROUTES = [
    ("/uploads/presign", ["POST", "OPTIONS"]),
    ("/translate", ["POST", "OPTIONS"]),
    ("/docs/content", ["GET", "POST", "OPTIONS"]),
    ("/docs/list", ["GET", "OPTIONS"]),
    ("/admin/users/set-password", ["POST", "OPTIONS"]),
    ("/admin/users/resend-invite", ["POST", "OPTIONS"]),
    ("/chat/sessions", ["GET", "DELETE", "OPTIONS"]),
]
resources = {r_["path"]: r_["id"] for r_ in apig.get_resources(restApiId=api_id, limit=400)["items"]}
resources[""] = root_id
for path, _ in NEW_ROUTES:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        parent = cur
        cur = f"{cur}/{part}"
        if cur not in resources:
            try:
                rid = apig.create_resource(restApiId=api_id, parentId=resources[parent],
                                           pathPart=part)["id"]
            except apig.exceptions.ConflictException:
                time.sleep(2)
                for r_ in apig.get_resources(restApiId=api_id, limit=400)["items"]:
                    resources[r_["path"]] = r_["id"]
                rid = resources[cur]
            resources[cur] = rid

CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Authorization,Content-Type'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,DELETE,OPTIONS'",
}
uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"


def _safe(fn, **kw):
    try:
        fn(**kw)
        return True
    except (apig.exceptions.ConflictException, apig.exceptions.NotFoundException):
        return False


for path, verbs in NEW_ROUTES:
    rid = resources[path]
    for verb in verbs:
        kw = dict(restApiId=api_id, resourceId=rid, httpMethod=verb, apiKeyRequired=False)
        if verb == "OPTIONS":
            kw["authorizationType"] = "NONE"
        else:
            kw["authorizationType"] = "COGNITO_USER_POOLS"
            kw["authorizerId"] = auth_id
        _safe(apig.put_method, **kw)
        # AWS_PROXY: Lambda (resp()) mengembalikan header CORS sendiri pada
        # setiap response -> TIDAK perlu method/integration response params.
        if verb == "OPTIONS":
            _safe(apig.put_integration, restApiId=api_id, resourceId=rid, httpMethod="OPTIONS",
                  type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
            _safe(apig.put_method_response, restApiId=api_id, resourceId=rid,
                  httpMethod="OPTIONS", statusCode="200")
        else:
            _safe(apig.put_integration, restApiId=api_id, resourceId=rid, httpMethod=verb,
                  type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
            try:
                apig.put_method_response(restApiId=api_id, resourceId=rid, httpMethod=verb,
                                         statusCode="200")
            except apig.exceptions.ConflictException:
                pass
log(f"  {len(NEW_ROUTES)} route groups wired (AWS_PROXY passthrough CORS)")

try:
    apig.add_permission(FunctionName="maa-agent-edge", StatementId=f"apigw-v34-{uuid.uuid4().hex[:6]}",
                        Action="lambda:InvokeFunction", Principal="apigateway.amazonaws.com",
                        SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/*")
except Exception as e:
    if "ResourceConflictException" not in str(e):
        log(f"  permission warn: {str(e)[:120]}")

d = apig.create_deployment(restApiId=api_id, stageName=STAGE)
log(f"  stage {STAGE} redeployed: {d['id']}")

# ================================================================ 5. SEED DOCS
log("=== 5/6 Seed dokumentasi site/docs/ ===")
DOCS = {
    "panduan-cepat.md": """# Panduan Cepat MAA AWS Agent

## Mulai dalam 60 detik
1. Login dengan akun Anda + kode TOTP dari authenticator app.
2. Pilih mode di atas kolom chat:
   - **AUTO** - agent memilih model sendiri (default terbaik).
   - **FAST** - jawaban cepat & hemat (nova-micro).
   - **DEEP** - reasoning mendalam (gpt-oss-120b).
   - **LONG** - tugas besar multi-langkah dengan todo list live.
   - **FULLSTACK** - bangun aplikasi web lengkap + preview URL.
   - **PRESENTATION** - susun slide deck profesional otomatis.
   - **MANUAL** - Anda pilih model dari katalog 88 model.
3. Ketik perintah, contoh: "List EC2", "Analisis biaya 30 hari", "Buat VPC staging".

## Upload file
Klik ikon klip di composer. Mendukung banyak file sekaligus, hingga 200 MB per file:
CSV/JSON/MD/TXT/kode diekstrak otomatis ke konteks; PNG/JPG dilihat langsung model;
PDF diekstrak teksnya. Minta agent "analisis CSV ini" setelah mengunggah.

## Keamanan
Operasi destruktif (terminate EC2, hapus bucket/table/stack) SELALU melewati
layar konfirmasi ganda: ketik string challenge 2x, jendela 5 menit.
""",
    "mode-agent.md": """# Mode & Kemampuan Agent

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

## Edit dokumentasi
Menu Dokumentasi -> tombol Edit (khusus superadmin). Format markdown dengan
preview langsung. Perubahan tersimpan terenkripsi KMS di S3.
""",
}
for name, content in DOCS.items():
    s3.put_object(Bucket=ART, Key=f"site/docs/{name}", Body=content.encode(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="text/markdown; charset=utf-8")
log(f"  {len(DOCS)} dokumen di-seed")

# ================================================================ 6. FRONTEND
if "--skip-frontend" not in sys.argv:
    import shutil
    import subprocess

    log("=== 6/6 Frontend build + Amplify deploy ===")
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
    log("=== 6/6 Frontend dilewati (--skip-frontend) ===")

log("=== DEPLOY v3.4 RESUME COMPLETE ===")
