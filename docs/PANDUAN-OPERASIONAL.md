# 🤖 MAA AWS Agent — Panduan Deploy & Akses

> Autonomous Enterprise Cloud Operations & Infrastructure Agent di AWS
> Sesuai PRD: Bedrock AgentCore Runtime • TOTP MFA Wajib • Live Trace • Zero-Trust

## 🔗 Akses

| Item | Nilai |
|---|---|
| **URL Aplikasi (HP)** | https://main.dnhise495bdci.amplifyapp.com |
| **Username** | `architect` |
| **Password** | ``<lihat aws/maa-user-credentials.json — tidak di-commit>`` |
| **Region** | us-east-1 |

Login pertama di perangkat baru: masukkan kode TOTP (6 digit) dari authenticator.
Untuk mendaftarkan perangkat baru, pindai **MAA-TOTP-QR.png** (terlampir) atau
masukkan secret key secara manual. Secret tersimpan di
`/home/z/my-project/aws/maa-user-credentials.json` (field `totp_secret`).

## 🏗️ Arsitektur Terpasang

```
[Browser HP] ──TLS──► [Amplify Hosting dnhise495bdci]
   │                        │ Cognito MFA TOTP (WAF 100 req/5m)
   ▼                        ▼
[API Gateway REST bklw93lic3] ◄── WAF 2000 req/5m + AWS Managed Rules
   │ Cognito Authorizer
   ▼
[Lambda maa-agent-edge] ──SigV4──► [★ AgentCore Runtime maa_agent_runtime]
                                     ├─ FAST  → amazon.nova-micro (prompt caching)
                                     ├─ DEEP  → openai.gpt-oss-120b (reasoning high)
                                     ├─ MANUAL→ 43 model Bedrock (incl. zai.glm-5)
                                     ├─ Guardrail ff25xera9ylt (content+PII+attack)
                                     ├─ Knowledge Base AZBQNYYPOY (S3 Vectors)
                                     └─ STS single-use → maa-agent-execution-role
```

## ✅ Fitur PRD yang Terimplementasi & Terverifikasi

- **F01**: Cognito + TOTP wajib (MFA_SETUP dipaksa saat pertama), password policy 12+,
  WAF rate-limit di Cognito & API, idle 15 menit → logout paksa
- **F02**: Selector FAST ⚡ / DEEP 🔬 / MANUAL 🛠️ (dropdown 43 model, grouped per vendor)
- **F03**: 14 tool otonom (EC2/VPC/S3/DDB/Lambda/RDS/Route53/ElastiCache/Cost/Logs/IaC/KB);
  konfirmasi ganda 2× string untuk operasi destruktif; sesi STS single-use per perintah
- **F04**: Live Trace realtime (thinking/tool/kb_search/error/self-heal/IaC/response)
- **NFR**: KMS AES-256 at-rest, TLS in-transit, CloudTrail audit otomatis,
  prompt caching Nova (cache read terverifikasi), 100% serverless (idle = Rp0)

## 📋 Sesi Uji yang Lolos

1. Login + enrollment TOTP (Cognito MFA_SETUP → verify → JWT)
2. Chat FAST: list EC2 → 2 instance demo disebut dengan detail
3. Chat DEEP: arsitektur + CloudFormation tervalidasi via iac_generate
4. Chat MANUAL (glm-5): analisis biaya Cost Explorer
5. Konfirmasi destruktif: bucket dibuat → perintah hapus → modal → ketik 2× → terhapus
6. KB search: prosedur restart EC2 dari runbook PDF; PNG dipahami via parsing multimodal
7. Live Trace polling realtime di UI mobile

## ⚠️ Catatan Kepatuhan

- STS `DurationSeconds` minimum AWS = 900 detik (15 menit). PRD meminta ≤5 menit →
  diimplementasikan pola *single-use per perintah* (kredensial dibuang langsung setelah
  eksekusi, tidak pernah di-cache). Dokumentasi lengkap di kode runtime.
- Anthropic Claude + OpenAI GPT-5.6 komersial diblokir pembatasan regional pada
  environment ini → DEEP mode memakai openai.gpt-oss-120b (OpenAI, native Bedrock).
- `bedrock:CreateAgent` (API lama) explicit-deny oleh environment → sesuai arsitektur
  PRD, orkestrasi berjalan di **Bedrock AgentCore Runtime** (service terpisah, diizinkan).

## 🧰 Operasi

```bash
# semua script deploy idempotent (aman dijalankan ulang):
python3 aws/deploy_foundation.py     # KMS, S3, DynamoDB, IAM
python3 aws/deploy_bedrock.py        # Guardrail, KB, dokumen, ingestion
python3 aws/deploy_cognito.py        # User Pool + MFA + user
python3 aws/deploy_runtime_role.py   # IAM role runtime
python3 aws/deploy_agentcore.py      # ★ build + deploy AgentCore Runtime
python3 aws/deploy_edge_apigw_waf.py # Lambda edge + API GW + WAF x2
python3 aws/seed_demo.py             # VPC + 2 EC2 demo (stopped)
python3 aws/deploy_amplify.py        # build + deploy frontend
python3 aws/test_e2e.py              # test end-to-end
```

State resource tersimpan di `aws/state.json`. Kredensial demo di
`aws/maa-user-credentials.json`. Zip kode runtime: `aws/agent_runtime/main.py`.

---

## Perubahan v2 (30 Agustus 2026) — Perbaikan Total

### Perbaikan kritis
1. **Chat tidak keluar apapun — FIXED.** Akar masalah: preflight CORS API Gateway mengembalikan 200 TANPA header `Access-Control-Allow-Origin`, sehingga semua fetch browser (POST /chat, GET /models) gagal diam-diam. Solusi: OPTIONS dipindah ke AWS_PROXY via Lambda + Gateway Responses (401/403/429/4XX/5XX) kini menyertakan header CORS. Terverifikasi E2E dari browser nyata di produksi.
2. **Pesan duplikat — FIXED.** Edge Lambda dan AgentCore Runtime sama-sama menulis pesan ke sesi. Kini single-writer (runtime), edge hanya fallback.
3. **Error tak terlihat — FIXED.** Semua kegagalan API kini tampil sebagai toast + bubble error di dalam chat.

### Model MANUAL: 47 model (sebelumnya 43 tersembunyi)
Dropdown kini: pencarian, tergrup per provider (Amazon, Z.ai, OpenAI-OS, Qwen, Mistral, NVIDIA, Meta, MiniMax, Google, DeepSeek, Moonshot, Writer), nama ramah + chip context (24k/128k/300k/mm). Semua model diuji ulang dgn tool-use nyata (converse + toolConfig); model via inference profile (us.*) ikut disertakan. Anthropic region-blocked oleh akun workshop.

### UI v2
- Layout 3 zona: sidebar (mode + workbench + profil), chat tengah (markdown penuh: tabel, code block + tombol salin, list), Live Trace panel kanan (timeline, expand/collapse, auto-scroll).
- Mode selector kartu dengan deskripsi; composer auto-grow; Enter kirim; suggestion chips; animasi halus; toasts; modal konfirmasi ganda dengan timer TTL 5 menit + validasi real-time.
- Idle 15 menit tetap mengakhiri sesi (revokes token + global signout).

### Optimasi biaya (berlaku hari ini)
- CloudWatch retention 7 hari (edge + semua runtime).
- Cache daftar model 1 jam → 5 menit (konsistensi dropdown).
- WAF: rule body-inspection (XSS_BODY/SQLi_BODY/Log4JRCE) → Count agar percakapan soal keamanan tidak false-positive diblok; rate-limit per-IP 2000/5menit tetap Block.
- Semua serverless; idle = Rp0 kecuali WAF (~$6/bln).

### URL & kredensial (tidak berubah)
- Aplikasi: https://main.dnhise495bdci.amplifyapp.com
- API: https://bklw93lic3.execute-api.us-east-1.amazonaws.com/v1
- User: `architect` / ``<lihat aws/maa-user-credentials.json — tidak di-commit>`` + TOTP (secret: aws/maa-user-credentials.json, QR: MAA-TOTP-QR.png)
