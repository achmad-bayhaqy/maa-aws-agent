---
name: maa-agentcore-orchestration
description: "Kamu membaca skill ini saat tugas pengguna menyangkut Amazon Bedrock AgentCore (runtime, gateway, memory, code interpreter) atau arsitektur agent di AWS."
---

# AWS AgentCore Expert
Kamu membaca skill ini saat tugas pengguna menyangkut Amazon Bedrock AgentCore (runtime, gateway, memory, code interpreter) atau arsitektur agent di AWS.

## Pengetahuan inti (diperbarui 2026-08)
- **AgentCore Runtime**: serverless untuk host agent (container/code PYTHON_3_12). Mode network: PUBLIC (internet) / SANDBOX (isolat) / VPC. Sesi HTTP via invoke_agent_runtime dengan runtimeSessionId >= 33 karakter. Idle session timeout dapat diatur (MAA pakai 900s).
- **Code Interpreter**: sandbox Python managed. networkMode PUBLIC memberi akses internet untuk scraping/API eksternal; SANDBOX terisolasi. Menyimpan file output (chart PNG) dan mengembalikan structuredContent (stdout/stderr/exitCode).
- **Gateway**: MCP endpoint untuk tool eksternal (web_search/web_fetch di MAA) dengan SigV4 dan target AWS Lambda/OpenAPI.
- **Memory**: LTM konteks lintas-sesi (semantic extraction asinkron). MAA menulis per giliran (user+assistant) dan mengingat top-k fakta per chat.
- **Identity**: workload identity per runtime; IAM role per-agent (MAA: maa-agent-runtime-role dengan STS scoped downstream).

## Pola jawaban
1. Kaitkan pertanyaan ke komponen AgentCore yang relevan dengan istilah resminya.
2. Saat merancang agent baru: sebutkan pilihan network mode, timeout, dan IAM least-privilege.
3. Contoh kode: pakai boto3 (invoke_agent_runtime / start_code_interpreter_session + invoke_code_interpreter).
4. Tambahkan praktik keamanan: jangan hardcode kredensial, pakai peran, audit via CloudTrail.
