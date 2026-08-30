#!/usr/bin/env python3
"""Probe blocked models via their regional inference profile IDs (us.*).
Merge into allowed-chat-models.json + re-upload."""
import boto3, json, time, sys
sys.path.insert(0, "/home/z/my-project/scripts")
from probe_models_v2 import friendly

st = json.load(open("/home/z/my-project/aws/state.json"))
bed = boto3.client("bedrock", region_name="us-east-1")
rt = boto3.client("bedrock-runtime", region_name="us-east-1")
res = json.load(open("/home/z/my-project/aws/probe_result.json"))

# collect inference profiles
profiles = []
for key in ("foundation-model", "inference-profile"):
    try:
        r = bed.list_inference_profiles(type=key, maxResults=300)
        profiles += [(p["inferenceProfileId"], p.get("models", [])) for p in r["profileSummaryList"]]
    except Exception:
        pass
print(f"inference profiles: {len(profiles)}")

blocked_ids = [b["modelId"] for b in res["blocked"]]
TOOL = {"tools": [{"toolSpec": {
    "name": "noop_probe", "description": "probe",
    "inputSchema": {"json": {"type": "object", "properties": {"x": {"type": "string"}}}}}}]}

def probe(mid):
    try:
        rt.converse(modelId=mid,
                    messages=[{"role": "user", "content": [{"text": "hi"}]}],
                    system=[{"text": "You are a probe."}],
                    inferenceConfig={"maxTokens": 8, "temperature": 0.0},
                    toolConfig=TOOL)
        provider = mid.split(".")[0] if "." in mid else "other"
        print(f"OK   {mid}", flush=True)
        return {"modelId": mid, "provider": provider, "name": friendly(mid)}
    except Exception as e:
        print(f"XX   {mid} :: {str(e)[:80]}", flush=True)
        return None

candidates = set()
for pid, models in profiles:
    if not pid.startswith(("us.", "global.", "eu.", "apac.")):
        continue
    for mm in models:
        mid = mm.get("modelArn", "").split("/")[-1]
        if mid in blocked_ids:
            candidates.add(pid)
for b in blocked_ids:  # also try plain us. prefix
    if b.split(":")[0].split(".")[0] in ("amazon", "anthropic", "meta", "deepseek", "mistral", "cohere", "writer", "ai21"):
        candidates.add(f"us.{b}")
candidates = sorted(candidates)
print(f"candidates: {len(candidates)}")

wins = []
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=8) as ex:
    for r in ex.map(probe, candidates):
        if r:
            wins.append(r)

existing = {m["modelId"] for m in res["models"]}
added = 0
for w in wins:
    if w["modelId"] not in existing and not any(n in w["modelId"] for n in ("rerank", "pegasus", "embed")):
        res["models"].append(w)
        added += 1
res["models"].sort(key=lambda m: (m["provider"], m["modelId"]))
res["profileProbeAt"] = int(time.time())
body = json.dumps(res, indent=1)
boto3.client("s3").put_object(Bucket=st["art_bucket"], Key="models/allowed-chat-models.json",
                              Body=body.encode(), ServerSideEncryption="aws:kms",
                              SSEKMSKeyId=st["kms_key_id"], ContentType="application/json")
json.dump(res, open("/home/z/my-project/aws/probe_result.json", "w"), indent=1)
print(f"\nFINAL allowed: {len(res['models'])} (added {added} via profiles) -> uploaded")
