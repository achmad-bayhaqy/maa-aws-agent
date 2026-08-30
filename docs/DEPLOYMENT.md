# Panduan Deploy — MAA AWS Agent

Semua deploy dilakukan lewat script Python + boto3 yang **idempoten** (aman dijalankan
ulang). State terpusat di `aws/state.json` — registry seluruh resource yang dibuat.

## 0. Prasyarat

- Akun AWS dengan izin: IAM, KMS, S3, DynamoDB, Cognito, Lambda, API Gateway,
  WAF, Bedrock, Bedrock AgentCore, Amplify, EC2.
- Python 3.12+, boto3 (versi dengan `bedrock-agentcore` & `bedrock-agentcore-control`),
  Node.js/bun untuk build frontend.
- Kredensial CLI disimpan di `scripts/awsenv.sh` (buat sendiri, **jangan pernah di-commit**):

```bash
export AWS_DEFAULT_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="AKIA…"
export AWS_SECRET_ACCESS_KEY="…"
# + AWS_SESSION_TOKEN bila memakai STS
```

## 1. Urutan Eksekusi

```bash
source scripts/awsenv.sh && cd aws
python3 deploy_foundation.py      # 1  KMS, S3 ×3, DynamoDB ×3, IAM ×4
python3 deploy_bedrock.py         # 2  Guardrail, KB (S3 Vectors), unggah dokumen
python3 deploy_cognito.py         # 3  User pool + TOTP wajib + app client + user admin
python3 deploy_runtime_role.py    # 4  IAM role runtime (least privilege)
python3 deploy_v3_agentcore.py    # 5  Memory, Gateway, Policy, Code Interpreter, Evaluations
python3 deploy_runtime_v3.py      # 6  Zip kode agent → Runtime v3 + smoke invoke
python3 deploy_edge_apigw_waf.py  # 7  Lambda edge, API GW (13 route), WAF, Gateway Responses
python3 seed_demo.py              # 8  VPC demo + 2× EC2 t3.micro (stopped)
python3 test_e2e_v3.py            # 9  Uji end-to-end (login → chat → edit → trace)
python3 deploy_amplify.py         # 10 Build static export → Amplify Hosting
```

Estimasi total ~15–25 menit. Script ke-N **bergantung state** dari script (N-1) —
jalankan berurutan pada deploy pertama.

## 2. Yang Dibuat Tiap Tahap

### Tahap 1 — Foundation
KMS key (alias maa-agent), bucket `maa-agent-kb-docs-<acct>` (dokumen KB),
`maa-agent-artifacts-<acct>` (katalog model), `maa-agent-vectors-<acct>` (S3 Vectors);
semua KMS + TLS-only + versioned. DynamoDB `maa-agent-sessions` (GSI user-index, TTL),
`maa-agent-confirmations` (TTL), `maa-agent-traces`. IAM: orchestrator, execution
(zero-trust deny), kb-role, instance-profile demo.

### Tahap 2 — Bedrock
Guardrail (konten + PII + prompt attack) — diuji: prompt benign → NONE, injeksi →
INTERVENED. Knowledge Base `EQ0YEDUC9N` berbasis S3 Vectors (1024d cosine) dengan
`supplementalDataStorageConfiguration` (wajib untuk parsing multimodal Nova),
lalu ingestion 3 dokumen contoh (PDF/XLSX/PNG).

### Tahap 3 — Cognito
User pool + **SetUserPoolMfaConfig TOTP ON**, password policy 12+, app client
(tanpa secret, flow USER_PASSWORD_AUTH), grup `superadmin`, user awal.
Login pertama memicu `MFA_SETUP` (QR QRCode di UI).

### Tahap 5–6 — AgentCore
Memory, Gateway (target web tools), Policy Engine, Code Interpreter, Evaluator +
Online evaluation. Runtime v3: kode `aws/agent_runtime/main.py` di-zip → S3 →
`CreateAgentRuntime` (PYTHON_3_12, HTTP protocol, ARM64). **Catatan build**:
wheels harus `aarch64`; boto3/botocore di-vendor versi slim; HTTP server stdlib
port 8080 + lazy client agar init <30 s. Setelah READY, smoke invoke AUTO.

### Tahap 7 — Edge + API GW + WAF
Lambda `maa-agent-edge` (256 MB, timeout 240 s). API Gateway REST: 13 route +
authorizer Cognito + throttling 40/80. **Penting**: OPTIONS semua route memakai
integration `AWS_PROXY` (lambda mengembalikan header CORS) — bukan MOCK.
Gateway Responses (`DEFAULT_4XX/5XX`, `UNAUTHORIZED`, `THROTTLED`) juga diberi
header CORS agar error tetap terbaca browser. WAF: rate 2000/5m + managed rules
(SQLi/XSS/Log4J di-override `Count` — pertanyaan keamanan tentang exploit tidak
boleh diblok; eksekusi tetap dicek guardrail).

### Tahap 9 — E2E
`test_e2e_v3.py`: login TOTP → `/me` → `/models` (88 + autoDefaults) → `POST /chat`
AUTO (asersi `autoRoute`) → polling done → trace ≥2 event → **edit pesan**
(`editFrom`, asersi `versions[]`) → daftar sesi.

### Tahap 10 — Amplify
Build dir terpisah (`aws/amplify-build`) dengan `next.config` `output: "export"` +
`.env.production` (pool/client/API URL) → `next build` → zip `out/` →
`create_deployment` (zipUploadUrl) → `start_deployment`. Custom rule Amplify
me-rewrite path tanpa ekstensi (termasuk `/c/<sessionId>`) → `/index.html` status 200.

## 3. Verifikasi Pasca-Deploy

```bash
# preflight CORS
curl -X OPTIONS $API_URL/me -H "Origin: https://main.d3m7p7m7eyo6tj.amplifyapp.com" \
     -H "Access-Control-Request-Method: GET" -D - -o /dev/null   # 200 + ACAO
# login + chat ringkas
python3 aws/test_e2e_v3.py
```

## 4. Rotasi & Perubahan Kode

| Perubahan | Perintah ulang |
|---|---|
| Kode agent (`agent_runtime/main.py`) | `python3 deploy_runtime_v3.py` |
| Lambda edge (`lambda_edge/handler.py`) | upload zip ulang (lihat deploy_edge) |
| Route API GW | `python3 fix_apigw_me.py` (idempoten patch + redeploy) |
| Frontend | `python3 deploy_amplify.py` |
| Katalog model | `python3 ../scripts/probe_models_v2.py` (unggah S3) |

## 5. Optimasi Biaya

- Serverless penuh: Lambda, Runtime AgentCore (idle ≠ billed), DynamoDB on-demand + TTL.
- EC2 demo **stopped** (Rp0); hapus bila tak dipakai (`aws ec2 terminate-instances`).
- CloudWatch log retention 7 hari (edge + runtime).
- Cache katalog model 5 menit; prompt caching untuk FAST (nova-micro).
- Biaya kontinu utama: **WAF ~$6/bln** + penyimpanan micro.

## 6. Tear-down

Hapus berurutan kebalikan tahap (Amplify app → API GW → WAF → Lambda → Runtime/
Memory/Gateway/Policy/Eval → Cognito → KB → DynamoDB → bucket → KMS). Semua nama
resource berprefix `maa-` sehingga mudah difilter saat destroy.
