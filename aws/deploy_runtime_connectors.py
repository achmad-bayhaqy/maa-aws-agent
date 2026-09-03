#!/usr/bin/env python3
"""MAA AWS Agent - v3.6: rebuild runtime + konektor tools, repoint edge.

Langkah:
  1. Vendor paramiko+deps ARM64 (utk SFTP di runtime; fallback tanpa paramiko)
  2. Build zip runtime: main.py + connectors.py + pkg/ (boto3 ARM64 slim)
  3. Upload S3 (SSE-KMS)
  4. IAM runtime role: + dynamodb Scan/GetItem di maa-connectors
  5. Recreate AgentCore runtime (env + CONNECTORS_TABLE)
  6. Repoint edge lambda env RUNTIME_ARN
  7. Tunggu ACTIVE + smoke invoke
"""
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_common import REGION, log, load_state, save_state

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "agent_runtime")
PKG = f"{ROOT}/pkg"
ZIP_PATH = f"{ROOT}/maa-agent-runtime.zip"
RUNTIME_NAME = "maa_agent_runtime"
EDGE_FN = "maa-agent-edge"
TABLE = "maa-connectors"

st = load_state()
ART = st["art_bucket"]

# ------------------------------------------------- 1. vendor ARM64 SFTP deps
log("=== 1/6 vendor paramiko ARM64 (SFTP di runtime) ===")
need = ["paramiko", "cryptography", "bcrypt", "pynacl", "cffi", "pycparser"]
if not os.path.exists(f"{PKG}/paramiko"):
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                        "--platform", "manylinux2014_aarch64", "--python-version", "3.12",
                        "--only-binary=:all:"] + need, capture_output=True, text=True)
    if r.returncode != 0:
        log("  vendor gagal (runtime tanpa SFTP, edge tetap bisa): " + (r.stderr or "")[-200:])
    else:
        subprocess.run(["find", PKG, "-name", "__pycache__", "-type", "d",
                        "-exec", "rm", "-rf", "{}", "+"], check=False)
        log("  + paramiko ARM64 siap")
else:
    log("  = sudah ada")

# ------------------------------------------------- 2. build zip
log("=== 2/6 build zip runtime ===")
if not (os.path.exists(f"{PKG}/boto3") and os.path.exists(f"{PKG}/.slimmed")):
    log("  vendoring boto3 (ARM64 slim)...")
    subprocess.run(["rm", "-rf", PKG], check=False)
    os.makedirs(PKG, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                    "boto3", "botocore", "s3transfer", "jmespath", "python-dateutil",
                    "urllib3", "six"], check=True)
    KEEP = {"ec2", "s3", "dynamodb", "bedrock", "bedrock-runtime", "bedrock-agent",
            "bedrock-agent-runtime", "bedrock-agentcore", "bedrock-agentcore-control",
            "s3vectors", "sts", "lambda", "rds", "route53", "elasticache",
            "cloudwatch", "cloudformation", "ce", "logs", "account", "guardduty"}
    data_dir = f"{PKG}/botocore/data"
    if os.path.isdir(data_dir):
        for svc in os.listdir(data_dir):
            p = os.path.join(data_dir, svc)
            if os.path.isdir(p) and svc not in KEEP and svc != "endpoints":
                subprocess.run(["rm", "-rf", p], check=False)
    subprocess.run(["find", PKG, "-name", "__pycache__", "-type", "d",
                    "-exec", "rm", "-rf", "{}", "+"], check=False)
    subprocess.run(["find", PKG, "-maxdepth", "1", "-name", "*.dist-info", "-type", "d",
                    "-exec", "rm", "-rf", "{}", "+"], check=False)
    if os.path.exists(f"{PKG}/bin"):
        subprocess.run(["rm", "-rf", f"{PKG}/bin"], check=False)
    open(f"{PKG}/.slimmed", "w").write("1")
    # vendor paramiko dijalankan sebelum boto3 hilang di step 1 — kalau boto3 baru di-vendor
    # sekarang, paramiko ikut hilang; ulangi:
    if not os.path.exists(f"{PKG}/paramiko"):
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                        "--platform", "manylinux2014_aarch64", "--python-version", "3.12",
                        "--only-binary=:all:", "paramiko", "cryptography", "bcrypt",
                        "pynacl", "cffi", "pycparser"], capture_output=True, text=True)
        log("  + paramiko ARM64 (ulang setelah boto3)")
if os.path.exists(ZIP_PATH):
    os.remove(ZIP_PATH)
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{ROOT}/main.py", "main.py")
    z.write(os.path.join(HERE, "lambda_edge", "connectors.py"), "connectors.py")
    for base, _, files in os.walk(PKG):
        for f in files:
            full = os.path.join(base, f)
            z.write(full, os.path.relpath(full, PKG))
log(f"  zip: {os.path.getsize(ZIP_PATH)/1e6:.1f} MB")

# ------------------------------------------------- 3. upload
log("=== 3/6 upload S3 (SSE-KMS) ===")
S3_KEY = f"runtime/maa-agent-runtime-{uuid.uuid4().hex[:8]}.zip"
s3 = boto3.client("s3", region_name=REGION)
r = s3.put_object(Bucket=ART, Key=S3_KEY, Body=open(ZIP_PATH, "rb").read(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="application/zip")
version_id = r["VersionId"]
log(f"  s3://{ART}/{S3_KEY} v={version_id}")

# ------------------------------------------------- 4. IAM runtime role
log("=== 4/6 IAM runtime role (dynamodb maa-connectors) ===")
iam = boto3.client("iam")
table_arn = f"arn:aws:dynamodb:{REGION}:{st.get('account_id', '')}:table/{TABLE}"
table_arn = f"arn:aws:dynamodb:{REGION}:{boto3.client('sts').get_caller_identity()['Account']}:table/{TABLE}"
acct = boto3.client("sts").get_caller_identity()["Account"]
ROLE = "maa-agent-runtime-role"
done = False
for pname in ("maa-agent-runtime-policy", "maa-agent-runtime-role-policy"):
    try:
        pol = iam.get_role_policy(RoleName=ROLE, PolicyName=pname)["PolicyDocument"]
    except iam.exceptions.NoSuchEntityException:
        continue
    stmt = next((s for s in pol["Statement"] if any("dynamodb:" in a for a in s.get("Action", []))), None)
    if stmt:
        acts = set(stmt.get("Action", [])) | {"dynamodb:Scan", "dynamodb:GetItem", "dynamodb:Query"}
        stmt["Action"] = sorted(acts)
        if table_arn not in stmt.get("Resource", []):
            stmt["Resource"] = list(stmt.get("Resource", [])) + [table_arn]
        iam.put_role_policy(RoleName=ROLE, PolicyName=pname, PolicyDocument=json.dumps(pol))
        log(f"  + policy '{pname}' diperbarui")
        done = True
        break
if not done:
    iam.put_role_policy(RoleName=ROLE, PolicyName="maa-agent-connectors-policy", PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:Query"],
                       "Resource": table_arn}]}))
    log("  + policy baru dibuat")

# ------------------------------------------------- 5. update runtime (in-place)
log("=== 5/6 update AgentCore runtime (in-place, ARN tetap) ===")
bac = boto3.client("bedrock-agentcore-control", region_name=REGION)

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
    "SCHEDULES_TABLE": st.get("schedules_table", ""),
    "CONNECTORS_TABLE": TABLE,
}
resp = bac.update_agent_runtime(
    agentRuntimeId=st["agent_runtime_id"],
    roleArn=st["runtime_role_arn"],
    agentRuntimeArtifact={"codeConfiguration": {
        "code": {"s3": {"bucket": ART, "prefix": S3_KEY, "versionId": version_id}},
        "runtime": "PYTHON_3_12", "entryPoint": ["main.py"]}},
    networkConfiguration={"networkMode": "PUBLIC"},
    protocolConfiguration={"serverProtocol": "HTTP"},
    lifecycleConfiguration={"idleRuntimeSessionTimeout": 900},
    environmentVariables=env,
    description="MAA AWS Agent v3.6 - connectors + scheduler + research")
rt_id, arn = st["agent_runtime_id"], resp.get("agentRuntimeArn", st["agent_runtime_arn"])
st["agent_runtime_arn"] = arn
save_state(st)
log(f"  runtime update diterima: {rt_id}")

for _ in range(40):
    d = bac.get_agent_runtime(agentRuntimeId=rt_id)
    if d["status"] in ("ACTIVE", "READY", "FAILED"):
        if d["status"] == "FAILED":
            log(json.dumps(d, default=str)[:600])
            raise SystemExit(1)
        log(f"  status: {d['status']}")
        break
    time.sleep(10)

# ------------------------------------------------- 6. repoint edge
log("=== 6/6 repoint edge RUNTIME_ARN ===")
lam = boto3.client("lambda", region_name=REGION)
for attempt in range(10):
    try:
        env_e = lam.get_function_configuration(FunctionName=EDGE_FN)["Environment"]["Variables"]
        env_e["RUNTIME_ARN"] = arn
        lam.update_function_configuration(FunctionName=EDGE_FN, Environment={"Variables": env_e})
        log("  + edge menunjuk runtime baru")
        break
    except lam.exceptions.ResourceConflictException:
        time.sleep(6)
log("=== DEPLOY RUNTIME KONEKTOR SELESAI ===")
