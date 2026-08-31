#!/usr/bin/env python3
"""MAA AWS Agent - Deploy v3.4.3 (satu perintah, idempotent).

Fix: link artefak hasil generate (gambar / deck / web-app) "tidak bisa dibuka".

Akar masalah:
  URL artefak dibuat sebagai S3 presigned URL yang ditandatangani kredensial
  sementara (role session) di dalam AgentCore Runtime. AWS membatasi masa
  berlaku presigned URL sampai kredensial penandatangan berakhir (~1 jam),
  berapapun ExpiresIn yang diminta (86400 s / 7 hari diabaikan). Setelah itu
  link -> 403 ExpiredToken. Di tambah pula presigned URL panjang (800-1200
  karakter) sering terpotong saat model menyalinnya ke markdown.

Solusi v3.4.3 (durable artifact links):
  1. Runtime: artefak (gen/, decks/, apps/) disimpan dengan SSE-S3 (AES256)
     dan dijawab dengan URL publik permanen (key acak 32-hex, unguessable).
     Objek SSE-KMS tidak bisa dibaca anonim, sehingga prefix publik wajib
     SSE-S3. Upload user (uploads/) tetap privat + SSE-KMS + presigned.
  2. Bucket ART: matikan BlockPublicPolicy/RestrictPublicBuckets (ACL tetap
     diblokir) + bucket policy GetObject hanya utk gen/*, decks/*, apps/*.
  3. Runtime rebuild + edge Lambda re-point RUNTIME_ARN.

Frontend TIDAK berubah (kartu artefak & galeri gambar memakai a.url apa
adanya), jadi deploy Amplify tidak diperlukan.

Jalankan:  python3 aws/deploy_v343.py
Prasyarat: kredensial AWS valid (source scripts/awsenv.sh)
"""
import io
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile

import boto3
from botocore.config import Config

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_PATH = os.path.join(HERE, "state.json")


def log(m):
    print(f"[v343] {m}", flush=True)


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

# ============================================================ 1. BUCKET POLICY
log("=== 1/3 Public artifact prefixes (gen/, decks/, apps/) ===")
s3.put_public_access_block(
    Bucket=ART,
    PublicAccessBlockConfiguration={
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,          # ACL tetap diblokir; publik hanya via policy
        "BlockPublicPolicy": False,        # izinkan policy GetObject publik terbatas
        "RestrictPublicBuckets": False,
    },
)
log("  public access block: ACL diblokir, policy publik terbatas diizinkan")

RES = [f"arn:aws:s3:::{ART}/{p}" for p in ("gen/*", "decks/*", "apps/*")]
stmt_new = {
    "Sid": "PublicReadGeneratedArtifacts",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": RES,
}
try:
    pol = json.loads(s3.get_bucket_policy(Bucket=ART)["Policy"])
    stmts = [s for s in pol.get("Statement", []) if s.get("Sid") != stmt_new["Sid"]]
    stmts.append(stmt_new)
    pol["Statement"] = stmts
except s3.exceptions.NoSuchBucketPolicy:
    pol = {"Version": "2012-10-17", "Statement": [stmt_new]}
s3.put_bucket_policy(Bucket=ART, Policy=json.dumps(pol))
log(f"  bucket policy GetObject utk 3 prefix (Sid={stmt_new['Sid']})")

# ============================================================ 2. RUNTIME REBUILD
log("=== 2/3 Runtime rebuild (v3.4.3) ===")
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
            description="MAA AWS Agent v3.4.3 - durable artifact links (public gen/decks/apps, SSE-S3)",
            tags={"Project": "maa-agent"},
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

# ============================================================ 3. EDGE RE-POINT
log("=== 3/3 Edge Lambda re-point RUNTIME_ARN ===")
lam = boto3.client("lambda", region_name=REGION, config=cfg)
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
log("  edge config updated")

log("SELESAI v3.4.3. Verifikasi:")
log("  python3 aws/smoke_v4.py   (atau minta agent 'generate gambar <prompt>' lalu klik link-nya)")
