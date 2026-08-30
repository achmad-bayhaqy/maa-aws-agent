#!/usr/bin/env python3
"""Probe v2: test ALL chat model IDs (incl. context variants) from chat_models.txt
plus list_foundation_models extras, WITH a real toolConfig (honest compatibility
test for MANUAL mode). Writes expanded allowed-chat-models.json to artifacts."""
import boto3, json, time, sys

st = json.load(open("/home/z/my-project/aws/state.json"))
br = boto3.client("bedrock", region_name="us-east-1")
rt = boto3.client("bedrock-runtime", region_name="us-east-1")

static = [l.strip() for l in open("/home/z/my-project/scripts/chat_models.txt") if l.strip()]
try:
    summaries = br.list_foundation_models()["modelSummaries"]
    extra = sorted({m["modelId"] for m in summaries
                    if "TEXT" in m.get("inputModalities", []) and "TEXT" in m.get("outputModalities", [])})
except Exception:
    extra = []
all_ids = list(dict.fromkeys(static + extra))
print(f"catalog: {len(static)} static + {len(extra)} from API = {len(all_ids)} unique")

TOOL = {"tools": [{"toolSpec": {
    "name": "noop_probe", "description": "probe",
    "inputSchema": {"json": {"type": "object", "properties": {"x": {"type": "string"}}}}}}],
    "toolChoice": {"auto": {}}}

FRIENDLY = [
    ("nova-premier", "Nova Premier"), ("nova-pro", "Nova Pro"), ("nova-lite", "Nova Lite"),
    ("nova-micro", "Nova Micro"), ("nova-2-lite", "Nova 2 Lite"), ("nova", "Nova"),
    ("claude-opus", "Claude Opus"), ("claude-sonnet", "Claude Sonnet"),
    ("claude-haiku", "Claude Haiku"), ("claude", "Claude"),
    ("gpt-oss-120b", "GPT-OSS 120B"), ("gpt-oss", "GPT-OSS"),
    ("glm", "GLM"), ("deepseek-r", "DeepSeek R1"), ("deepseek", "DeepSeek"),
    ("llama4", "Llama 4"), ("llama-4", "Llama 4"), ("llama3", "Llama 3"), ("llama", "Llama"),
    ("jamba", "Jamba"), ("mistral-large", "Mistral Large"), ("pixtral", "Pixtral Large"),
    ("mistral", "Mistral"), ("titan", "Titan"), ("command", "Command"),
    ("qwen", "Qwen"), ("palmyra", "Palmyra"), ("grok", "Grok"), ("kimi", "Kimi"),
    ("trinity", "Trinity"), ("bria", "Bria"), ("openai", "OpenAI"),
]

def friendly(mid):
    tail = mid.split(".", 1)[-1]
    for pat, nm in FRIENDLY:
        if pat in tail.lower():
            return nm
    return tail.split(":")[0]

allowed, blocked = [], []
lock = __import__("threading").Lock()

def probe(mid):
    try:
        rt.converse(
            modelId=mid,
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
            system=[{"text": "You are a probe."}],
            inferenceConfig={"maxTokens": 8, "temperature": 0.0},
            toolConfig=TOOL,
        )
        provider = mid.split(".")[0] if "." in mid else "other"
        with lock:
            allowed.append({"modelId": mid, "provider": provider, "name": friendly(mid)})
        print(f"OK   {mid}", flush=True)
    except Exception as e:
        msg = str(e)
        short = "access-denied" if "AccessDenied" in msg or "access" in msg.lower()[:120] else \
                "throttled" if "Throttling" in msg else \
                "not-found" if "not found" in msg.lower() or "ResourceNotFound" in msg else \
                "validation" if "Validation" in msg else msg[:70]
        with lock:
            blocked.append({"modelId": mid, "reason": short})
        print(f"XX   {mid} :: {short}", flush=True)

from concurrent.futures import ThreadPoolExecutor
t0 = time.time()
with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(probe, all_ids))

print(f"\nprobed {len(all_ids)} in {time.time()-t0:.0f}s -> OK {len(allowed)} / BLOCKED {len(blocked)}")
body = json.dumps({"generatedAt": int(time.time()),
                   "models": allowed, "blocked": blocked}, indent=1)
s3 = boto3.client("s3")
s3.put_object(Bucket=st["art_bucket"], Key="models/allowed-chat-models.json",
              Body=body.encode(), ServerSideEncryption="aws:kms",
              SSEKMSKeyId=st["kms_key_id"], ContentType="application/json")
print("uploaded to s3://" + st["art_bucket"] + "/models/allowed-chat-models.json")
with open("/home/z/my-project/aws/probe_result.json", "w") as f:
    f.write(body)
