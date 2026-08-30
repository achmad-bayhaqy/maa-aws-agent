#!/usr/bin/env python3
"""Re-probe validation-failed models WITHOUT toolChoice (runtime omits it too).
Merge results into allowed-chat-models.json and re-upload."""
import boto3, json, time, sys
sys.path.insert(0, "/home/z/my-project/scripts")
from probe_models_v2 import FRIENDLY, friendly  # reuse mapping

st = json.load(open("/home/z/my-project/aws/state.json"))
rt = boto3.client("bedrock-runtime", region_name="us-east-1")
res = json.load(open("/home/z/my-project/aws/probe_result.json"))

retest = [b["modelId"] for b in res["blocked"] if b["reason"] == "validation"]
print(f"re-testing {len(retest)} models without toolChoice")

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
        print(f"XX   {mid} :: {str(e)[:60]}", flush=True)
        return None

from concurrent.futures import ThreadPoolExecutor
extra = []
with ThreadPoolExecutor(max_workers=8) as ex:
    for r in ex.map(probe, retest):
        if r:
            extra.append(r)

# cohere rerank / twelvelabs pegasus are not chat models - filter explicitly
NON_CHAT = ("rerank", "pegasus", "embed", "nova-sonic")
extra = [e for e in extra if not any(n in e["modelId"] for n in NON_CHAT)]

existing = {m["modelId"] for m in res["models"]}
for e in extra:
    if e["modelId"] not in existing:
        res["models"].append(e)

res["models"].sort(key=lambda m: (m["provider"], m["modelId"]))
res["retestedAt"] = int(time.time())
body = json.dumps(res, indent=1)
boto3.client("s3").put_object(Bucket=st["art_bucket"], Key="models/allowed-chat-models.json",
                              Body=body.encode(), ServerSideEncryption="aws:kms",
                              SSEKMSKeyId=st["kms_key_id"], ContentType="application/json")
json.dump(res, open("/home/z/my-project/aws/probe_result.json", "w"), indent=1)
print(f"\nFINAL allowed: {len(res['models'])} models (added {len(extra)}) -> uploaded")
