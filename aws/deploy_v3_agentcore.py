#!/usr/bin/env python3
"""MAA AWS Agent - Full Core v3: AgentCore Memory + Gateway (+target Lambda web
tools) + Policy Engine (Cedar) + Workload Identity + Code Interpreter +
Evaluator/Online Evaluation + CloudWatch trace log group + katalog 88 model.
Semua idempotent: kalau sudah ada, dipakai ulang."""
import io
import json
import os
import subprocess
import sys
import time
import zipfile

import boto3

sys.path.insert(0, "/home/z/my-project/aws")
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state

st = load_state()
iam = boto3.client("iam")
s3 = boto3.client("s3")
bac = boto3.client("bedrock-agentcore-control", region_name=REGION)
cw = boto3.client("cloudwatch", region_name=REGION)
wlogs = boto3.client("logs", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)

KMS_ARN = st["kms_arn"]
RT_ROLE = "maa-agent-runtime-role"
GW_ROLE = "maa-agent-gateway-role"
WEB_ROLE = "maa-agent-webtool-role"
MEM_ROLE = "maa-agent-memory-role"
EVAL_ROLE = "maa-agent-eval-role"
GW_FN = "maa-agent-webtool"
TRACE_LG = "/maa/agent/trace"

BEDROCK_INVOKE_RES = [
    f"arn:aws:bedrock:{REGION}::foundation-model/*",
    f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:inference-profile/*",
    f"arn:aws:bedrock:{REGION}::foundation-model/*/*",
]


def svc_trust(svc, with_source=True):
    cond = {}
    if with_source:
        cond = {"StringEquals": {"aws:SourceAccount": ACCOUNT_ID},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:*"}}
    st_ = {"Effect": "Allow", "Principal": {"Service": svc}, "Action": "sts:AssumeRole"}
    if cond:
        st_["Condition"] = cond
    return {"Version": "2012-10-17", "Statement": [st_]}


def ensure_role(name, trust, desc):
    try:
        return iam.get_role(RoleName=name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust),
                              Description=desc,
                              Tags=[{"Key": "Project", "Value": "maa-agent"}])["Role"]["Arn"]
        time.sleep(3)
        log(f"+ role {name}")
        return arn


def wait_role(name, tries=10):
    for i in range(tries):
        try:
            iam.get_role(RoleName=name)
            return
        except iam.exceptions.NoSuchEntityException:
            time.sleep(4)
    raise SystemExit(f"role {name} tidak muncul")


# ================================================================ 1. log group
log("1/9 CloudWatch trace log group...")
try:
    cur = boto3.client("kms").get_key_policy(KeyId=st["kms_key_id"], PolicyName="default")["Policy"]
    if "logs." not in cur:
        kp = json.loads(cur)
        kp["Statement"].append({
            "Sid": "AllowCloudWatchLogs", "Effect": "Allow",
            "Principal": {"Service": f"logs.{REGION}.amazonaws.com"},
            "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe"],
            "Resource": "*",
            "Condition": {"ArnEquals": {
                "kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:{TRACE_LG}:*"}}})
        boto3.client("kms").put_key_policy(KeyId=st["kms_key_id"], PolicyName="default",
                                           Policy=json.dumps(kp))
        log("  KMS key policy + logs")
    else:
        log("  = KMS policy sudah ada logs.")
except Exception as e:
    log(f"  kms warn: {str(e)[:120]}")
created = False
for attempt in range(6):
    try:
        wlogs.create_log_group(logGroupName=TRACE_LG, kmsKeyId=KMS_ARN, tags={"Project": "maa-agent"})
        log(f"+ {TRACE_LG} (KMS)")
        created = True
        break
    except wlogs.exceptions.ResourceAlreadyExistsException:
        log(f"  = {TRACE_LG} exists")
        created = True
        break
    except Exception as e:
        log(f"  create attempt {attempt+1}/6: {str(e)[:140]}")
        time.sleep(10)
if not created:
    try:
        wlogs.create_log_group(logGroupName=TRACE_LG, tags={"Project": "maa-agent"})
        log(f"  fallback: {TRACE_LG} TANPA CMK (default encryption AWS)")
    except wlogs.exceptions.ResourceAlreadyExistsException:
        log(f"  = {TRACE_LG} exists (fallback)")
wlogs.put_retention_policy(logGroupName=TRACE_LG, retentionInDays=7)
st["trace_log_group"] = TRACE_LG
save_state(st)

# ================================================================ 2. katalog 88 model
log("2/9 Katalog model lengkap (dari chat_models.txt + probe tool-compat)...")
CATALOG_SRC = "/home/z/my-project/scripts/chat_models.txt"
PROBE = "/home/z/my-project/aws/probe_result.json"
FRIENDLY = {
    "amazon.nova-micro-v1:0": "Nova Micro", "amazon.nova-lite-v1:0": "Nova Lite",
    "amazon.nova-pro-v1:0": "Nova Pro", "amazon.nova-premier-v1:0": "Nova Premier",
    "amazon.nova-2-lite-v1:0": "Nova 2 Lite",
    "openai.gpt-oss-120b-1:0": "GPT-OSS 120B (reasoning)", "openai.gpt-oss-20b-1:0": "GPT-OSS 20B",
    "openai.gpt-oss-120b": "GPT-OSS 120B (reasoning)", "openai.gpt-oss-20b": "GPT-OSS 20B",
    "zai.glm-5": "GLM-5", "zai.glm-4.6": "GLM-4.6",
    "moonshot.kimi-k2.5": "Kimi K2.5", "moonshotai.kimi-k2-thinking": "Kimi K2 Thinking",
    "deepseek.v3.2": "DeepSeek V3.2", "deepseek.r1-v1:0": "DeepSeek R1",
    "qwen.qwen3-235b-a22b": "Qwen3 235B", "qwen.qwen3-next-80b-a3b": "Qwen3 Next 80B",
    "mistral.pixtral-large-2502-v1:0": "Pixtral Large", "mistral.mistral-large-2402-v1:0": "Mistral Large",
    "mistral.mistral-small-2402-v1:0": "Mistral Small", "mistral.mistral-large-3-20251021-v1:0": "Mistral Large 3",
    "meta.llama4-maverick-17b-instruct-v1:0": "Llama 4 Maverick", "meta.llama4-scout-17b-instruct-v1:0": "Llama 4 Scout",
    "meta.llama3-3-70b-instruct-v1:0": "Llama 3.3 70B", "meta.llama3-1-8b-instruct-v1:0": "Llama 3.1 8B",
    "google.gemma-3-27b-it": "Gemma 3 27B", "google.gemma-3-12b-it": "Gemma 3 12B",
    "writer.palmyra-x5": "Palmyra X5",
}
GROUPS = {
    "amazon": "Amazon Nova", "anthropic": "Anthropic Claude", "openai": "OpenAI OSS",
    "zai": "Z.ai GLM", "moonshot": "Moonshot Kimi", "deepseek": "DeepSeek",
    "qwen": "Qwen", "mistral": "Mistral", "meta": "Meta Llama", "google": "Google",
    "writer": "Writer", "nvidia": "NVIDIA", "cohere": "Cohere", "ai21": "AI21 Jamba",
    "upstage": "Upstage", "lg": "LG EXAONE", "avian": "Avian", "palmyra": "Writer",
}
ids = [l.strip() for l in open(CATALOG_SRC) if l.strip()]
tool_ok = set()
try:
    pr = json.load(open(PROBE))
    for m in pr.get("models", []):
        tool_ok.add(m["modelId"])
except Exception:
    pass


def friendly(mid):
    if mid in FRIENDLY:
        return FRIENDLY[mid]
    base = mid.split(":")[0]
    if base in FRIENDLY:
        return FRIENDLY[base]
    # variant :24k/:300k dst
    core = mid.split(":")[1] if ":0" in mid else mid
    short = base
    prov = mid.split(".")[0]
    nm = short.split(".", 1)[1].replace("-v1:0", "").replace("-1:0", "").replace("-", " ").title()
    kw = ""
    if ":256k" in mid: kw = " (256k)"
    elif ":300k" in mid: kw = " (300k)"
    elif ":200k" in mid: kw = " (200k)"
    elif ":1000k" in mid: kw = " (1M)"
    elif ":128k" in mid: kw = " (128k)"
    elif ":24k" in mid: kw = " (24k)"
    elif ":8k" in mid: kw = " (8k)"
    elif ":20k" in mid: kw = " (20k)"
    elif ":mm" in mid: kw = " (multimodal)"
    return f"{nm}{kw}"


def base_id(mid):
    b = mid.split(":")[0]
    if b.endswith("-1:0"):
        b = b[:-4]
    return b


def in_tools(mid):
    return mid in tool_ok or base_id(mid) in tool_ok


models = []
seen = set()
for mid in ids:
    if mid in seen:
        continue
    seen.add(mid)
    prov = mid.split(".")[0] if "." in mid else "other"
    models.append({
        "modelId": mid,
        "name": friendly(mid),
        "provider": prov,
        "group": GROUPS.get(prov, prov.title()),
        "toolCompatible": in_tools(mid),
        "cacheSupported": prov == "amazon" or "nova" in mid,
        "reasoning": ("gpt-oss" in mid or "r1" in mid or "thinking" in mid or "deepseek" in mid),
    })
catalog = {"autoDefaults": {"fast": "amazon.nova-micro-v1:0", "deep": "openai.gpt-oss-120b-1:0"},
           "generatedAt": int(time.time()), "total": len(models), "models": models}
art = st["art_bucket"]
s3.put_object(Bucket=art, Key="models/allowed-chat-models.json",
              Body=json.dumps(catalog, ensure_ascii=False).encode(),
              ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
              ContentType="application/json")
log(f"  katalog {len(models)} model -> s3://{art}/models/allowed-chat-models.json")

# ================================================================ 3. roles
log("3/9 IAM roles...")
# runtime role (update policy: + memory, CI, browser, gateway, logs, canvas)
rt_arn = st.get("runtime_role_arn") or ensure_role(RT_ROLE, svc_trust("bedrock-agentcore.amazonaws.com"), "MAA runtime")
rt_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Logs", "Effect": "Allow", "Action": [
            "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams",
            "logs:CreateLogGroup"],
            "Resource": [f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:{TRACE_LG}:*",
                         f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/*"]},
        {"Sid": "BedrockModels", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse", "bedrock:ConverseStream"],
         "Resource": BEDROCK_INVOKE_RES + ["*"]},
        {"Sid": "BedrockKB", "Effect": "Allow", "Action": ["bedrock:Retrieve"],
         "Resource": [f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:knowledge-base/{st.get('kb_id', '*')}",
                      f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:knowledge-base/*"]},
        {"Sid": "AgentCoreMemory", "Effect": "Allow", "Action": [
            "bedrock-agentcore:CreateEvent", "bedrock-agentcore:GetEvent",
            "bedrock-agentcore:ListEvents", "bedrock-agentcore:RetrieveMemoryRecords",
            "bedrock-agentcore:ListMemoryRecords"],
         "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:memory/*"},
        {"Sid": "AgentCoreCI", "Effect": "Allow", "Action": [
            "bedrock-agentcore:StartCodeInterpreterSession",
            "bedrock-agentcore:StopCodeInterpreterSession",
            "bedrock-agentcore:GetCodeInterpreterSession",
            "bedrock-agentcore:InvokeCodeInterpreter",
            "bedrock-agentcore:ListCodeInterpreterSessions"],
         "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:code-interpreter/*"},
        {"Sid": "AgentCoreBrowser", "Effect": "Allow", "Action": [
            "bedrock-agentcore:StartBrowserSession", "bedrock-agentcore:StopBrowserSession",
            "bedrock-agentcore:GetBrowserSession", "bedrock-agentcore:InvokeBrowser",
            "bedrock-agentcore:UpdateBrowserStream", "bedrock-agentcore:ListBrowserSessions"],
         "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:browser/*"},
        {"Sid": "GatewayInvoke", "Effect": "Allow", "Action": ["bedrock-agentcore:InvokeGateway"],
         "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:gateway/*"},
        {"Sid": "S3Artifacts", "Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject"],
         "Resource": [f"arn:aws:s3:::{st['art_bucket']}/*"]},
        {"Sid": "S3KBRead", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": [f"arn:aws:s3:::{st['kb_bucket']}", f"arn:aws:s3:::{st['kb_bucket']}/*"]},
        {"Sid": "S3ArtList", "Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{st['art_bucket']}", f"arn:aws:s3:::{st['art_bucket']}/*"]},
        {"Sid": "Tables", "Effect": "Allow", "Action": [
            "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"],
         "Resource": [f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{st['sessions_table']}",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{st['sessions_table']}/index/*",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{st['confirm_table']}"]},
        {"Sid": "STSExec", "Effect": "Allow", "Action": ["sts:AssumeRole"],
         "Resource": st["exec_role_arn"]},
        {"Sid": "VectorIndex", "Effect": "Allow", "Action": ["s3vectors:QueryVectors", "s3vectors:GetVectors"],
         "Resource": st["vector_index_arn"]},
    ],
}
iam.put_role_policy(RoleName=RT_ROLE, PolicyName="maa-agent-runtime-policy",
                    PolicyDocument=json.dumps(rt_policy))
log(f"  {RT_ROLE} policy v3 (memory+CI+browser+gateway+CW)")

gw_role_arn = ensure_role(GW_ROLE, svc_trust("bedrock-agentcore.amazonaws.com"), "MAA gateway")
iam.put_role_policy(RoleName=GW_ROLE, PolicyName="maa-agent-gateway-policy", PolicyDocument=json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "InvokeTargets", "Effect": "Allow", "Action": ["lambda:InvokeFunction"],
         "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{GW_FN}*"},
        {"Sid": "Logs", "Effect": "Allow", "Action": [
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:*"},
    ]}))
wait_role(GW_ROLE)
log(f"  {GW_ROLE} ok")

web_role_arn = ensure_role(WEB_ROLE, svc_trust("lambda.amazonaws.com", with_source=False), "MAA web tools (gateway target)")
iam.update_assume_role_policy(RoleName=WEB_ROLE, PolicyDocument=json.dumps(
    svc_trust("lambda.amazonaws.com", with_source=False)))
iam.put_role_policy(RoleName=WEB_ROLE, PolicyName="maa-agent-webtool-policy", PolicyDocument=json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Logs", "Effect": "Allow", "Action": [
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:*"},
        {"Sid": "Browser", "Effect": "Allow", "Action": [
            "bedrock-agentcore:StartBrowserSession", "bedrock-agentcore:StopBrowserSession",
            "bedrock-agentcore:GetBrowserSession", "bedrock-agentcore:InvokeBrowser",
            "bedrock-agentcore:UpdateBrowserStream", "bedrock-agentcore:ListBrowserSessions"],
         "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:browser/*"},
    ]}))
wait_role(WEB_ROLE)
log(f"  {WEB_ROLE} ok")

mem_role_arn = ensure_role(MEM_ROLE, svc_trust("bedrock-agentcore.amazonaws.com"), "MAA memory extraction")
iam.put_role_policy(RoleName=MEM_ROLE, PolicyName="maa-agent-memory-policy", PolicyDocument=json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Bedrock", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
         "Resource": BEDROCK_INVOKE_RES + ["*"]},
        {"Sid": "Logs", "Effect": "Allow", "Action": [
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:*"},
    ]}))
wait_role(MEM_ROLE)
log(f"  {MEM_ROLE} ok")

eval_role_arn = ensure_role(EVAL_ROLE, svc_trust("bedrock-agentcore.amazonaws.com"), "MAA online evaluation")
iam.put_role_policy(RoleName=EVAL_ROLE, PolicyName="maa-agent-eval-policy", PolicyDocument=json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Bedrock", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
         "Resource": BEDROCK_INVOKE_RES + ["*"]},
        {"Sid": "LogsRead", "Effect": "Allow", "Action": [
            "logs:GetLogEvents", "logs:DescribeLogStreams", "logs:FilterLogEvents",
            "logs:DescribeLogGroups", "logs:ListLogGroups", "logs:GetLogGroupFields"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:*"},
        {"Sid": "LogsWriteResults", "Effect": "Allow", "Action": [
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": [f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/evaluations/*",
                      f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:/maa/agent/*"]},
    ]}))
wait_role(EVAL_ROLE)
log(f"  {EVAL_ROLE} ok")

# ================================================================ 4. Memory
log("4/9 AgentCore Memory...")
memory_id = st.get("memory_id")
if memory_id:
    try:
        mem = bac.get_memory(memoryId=memory_id)
        log(f"  = memory {memory_id} status {mem['memory']['status']}")
    except Exception:
        memory_id = None
if not memory_id:
    for m in bac.list_memories(maxResults=50).get("memories", []):
        if str(m.get("name", "")).startswith("maaagentmemory") or str(m.get("id", "")).startswith("maaagentmemory"):
            memory_id = m.get("memoryId") or m.get("id")
            break
if not memory_id:
    for attempt in range(5):
        try:
            r = bac.create_memory(
                name="maaagentmemory",
                description="Konteks lintas-sesi MAA AWS Agent (semantic + preferensi)",
                eventExpiryDuration=90,
                encryptionKeyArn=KMS_ARN,
                memoryExecutionRoleArn=mem_role_arn,
                memoryStrategies=[
                    {"semanticMemoryStrategy": {
                        "name": "semantic_facts",
                        "description": ("Fakta proyek, keputusan arsitektur, hasil operasi AWS, "
                                        "dan konteks penting lain dari percakapan")}},
                    {"userPreferenceMemoryStrategy": {
                        "name": "user_prefs",
                        "description": ("Preferensi pengguna: gaya jawaban, bahasa, level detail, "
                                        "dan cara kerja yang disukai")}},
                ],
                tags={"Project": "maa-agent"})
            memory_id = r["memory"].get("memoryId") or r["memory"].get("id")
            break
        except Exception as e:
            msg = str(e)
            if "Conflict" in msg or "already" in msg.lower():
                for m in bac.list_memories(maxResults=50).get("memories", []):
                    if str(m.get("name", "")).startswith("maaagentmemory") or str(m.get("id", "")).startswith("maaagentmemory"):
                        memory_id = m.get("memoryId") or m.get("id")
                break
            log(f"  create memory retry {attempt+1}/5: {msg[:150]}")
            time.sleep(8)
    else:
        raise SystemExit("memory gagal dibuat")
for i in range(40):
    s = bac.get_memory(memoryId=memory_id)["memory"]["status"]
    if s in ("ACTIVE", "FAILED"):
        log(f"  memory {memory_id}: {s}")
        if s == "FAILED":
            raise SystemExit("memory FAILED")
        break
    time.sleep(5)
st["memory_id"] = memory_id
save_state(st)

# ================================================================ 5. Gateway target Lambda
log("5/9 Web tool Lambda (gateway target)...")
ROOT = "/home/z/my-project/aws/lambda_gateway_target"
PKG = f"{ROOT}/pkg"
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", PKG,
                "websocket-client"], check=False)
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{ROOT}/handler.py", "handler.py")
    for base, _, files in os.walk(PKG):
        for f in files:
            full = os.path.join(base, f)
            z.write(full, os.path.relpath(full, PKG))
fn_env = {"BROWSER_ID": "aws.browser.v1"}
try:
    lam.get_function(FunctionName=GW_FN)
    for attempt in range(10):
        try:
            lam.update_function_code(FunctionName=GW_FN, ZipFile=zbuf.getvalue())
            while lam.get_function_configuration(FunctionName=GW_FN)["LastUpdateStatus"] == "InProgress":
                time.sleep(3)
            lam.update_function_configuration(FunctionName=GW_FN, Timeout=120, MemorySize=512,
                                               Environment={"Variables": fn_env})
            while lam.get_function_configuration(FunctionName=GW_FN)["LastUpdateStatus"] == "InProgress":
                time.sleep(3)
            break
        except lam.exceptions.ResourceConflictException:
            time.sleep(6)
    log(f"  = {GW_FN} updated")
except lam.exceptions.ResourceNotFoundException:
    for attempt in range(6):
        try:
            lam.create_function(FunctionName=GW_FN, Runtime="python3.12", Role=web_role_arn,
                                Handler="handler.handler", Code={"ZipFile": zbuf.getvalue()},
                                Timeout=120, MemorySize=512, Environment={"Variables": fn_env},
                                Description="MAA gateway target: web_search + web_fetch (AgentCore Browser)",
                                Tags={"Project": "maa-agent"})
            break
        except lam.exceptions.InvalidParameterValueException as e:
            if "cannot be assumed" in str(e) and attempt < 5:
                time.sleep(12)
                continue
            raise
    log(f"+ {GW_FN} created")
web_fn_arn = lam.get_function(FunctionName=GW_FN)["Configuration"]["FunctionArn"]
st["webtool_fn_arn"] = web_fn_arn
save_state(st)

# ================================================================ 6. Gateway
log("6/9 AgentCore Gateway (MCP, AWS_IAM)...")
gateway_id = st.get("gateway_id")
gw_url = st.get("gateway_url")
if gateway_id:
    try:
        g = bac.get_gateway(gatewayIdentifier=gateway_id)
        gw_url = g["gatewayUrl"]
        log(f"  = gateway {gateway_id} status {g['status']}")
    except Exception:
        gateway_id = None
if not gateway_id:
    r = bac.create_gateway(
        name="maa-agent-gateway",
        roleArn=gw_role_arn,
        protocolType="MCP",
        authorizerType="AWS_IAM",
        description="MAA AWS Agent tool gateway (web tools) - inbound IAM SigV4",
        tags={"Project": "maa-agent"})
    gateway_id, gw_url = r["gatewayId"], r["gatewayUrl"]
for i in range(40):
    s = bac.get_gateway(gatewayIdentifier=gateway_id)["status"]
    if s in ("READY", "FAILED"):
        log(f"  gateway {gateway_id}: {s}")
        if s == "FAILED":
            raise SystemExit("gateway FAILED")
        break
    time.sleep(5)
st["gateway_id"], st["gateway_url"] = gateway_id, gw_url
st["gateway_arn"] = bac.get_gateway(gatewayIdentifier=gateway_id)["gatewayArn"]
save_state(st)

# target
log("  gateway target webtools...")
target_id = st.get("gateway_target_id")
exists = False
if target_id:
    try:
        bac.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)
        exists = True
    except Exception:
        target_id = None
tool_schema = [
    {"name": "web_search", "description": "Cari informasi terbaru di internet via DuckDuckGo (gratis). Kembalikan judul, URL, snippet.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "kata kunci pencarian"},
         "max_results": {"type": "integer"}}, "required": ["query"]}},
    {"name": "web_fetch", "description": ("Ambil isi halaman web. GET cepat dulu; otomatis fallback ke "
                                          "AgentCore Browser untuk halaman ber-JS. Set js=true untuk paksa browser."),
     "inputSchema": {"type": "object", "properties": {
         "url": {"type": "string"},
         "js": {"type": "boolean"},
         "max_chars": {"type": "integer"}}, "required": ["url"]}},
]
if not exists:
    for attempt in range(5):
        try:
            r = bac.create_gateway_target(
                gatewayIdentifier=gateway_id,
                name="webtools",
                description="Web search (DuckDuckGo) + web fetch (AgentCore Browser)",
                targetConfiguration={"mcp": {"lambda": {
                    "lambdaArn": web_fn_arn,
                    "toolSchema": {"inlinePayload": tool_schema}}}},
                credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
            target_id = r["targetId"]
            break
        except Exception as e:
            if "Conflict" in str(e):
                for t in bac.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", []):
                    if t["name"] == "webtools":
                        target_id = t["targetId"]
                break
            log(f"  target retry {attempt+1}/5: {str(e)[:150]}")
            time.sleep(6)
for i in range(40):
    s = bac.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)["status"]
    if s in ("READY", "SYNCHRONIZED", "FAILED"):
        log(f"  target webtools: {s}")
        if s == "FAILED":
            raise SystemExit("target FAILED")
        break
    time.sleep(5)
st["gateway_target_id"] = target_id
save_state(st)

# ================================================================ 7. Policy engine + Cedar
log("7/9 Policy Engine (Cedar)...")
pe_id = st.get("policy_engine_id")
if not pe_id:
    try:
        pe_id = bac.create_policy_engine(name="maa_agent_policy_engine",
                                         description="Kebijakan tool gateway MAA")["policyEngineId"]
    except Exception as e:
        if "Conflict" in str(e) or "already" in str(e).lower():
            for pe in bac.list_policy_engines(maxResults=50).get("policyEngines", []):
                if pe.get("name") == "maa_agent_policy_engine":
                    pe_id = pe["policyEngineId"]
        else:
            log(f"  policy engine warn: {str(e)[:150]}")
gw_arn = st["gateway_arn"]
if pe_id:
    st["policy_engine_id"] = pe_id
    try:
        bac.update_gateway(gatewayIdentifier=gateway_id,
                           name="maa-agent-gateway",
                           roleArn=gw_role_arn,
                           authorizerType="AWS_IAM",
                           policyEngineConfiguration={"arn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:policy-engine/{pe_id}",
                                                      "mode": "LOG_ONLY"})
        log("  policy engine attached (LOG_ONLY)")
    except Exception as e:
        log(f"  attach warn: {str(e)[:150]}")
    have = {p["name"] for p in bac.list_policies(policyEngineId=pe_id, maxResults=50).get("policies", [])}
    gw_cedar_res = f'AgentCore::Gateway::"{gw_arn}"'
    cedar_stmts = {
        "permit_web_search": (
            f'permit(principal, action == AgentCore::Action::"webtools___web_search", '
            f'resource == {gw_cedar_res});'),
        "permit_web_fetch": (
            f'permit(principal, action == AgentCore::Action::"webtools___web_fetch", '
            f'resource == {gw_cedar_res});'),
        "forbid_admin_tools": (
            f'forbid(principal, action == AgentCore::Action::"webtools___admin_delete", '
            f'resource == {gw_cedar_res});'),
    }
    for pname, stmt in cedar_stmts.items():
        if pname in have:
            continue
        try:
            bac.create_policy(name=pname,
                              policyEngineId=pe_id,
                              definition={"cedar": {"statement": stmt}},
                              validationMode="FAIL_ON_ANY_FINDINGS",
                              enforcementMode="LOG_ONLY",
                              description="MAA gateway policy")
            log(f"  + cedar policy {pname}")
        except Exception as e:
            log(f"  policy {pname} warn: {str(e)[:180]}")
save_state(st)

# ================================================================ 8. WorkloadIdentity + Code Interpreter
log("8/9 WorkloadIdentity + Code Interpreter...")
try:
    bac.create_workload_identity(name="maa-agent-runtime", tags={"Project": "maa-agent"})
    log("  + workload identity")
except Exception as e:
    if "Conflict" not in str(e) and "already" not in str(e).lower() and "with name" not in str(e).lower():
        log(f"  identity warn: {str(e)[:120]}")
    else:
        log("  = workload identity sudah ada (auto-registered runtime)")
ci_id = st.get("ci_id")
if not ci_id:
    try:
        ci_id = bac.create_code_interpreter(
            name="maacodeinterpreter",
            description="Sandbox Python untuk analisis data & chart (AgentCore Code Interpreter)",
            networkConfiguration={"networkMode": "SANDBOX"},
            tags={"Project": "maa-agent"})["codeInterpreterId"]
    except Exception as e:
        if "Conflict" not in str(e) and "already" not in str(e).lower():
            log(f"  CI warn: {str(e)[:150]}")
        for c in bac.list_code_interpreters(maxResults=50).get("codeInterpreters", []):
            if c.get("name") in ("maacodeinterpreter", "maa-code-interpreter"):
                ci_id = c["codeInterpreterId"]
if ci_id:
    st["ci_id"] = ci_id
    log(f"  code interpreter: {ci_id}")
save_state(st)

# ================================================================ 9. Evaluator + Online Evaluation
log("9/9 Evaluator + Online Evaluation Config...")
evaluator_id = st.get("evaluator_id")
if not evaluator_id:
    try:
        r = bac.create_evaluator(
            evaluatorName="maa_helpfulness",
            description="Kualitas jawaban agent dinilai LLM-as-judge (skala 1-5)",
            level="SESSION",
            evaluatorConfig={"llmAsAJudge": {
                "instructions": ("Nilai kualitas keseluruhan sesi agen cloud-ops dalam konteks berikut: "
                                 "{context}. Nilai keakuratan data tool, kelengkapan langkah, bahasa Indonesia, "
                                 "dan keamanan (tidak mengeksekusi destruktif tanpa konfirmasi ganda). "
                                 "1=sangat buruk, 3=cukup, 5=sangat baik."),
                "ratingScale": {"numerical": [
                    {"value": 1, "label": "sangat buruk", "definition": "salah/tidak lengkap/berbahaya"},
                    {"value": 3, "label": "cukup", "definition": "benar tapi kurang detail"},
                    {"value": 5, "label": "sangat baik", "definition": "akurat, lengkap, aman"}]},
                "modelConfig": {"bedrockEvaluatorModelConfig": {
                    "modelId": "amazon.nova-micro-v1:0",
                    "inferenceConfig": {"maxTokens": 800, "temperature": 0.0}}}}},
            tags={"Project": "maa-agent"})
        evaluator_id = r["evaluatorId"]
        log(f"  + evaluator {evaluator_id}")
    except Exception as e:
        log(f"  evaluator warn: {str(e)[:180]}")
if evaluator_id:
    st["evaluator_id"] = evaluator_id
    oe_id = st.get("online_eval_id")
    if not oe_id:
        try:
            r = bac.create_online_evaluation_config(
                onlineEvaluationConfigName="maa_agent_online_eval",
                description="Sampling 10% sesi MAA agent utk evaluasi otomatis",
                rule={"samplingConfig": {"samplingPercentage": 10.0},
                      "sessionConfig": {"sessionTimeoutMinutes": 60}},
                dataSourceConfig={"cloudWatchLogs": {
                    "logGroupNames": [TRACE_LG],
                    "serviceNames": ["bedrock-agentcore-runtime"]}},
                evaluators=[{"evaluatorId": evaluator_id}],
                evaluationExecutionRoleArn=eval_role_arn,
                enableOnCreate=True,
                tags={"Project": "maa-agent"})
            oe_id = r.get("onlineEvaluationConfigId") or r.get("onlineEvaluationConfig", {}).get("onlineEvaluationConfigId")
            log(f"  + online eval config {oe_id}")
        except Exception as e:
            log(f"  online eval warn (non-blocking): {str(e)[:200]}")
    if oe_id:
        st["online_eval_id"] = oe_id
save_state(st)

log("=== AGENTCORE FULL-CORE v3 RESOURCES COMPLETE ===")
log(f"memory={st.get('memory_id')} gateway={st.get('gateway_id')} target={st.get('gateway_target_id')} "
    f"policy={st.get('policy_engine_id')} ci={st.get('ci_id')} evaluator={st.get('evaluator_id')}")
