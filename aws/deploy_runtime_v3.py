#!/usr/bin/env python3
"""MAA AWS Agent - Deploy otak v3 ke Bedrock AgentCore Runtime (Full Core env)."""
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile

import boto3

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lib_common import REGION, log, load_state, save_state

st = load_state()
ROOT = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "agent_runtime")
PKG = f"{ROOT}/pkg"
ZIP_PATH = f"{ROOT}/maa-agent-runtime.zip"
S3_KEY = f"runtime/maa-agent-runtime-{uuid.uuid4().hex[:8]}.zip"

RUNTIME_NAME = "maa_agent_runtime"

KEEP_SERVICES = {"ec2", "s3", "dynamodb", "bedrock", "bedrock-runtime", "bedrock-agent",
                 "bedrock-agent-runtime", "bedrock-agentcore", "bedrock-agentcore-control",
                 "s3vectors", "sts", "lambda", "rds", "route53", "elasticache",
                 "cloudwatch", "cloudformation", "ce", "logs", "account", "guardduty"}

if not os.path.exists(f"{PKG}/boto3") or not os.path.exists(f"{PKG}/.slimmed"):
    log("vendoring boto3 (ARM64) + slimming botocore...")
    subprocess.run(["rm", "-rf", PKG], check=False)
    os.makedirs(PKG, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG, "--no-deps",
                    "boto3", "botocore", "s3transfer", "jmespath", "python-dateutil",
                    "urllib3", "six"], check=True)
    data_dir = f"{PKG}/botocore/data"
    if os.path.isdir(data_dir):
        for svc in os.listdir(data_dir):
            p = os.path.join(data_dir, svc)
            if os.path.isdir(p) and svc not in KEEP_SERVICES and svc != "endpoints":
                subprocess.run(["rm", "-rf", p], check=False)
    subprocess.run(["find", PKG, "-name", "__pycache__", "-type", "d",
                    "-exec", "rm", "-rf", "{}", "+"], check=False)
    subprocess.run(["find", PKG, "-maxdepth", "1", "-name", "*.dist-info", "-type", "d",
                    "-exec", "rm", "-rf", "{}", "+"], check=False)
    if os.path.exists(f"{PKG}/bin"):
        subprocess.run(["rm", "-rf", f"{PKG}/bin"], check=False)
    open(f"{PKG}/.slimmed", "w").write("1")
log("deps ready")

log("building zip (main.py + deps at root)...")
if os.path.exists(ZIP_PATH):
    os.remove(ZIP_PATH)
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{ROOT}/main.py", "main.py")
    for base, _, files in os.walk(PKG):
        for f in files:
            full = os.path.join(base, f)
            rel = os.path.relpath(full, PKG)
            z.write(full, rel)
size_mb = os.path.getsize(ZIP_PATH) / 1e6
log(f"zip built: {size_mb:.1f} MB")

s3 = boto3.client("s3")
ART = st["art_bucket"]
r = s3.put_object(Bucket=ART, Key=S3_KEY,
                  Body=open(ZIP_PATH, "rb").read(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="application/zip")
version_id = r["VersionId"]
log(f"uploaded s3://{ART}/{S3_KEY} version={version_id}")

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
}

if st.get("agent_runtime_arn"):
    log(f"= runtime exists: {st['agent_runtime_arn']} (recreating)")
    try:
        bac.delete_agent_runtime(agentRuntimeId=st["agent_runtime_id"])
        log("  old runtime deleted")
    except Exception:
        pass

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
            description="MAA AWS Agent v3 - Full Core (Memory+Gateway+CI+CloudWatch trace)",
            tags={"Project": "maa-agent", "MAA": "true"},
        )
        break
    except bac.exceptions.ConflictException:
        log(f"  name still reserved, retry in 30s ({attempt+1}/15)")
        time.sleep(30)
if resp is None:
    raise SystemExit("could not create runtime - name reservation timeout")
arn = resp["agentRuntimeArn"]
rt_id = resp["agentRuntimeId"]
log(f"runtime created: {rt_id} status={resp['status']}")
st["agent_runtime_arn"] = arn
st["agent_runtime_id"] = rt_id
save_state(st)

for i in range(40):
    d = bac.get_agent_runtime(agentRuntimeId=rt_id)
    s = d["status"]
    if s in ("ACTIVE", "READY", "FAILED"):
        log(f"runtime status: {s}")
        if s == "FAILED":
            log(json.dumps(d, default=str)[:600])
            raise SystemExit(1)
        break
    time.sleep(10)
else:
    log("timeout waiting ACTIVE")
    raise SystemExit(1)

# smoke invoke: AUTO routing + memory path
log("smoke invoke (AUTO ping)...")
bac_runtime = boto3.client("bedrock-agentcore", region_name=REGION,
                           config=boto3.session.Config(read_timeout=280,
                                                       retries={"max_attempts": 2}))
sid = f"smoke-{uuid.uuid4().hex}"
t0 = time.time()
r = bac_runtime.invoke_agent_runtime(
    agentRuntimeArn=arn,
    runtimeSessionId=sid,
    contentType="application/json",
    accept="application/json",
    payload=json.dumps({
        "sessionId": sid, "userId": "smoke-user", "username": "smoke",
        "message": "Ping! Sebutkan jumlah instance EC2 di akun ini.",
        "mode": "AUTO",
    }).encode(),
)
out = r["response"].read().decode()
res = json.loads(out)
dt = time.time() - t0
log(f"invoke done in {dt:.0f}s -> status={res.get('status')} model={res.get('model')} "
    f"autoRoute={json.dumps(res.get('autoRoute'))[:80]}")
print("RESPONSE:", res.get("response", "")[:300])

save_state(st)
log("=== AGENTCORE RUNTIME V3 DEPLOY COMPLETE ===")
