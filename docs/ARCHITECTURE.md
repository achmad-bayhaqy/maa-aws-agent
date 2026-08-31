# Arsitektur Teknis — MAA AWS Agent

Dokumen ini menjelaskan arsitektur sistem secara end-to-end: komponen, alur data,
pola desain, dan keputusan penting yang diambil selama implementasi.

## 1. Peta Komponen

| Komponen | Service AWS | ID Produksi | Peran |
|---|---|---|---|
| Frontend | Amplify Hosting | `dnhise495bdci` | Next.js static export, mobile-first |
| Identity | Cognito User Pool | `us-east-1_l76zCTRHQ` | Login + TOTP MFA wajib + grup superadmin |
| API Edge | API Gateway REST | `bklw93lic3` (stage `v1`) | Router HTTP + Cognito authorizer + throttling 40/80 |
| WAF | WAFv2 | `maa-agent-api-waf` | Rate limit 2000/5m + Managed Rules |
| Proxy | Lambda | `maa-agent-edge` | Proxy tipis SigV4 → Runtime, admin, KB |
| Otak | AgentCore Runtime | `maa_agent_runtime-jo754738JS` | LLM orchestration + 14 tools |
| Memori | AgentCore Memory | `maaagentmemory-4sS7MtCwmH` | Riwayat → konteks lintas sesi |
| Tools MCP | AgentCore Gateway | `maa-agent-gateway-i7pqul6pud` | Web tools via MCP |
| Eksekusi kode | AgentCore Code Interpreter | `maacodeinterpreter-4uJsoLieIf` | Analitik data/kode |
| Governance | Policy Engine + Evaluations | `maa_agent_policy_engine-tqf9q5mcv2` | Kebijakan + penilaian kualitas |
| Safety | Bedrock Guardrail | `ff25xera9ylt` | Konten, PII, prompt-attack |
| Pengetahuan | Knowledge Base + S3 Vectors | `EQ0YEDUC9N` / index 1024d | RAG multimodal (PDF/XLSX/PNG) |
| State | DynamoDB ×3 | sessions / traces / confirmations | Sesi, konfirmasi (TTL), jejak |
| Kripto | KMS | `04cd02e6` | Enkripsi objek & artefak |
| Demo | EC2 t3.micro ×2 | `maa-demo-app-01/02` | Target operasi demo (stopped) |

## 2. Alur Chat End-to-End

1. **Auth**: browser login Cognito (password → challenge TOTP) → `IdToken` (1 jam).
2. **POST /chat**: API GW memvalidasi token via Cognito authorizer → lambda edge
   membuat record sesi DynamoDB (`status=processing`) → lambda **self-invoke async**
   (agar respons cepat `202` tanpa menunggu LLM) → payload diteruskan ke AgentCore Runtime.
3. **Runtime**: routing mode (AUTO/FAST/DEEP/MANUAL) → memilih model → guardrail check →
   loop tool (EC2/EKS/RDS/S3/KB search/… ) → jawaban final → **runtime adalah
   single-writer** yang menulis pesan user+assistant ke DynamoDB.
4. **Polling**: browser polling `GET /chat/status` (1,2 s) sampai `status=done`;
   jawaban berisi `versions[]`, `autoRoute` (mode+model+alasan), `clarify` bila ambigu.
5. **Trace**: runtime menulis event ke CloudWatch Logs `/maa/agent/trace`;
   UI polling `GET /chat/trace?after=<ts>`, render timeline (routing/tool/thinking).

## 3. Keputusan Desain Penting

### 3.1 Kenapa proxy tipis (bukan logika di edge)?
Semua kecerdasan ada di AgentCore Runtime agar mudah di-upgrade tanpa menyentuh edge.
Lambda edge hanya: auth claims, CRUD sesi ringan, presigned URL, admin Cognito,
penerusan payload. Efeknya: rotasi model/logika tidak menyentuh API.

### 3.2 Self-invoke async
Chat bisa berjalan >30 detik (reasoning + tools). Lambda edge memanggil dirinya sendiri
dengan `InvocationType=Event` sehingga client menerima `202` instan; proses berat
berjalan di invocation kedua. Status dibaca lewat DynamoDB, bukan menahan koneksi.

### 3.3 Single-writer untuk mencegah duplikasi
Versi awal menulis pesan dari dua tempat (edge & runtime) → jawaban dobel. Kini hanya
runtime yang menulis jawaban; edge hanya fallback bila runtime gagal menulis.

### 3.4 CORS via AWS_PROXY (bukan MOCK)
OPTIONS preflight ditangani lambda (header `Access-Control-Allow-*` dari `resp()`).
Mock integration pernah membuat preflight gagal silent di browser (error tidak terlihat).
Penting: **jangan** kembali ke MOCK tanpa Gateway Responses CORS.

### 3.5 Runtime ARM64 + boto3 slim
Runtime berjalan di Graviton (ARM64) — wheel harus `aarch64`. Lambda layer/vendor boto3
dibersihkan (19,8 MB → 6 MB) agar tetap dalam batas ukuran; HTTP server stdlib port 8080
dengan lazy clients menghindari batas init 30 detik.

### 3.6 Kontrak ID token
Frontend mengirim Cognito **ID token** pada header `Authorization: Bearer`.
Klaim yang dipakai: `sub` (userId), `cognito:username`, `email`, `cognito:groups`
(role `superadmin` bila anggota grup). Lambda membaca ketiganya dengan fallback.

## 4. Penanganan Konfirmasi Destruktif

1. Tool destruktif (mis. `ec2_terminate`, `s3_delete_bucket`) diminta agent → runtime
   membuat record `confirmations` (status `pending`, `challenge` acak, TTL 5 menit)
   dan **menghentikan eksekusi**.
2. UI menampilkan modal konfirmasi dua tahap: mengetik challenge **dua kali**.
3. `POST /chat/confirm {typed1, typed2, confirmToken}` → runtime memverifikasi
   → eksekusi nyata via STS single-use → trace `self_heal`/`tool` tercatat.

## 5. Knowledge Base & Memori

- **KB (S3 Vectors)**: dokumen di `s3://maa-agent-kb-docs-*/docs/`, ingestion
  multimodal (Nova) memahami diagram PNG, tabel XLSX, teks PDF. Query via
  `Retrieve` (fallback `QueryVectors`) dengan cosine 1024d. Upload dari UI memakai
  presigned URL SSE-KMS lalu `POST /kb/sync` memicu ingestion job.
- **AgentCore Memory**: setiap sesi menghasilkan ekstraksi memori jangka panjang;
  sesi baru memuat memori relevan → agent "mengingat" preferensi user lintas sesi.

## 6. Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Aksi destruktif keliru | Konfirmasi 2x + challenge + TTL + audit trace |
| Prompt injection | Guardrail prompt-attack + zero-trust role |
| Bocor PII | Guardrail PII + KMS + bucket TLS-only |
| Model region-blocked | Probe otomatis 88 model; katalog hanya yang lolos uji nyata |
| Duplikasi jawaban | Single-writer runtime |
| Preflight gagal silent | OPTIONS AWS_PROXY + error selalu tampil di UI |
