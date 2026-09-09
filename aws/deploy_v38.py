#!/usr/bin/env python3
"""Deploy v3.8 runtime — AgentCore 2026 superpowers: aws_api + policy engine + evaluations + self-improvement.
Mengambil env live runtime, build zip dari repo aws/agent_runtime/main.py, recreate runtime,
update edge RUNTIME_ARN. Idempotent."""
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile

import boto3
from botocore.config import Config

REGION = "us-east-1"
ART = "maa-agent-artifacts-010526264107"
RT_NAME = "maa_agent_runtime"
EDGE_FN = "maa-agent-edge"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/z/my-project/repo"
RT_ROOT = os.path.join(REPO, "aws", "agent_runtime")
PKG = os.path.join(RT_ROOT, "pkg")
ZIP_PATH = os.path.join(RT_ROOT, "maa-agent-runtime.zip")

cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, read_timeout=300)
s3 = boto3.client("s3", region_name=REGION, config=cfg)
lam = boto3.client("lambda", region_name=REGION, config=cfg)
bac = boto3.client("bedrock-agentcore-control", region_name=REGION, config=cfg)


def log(m):
    print(f"[v37] {m}", flush=True)


# 1) runtime live -> env & role
rts = bac.list_agent_runtimes()["agentRuntimes"]
mine = [r for r in rts if r["agentRuntimeName"] == RT_NAME and r["status"] == "READY"]
if not mine:
    raise SystemExit("runtime READY tidak ditemukan")
old = bac.get_agent_runtime(agentRuntimeId=mine[0]["agentRuntimeId"])
old_id = old["agentRuntimeId"]
old_env = (old.get("environmentVariables") or {})
role_arn = old["roleArn"]
log(f"runtime lama: {old_id}")

env = dict(old_env)  # pertahankan SEMUA env live (SSM_INSTANCE_PROFILE, GW_URL, dll.)
env.setdefault("SSM_INSTANCE_PROFILE", "maa-agent-ssm-profile")

# 2) vendor deps + zip
if not os.path.exists(os.path.join(PKG, "boto3")):
    log("vendoring deps...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                    "boto3", "botocore", "s3transfer", "jmespath", "python-dateutil",
                    "urllib3", "six"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                "pypdf"], check=False)
import glob as _glob
import shutil as _sh
for _old in _glob.glob(os.path.join(PKG, "resvg_py*")):
    _sh.rmtree(_old, ignore_errors=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG,
                "--no-deps", "--only-binary=:all:",
                "--platform", "manylinux2014_aarch64",
                "--implementation", "cp", "--python-version", "3.12",
                "resvg-py"], check=True)
subprocess.run(["find", PKG, "-name", "__pycache__", "-type", "d",
                "-exec", "rm", "-rf", "{}", "+"], check=False)

S3_KEY = f"runtime/maa-agent-runtime-{uuid.uuid4().hex[:8]}.zip"
if os.path.exists(ZIP_PATH):
    os.remove(ZIP_PATH)
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(RT_ROOT, "main.py"), "main.py")
    for base, _, files in os.walk(PKG):
        for f in files:
            full = os.path.join(base, f)
            z.write(full, os.path.relpath(full, PKG))
log(f"zip built: {os.path.getsize(ZIP_PATH) / 1e6:.1f} MB")

r = s3.put_object(Bucket=ART, Key=S3_KEY, Body=open(ZIP_PATH, "rb").read(),
                  ServerSideEncryption="aws:kms",
                  SSEKMSKeyId="arn:aws:kms:us-east-1:010526264107:key/723143b8-5dc2-4028-a463-cc2d489dabf6",
                  ContentType="application/zip")
version_id = r.get("VersionId", "")
log(f"zip uploaded: {S3_KEY} (versionId={version_id[:20]}...)")

# 3) hapus runtime lama -> buat baru (env merged + deskripsi v3.7)
try:
    bac.delete_agent_runtime(agentRuntimeId=old_id)
except Exception:
    pass
time.sleep(5)

resp = None
for attempt in range(20):
    try:
        resp = bac.create_agent_runtime(
            agentRuntimeName=RT_NAME,
            roleArn=role_arn,
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
            description="MAA AWS Agent v3.8 - AgentCore 2026 superpowers: aws_api generic (ribuan API AWS) "
                        "+ policy engine + evaluations + self-improvement + episodic memory",
            tags={"Project": "maa-agent", "MAA": "true"},
        )
        break
    except bac.exceptions.ConflictException:
        log(f"name reserved, retry 30s ({attempt + 1}/20)")
        time.sleep(30)
if resp is None:
    raise SystemExit("runtime create timeout")

rt_id = resp["agentRuntimeId"]
log(f"runtime baru: {rt_id}")
for i in range(90):
    d = bac.get_agent_runtime(agentRuntimeId=rt_id)
    if d["status"] in ("ACTIVE", "READY", "FAILED"):
        log(f"status: {d['status']}")
        if d["status"] == "FAILED":
            print(json.dumps(d, default=str)[:800])
            raise SystemExit(1)
        break
    time.sleep(10)
else:
    raise SystemExit("runtime masih CREATING setelah 15 menit — BATAL")

# 4) edge lambda: RUNTIME_ARN -> runtime baru (MERGE env)
def edge_status():
    return lam.get_function_configuration(FunctionName=EDGE_FN)["LastUpdateStatus"]


for i in range(30):
    s = edge_status()
    if s in ("Successful", "Failed"):
        break
    time.sleep(4)
cur_env = lam.get_function_configuration(FunctionName=EDGE_FN).get(
    "Environment", {}).get("Variables", {})
cur_env["RUNTIME_ARN"] = resp["agentRuntimeArn"]
lam.update_function_configuration(FunctionName=EDGE_FN,
                                  Environment={"Variables": cur_env}, Timeout=290)
for i in range(30):
    s = edge_status()
    if s == "Successful":
        break
    if s == "Failed":
        raise SystemExit("edge config FAILED")
    time.sleep(3)
log(f"edge RUNTIME_ARN -> {rt_id}")
log("DONE")
