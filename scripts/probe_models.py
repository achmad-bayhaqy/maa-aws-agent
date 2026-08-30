#!/usr/bin/env python3
"""Probe Bedrock model behaviors: tool use, reasoning params, prompt caching.
Informs the orchestrator Lambda design."""
import boto3
import json
import time

rt = boto3.client("bedrock-runtime", region_name="us-east-1")

TOOLS = {
    "tools": [
        {
            "toolSpec": {
                "name": "get_time",
                "description": "Get current UTC time in ISO format",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    }
                },
            }
        }
    ]
}

SYSTEM = [{"text": "You are a terse ops agent. Use tools when needed. Reply in Indonesian."}]

def probe(model_id, label, extra=None, use_cache=False, max_tokens=200):
    msgs = [{"role": "user", "content": [{"text": "Jam berapa sekarang? Pakai tool."}]}]
    system = list(SYSTEM)
    if use_cache:
        system.append({"cachePoint": {"type": "default"}})
    kwargs = dict(
        modelId=model_id,
        messages=msgs,
        system=system,
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1},
        toolConfig=TOOLS,
    )
    if extra:
        kwargs["additionalModelRequestFields"] = extra
    t0 = time.time()
    try:
        resp = rt.converse(**kwargs)
        dt = time.time() - t0
        stop = resp["stopReason"]
        out = resp["output"]["message"]["content"]
        tools_called = [c["toolUse"]["name"] for c in out if "toolUse" in c]
        thinking = [c.get("reasoningContent", {}).get("reasoningText", {}).get("text", "")[:80]
                    for c in out if "reasoningContent" in c]
        usage = resp.get("usage", {})
        cache_read = usage.get("cacheReadInputTokens", 0)
        cache_write = usage.get("cacheWriteInputTokens", 0)
        print(f"OK   {label:28s} stop={stop:10s} tools={tools_called} dt={dt:.1f}s "
              f"in={usage.get('inputTokens')} out={usage.get('outputTokens')} "
              f"cacheR={cache_read} cacheW={cache_write} think={'yes' if thinking else 'no'}")
        return True
    except Exception as e:
        dt = time.time() - t0
        msg = str(e)[:180]
        print(f"FAIL {label:28s} dt={dt:.1f}s err={msg}")
        return False


print("=== Tool-use capability probes ===")
probe("amazon.nova-micro-v1:0", "nova-micro + tools", use_cache=True)
probe("amazon.nova-micro-v1:0", "nova-micro cachePoint", use_cache=True)
probe("openai.gpt-oss-120b-1:0", "gpt-oss-120b + tools",
      extra={"reasoning_effort": "high"})
probe("openai.gpt-oss-120b-1:0", "gpt-oss-120b no-reasoning",
      extra={"reasoning_effort": "low"})
probe("zai.glm-5", "glm-5 + tools")
probe("zai.glm-4.7-flash", "glm-4.7-flash + tools")
probe("moonshot.kimi-k2-thinking", "kimi-k2-thinking + tools")
probe("deepseek.r1-v1:0", "deepseek-r1 + tools")
probe("qwen.qwen3-next-80b-a3b", "qwen3-next-80b + tools",
      extra={"enable_thinking": True})
probe("meta.llama3-1-8b-instruct-v1:0", "llama3.1-8b + tools")
probe("mistral.magistral-small-2509", "magistral + tools")
probe("xai.grok-4.6", "grok-4.6 + tools")
probe("minimax.minimax-m2.5", "minimax-m2.5 + tools")
probe("writer.palmyra-x5-v1:0", "palmyra-x5 + tools")
probe("nvidia.nemotron-super-3-120b", "nemotron-super + tools")
probe("openai.gpt-5.6-terra", "gpt-5.6-terra + tools")
probe("openai.gpt-5.6-luna", "gpt-5.6-luna + tools")
probe("anthropic.claude-haiku-4-5-20251001-v1:0", "claude-haiku-4.5 (expect fail)")

print("\n=== Embedding probe (for KB fallback query) ===")
try:
    emb = rt.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": "prosedur incident response"}),
    )
    vec = json.loads(emb["body"].read())["embedding"]
    print(f"OK   titan-embed-v2 dim={len(vec)}")
except Exception as e:
    print(f"FAIL titan-embed-v2: {str(e)[:150]}")
