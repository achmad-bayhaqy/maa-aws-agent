#!/usr/bin/env python3
"""Probe every chat model with a minimal Converse call to build the
allowed-models list for MANUAL mode. Writes JSON to artifacts bucket."""
import boto3
import json
import time

st = json.load(open("/home/z/my-project/aws/state.json"))
br = boto3.client("bedrock", region_name="us-east-1")
rt = boto3.client("bedrock-runtime", region_name="us-east-1")

models = br.list_foundation_models()["modelSummaries"]
chat = sorted({m["modelId"] for m in models
               if "TEXT" in m.get("inputModalities", []) and "TEXT" in m.get("outputModalities", [])})

allowed = []
for mid in chat:
    base = mid.split(":")[0] if ":0:" in mid else mid.split(":")[0]
    # skip variant suffixes (e.g. amazon.nova-pro-v1:0:24k) - dedupe to base ids
    if any(a["modelId"].startswith(mid.split(":")[0] + ":") for a in allowed):
        continue
    try:
        rt.converse(
            modelId=mid,
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
            inferenceConfig={"maxTokens": 5},
        )
        provider = mid.split(".")[0] if "." in mid else "other"
        allowed.append({"modelId": mid, "provider": provider,
                        "name": mid.split(".")[-1] if "." in mid else mid})
        print(f"OK  {mid}")
    except Exception as e:
        msg = str(e)[:90]
        print(f"XX  {mid} :: {msg}")
    time.sleep(0.2)

body = json.dumps({"generatedAt": int(time.time()), "models": allowed}, indent=1)
key = "models/allowed-chat-models.json"
s3 = boto3.client("s3")
s3.put_object(Bucket=st["art_bucket"], Key=key, Body=body.encode(),
              ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
              ContentType="application/json")
print(f"\nALLOWED: {len(allowed)} models -> s3://{st['art_bucket']}/{key}")
