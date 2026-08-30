#!/usr/bin/env python3
"""Patch friendly display names in allowed-chat-models.json + re-upload."""
import boto3, json, re

st = json.load(open("/home/z/my-project/aws/state.json"))
res = json.load(open("/home/z/my-project/aws/probe_result.json"))

def nice(mid):
    tail = mid.split(".", 1)[-1] if "." in mid else mid
    t = tail.lower()
    m = [
        (r"nova-2-lite", "Nova 2 Lite"), (r"nova-premier", "Nova Premier"),
        (r"nova-pro", "Nova Pro"), (r"nova-lite", "Nova Lite"), (r"nova-micro", "Nova Micro"),
        (r"glm-5", "GLM-5"), (r"glm-4\.7-flash", "GLM-4.7 Flash"), (r"glm-4\.7", "GLM-4.7"),
        (r"gpt-oss-safeguard-120b", "GPT-OSS Safeguard 120B"),
        (r"gpt-oss-safeguard-20b", "GPT-OSS Safeguard 20B"),
        (r"gpt-oss-120b", "GPT-OSS 120B"), (r"gpt-oss-20b", "GPT-OSS 20B"),
        (r"kimi-k2-thinking", "Kimi K2 Thinking"), (r"kimi-k2\.5", "Kimi K2.5"),
        (r"deepseek-v3\.2|v3\.2", "DeepSeek V3.2"), (r"deepseek-r1|r1", "DeepSeek R1"),
        (r"qwen3-vl-235b", "Qwen3 VL 235B"), (r"qwen3-coder-next", "Qwen3 Coder Next"),
        (r"qwen3-coder-30b", "Qwen3 Coder 30B"), (r"qwen3-next-80b", "Qwen3 Next 80B"),
        (r"qwen3-32b", "Qwen3 32B"),
        (r"llama4-maverick|llama-4-maverick", "Llama 4 Maverick"),
        (r"llama4-scout|llama-4-scout", "Llama 4 Scout"),
        (r"llama3-3-70b", "Llama 3.3 70B"), (r"llama3-1-70b", "Llama 3.1 70B"),
        (r"llama3-1-8b", "Llama 3.1 8B"),
        (r"pixtral", "Pixtral Large"), (r"magistral", "Magistral Small"),
        (r"devstral", "Devstral 2 123B"), (r"voxtral-small", "Voxtral Small 24B"),
        (r"voxtral-mini", "Voxtral Mini 3B"),
        (r"ministral-3-14b", "Ministral 3 14B"), (r"ministral-3-8b", "Ministral 3 8B"),
        (r"ministral-3-3b", "Ministral 3 3B"),
        (r"mistral-large-3-675b", "Mistral Large 3 (675B)"),
        (r"mistral-large", "Mistral Large"), (r"mistral-small", "Mistral Small"),
        (r"nemotron-super-3-120b", "Nemotron Super 3 120B"),
        (r"nemotron-nano-3-30b", "Nemotron Nano 3 30B"),
        (r"nemotron-nano-12b", "Nemotron Nano 12B"), (r"nemotron-nano-9b", "Nemotron Nano 9B"),
        (r"gemma-3-27b", "Gemma 3 27B"), (r"gemma-3-12b", "Gemma 3 12B"),
        (r"gemma-3-4b", "Gemma 3 4B"),
        (r"minimax-m2\.5", "MiniMax M2.5"), (r"minimax-m2\.1", "MiniMax M2.1"),
        (r"minimax-m2", "MiniMax M2"),
        (r"palmyra-x5", "Palmyra X5"), (r"palmyra-x4", "Palmyra X4"),
    ]
    for pat, nm in m:
        if re.search(pat, t):
            return nm
    return tail.split(":")[0]

changed = 0
for m in res["models"]:
    nm = nice(m["modelId"])
    if nm != m["name"]:
        m["name"] = nm
        changed += 1
res["models"].sort(key=lambda x: (x["provider"], x["modelId"]))

body = json.dumps(res, indent=1)
boto3.client("s3").put_object(Bucket=st["art_bucket"], Key="models/allowed-chat-models.json",
                              Body=body.encode(), ServerSideEncryption="aws:kms",
                              SSEKMSKeyId=st["kms_key_id"], ContentType="application/json")
json.dump(res, open("/home/z/my-project/aws/probe_result.json", "w"), indent=1)
print(f"names patched: {changed}; total {len(res['models'])} models re-uploaded")
for m in res["models"][:8]:
    print(" ", m["provider"], "|", m["name"], "|", m["modelId"])
