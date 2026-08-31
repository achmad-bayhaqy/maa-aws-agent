#!/usr/bin/env python3
"""Rebuild AgentCore runtime dengan kode terkini + update RUNTIME_ARN di edge lambda.
Idempotent. Jalankan setiap kali aws/agent_runtime/main.py berubah."""
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
st = json.load(open(os.path.join(HERE, "state.json")))
REGION = st["region"]
cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, read_timeout=300)
s3 = boto3.client("s3", region_name=REGION, config=cfg)
lam = boto3.client("lambda", region_name=REGION, config=cfg)
bac = boto3.client("bedrock-agentcore-control", region_name=REGION, config=cfg)
ART = st["art_bucket"]


def log(m):
    print(f"[rt] {m}", flush=True)


RT_ROOT = os.path.join(HERE, "agent_runtime")
PKG = os.path.join(RT_ROOT, "pkg")
ZIP_PATH = os.path.join(RT_ROOT, "maa-agent-runtime.zip")
S3_KEY = f"runtime/maa-agent-runtime-{uuid.uuid4().hex[:8]}.zip"

if not os.path.exists(os.path.join(PKG, "boto3")):
    log("vendoring deps...")
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
log(f"zip built: {os.path.getsize(ZIP_PATH) / 1e6:.1f} MB")

r = s3.put_object(Bucket=ART, Key=S3_KEY, Body=open(ZIP_PATH, "rb").read(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="application/zip")
version_id = r["VersionId"]

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
    log(f"delete runtime lama: {st['agent_runtime_id']}")
    try:
        bac.delete_agent_runtime(agentRuntimeId=st["agent_runtime_id"])
    except Exception:
        pass
    time.sleep(5)

resp = None
for attempt in range(20):
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
            description="MAA AWS Agent v3.4.1 - fix attachment constants + memory inject",
            tags={"Project": "maa-agent", "MAA": "true"},
        )
        break
    except bac.exceptions.ConflictException:
        log(f"name reserved, retry 30s ({attempt + 1}/20)")
        time.sleep(30)
if resp is None:
    raise SystemExit("runtime create timeout")

rt_id = resp["agentRuntimeId"]
st["agent_runtime_arn"] = resp["agentRuntimeArn"]
st["agent_runtime_id"] = rt_id
json.dump(st, open(os.path.join(HERE, "state.json"), "w"), indent=2)
log(f"runtime baru: {rt_id}")

for i in range(40):
    d = bac.get_agent_runtime(agentRuntimeId=rt_id)
    if d["status"] in ("ACTIVE", "READY", "FAILED"):
        log(f"status: {d['status']}")
        if d["status"] == "FAILED":
            print(json.dumps(d, default=str)[:600])
            raise SystemExit(1)
        break
    time.sleep(10)

# update edge RUNTIME_ARN
def edge_status():
    return lam.get_function_configuration(FunctionName="maa-agent-edge")["LastUpdateStatus"]


for i in range(30):
    s = edge_status()
    if s in ("Successful", "Failed"):
        break
    time.sleep(4)
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
        raise SystemExit("edge config FAILED")
    time.sleep(3)
log("edge RUNTIME_ARN -> " + rt_id)
log("DONE")
