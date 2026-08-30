# Keamanan — MAA AWS Agent

## 1. Identity & Access Management

- **TOTP MFA wajib** di level user pool (`SetUserPoolMfaConfig` TOTP `ON`).
  Login pertama memaksa `MFA_SETUP`: UI merender QR (lib qrcode, offline) yang
  dipindai authenticator. Tanpa kode TOTP 6 digit, tidak ada token yang diterbitkan.
- **Password policy** minimal 12 karakter dengan kompleksitas; kredensial demo
  tersimpan lokal (`aws/maa-user-credentials.json`, dikecualikan dari git).
- **Role model**: role `superadmin` berasal dari **grup Cognito** `superadmin`
  (klaim `cognito:groups`) — bukan atribut yang bisa diubah user. Endpoint admin
  memverifikasi role di server; UI hanya menyembunyikan menu.
- **Idle logout 15 menit** di frontend + `admin_user_global_sign_out` saat signout.
- **Zero-trust IAM**: role eksekusi resource memakai deny eksplisit di luar
  whitelist; aksi resource berjalan lewat **STS single-use** (sesi ≤15 menit,
  dibuat per aksi lalu dicabut). Lambda edge tidak punya izin resource — hanya
  invoke runtime + Cognito admin + S3 presign terbatas.

## 2. Network & Application Protection

- **AWS WAF** pada API Gateway (2000 req/5m Block) dan Cognito (100 req/5m):
  rate limit + AWS Managed Rules. SQLi/XSS/Log4J di-*override* `Count` — alasan:
  agent dites membedah exploit; blok body oleh WAF membuat produk tak teruji.
  Pertahanan konten sejatinya ada di guardrail, bukan WAF.
- **API Gateway**: Cognito authorizer (ID token), throttling 40 rps/burst 80,
  payload max 6.000 char untuk chat.
- **TLS 1.3** end-to-end (Amplify → API GW → Runtime).
- **CORS ketat**: preflight via AWS_PROXY; response header hanya
  `Authorization, Content-Type`.

## 3. Data Protection

- **KMS SSE** untuk semua bucket (dokumen KB, artefak, vectors); bucket policy
  menolak koneksi non-TLS (`aws:SecureTransport = false`).
- **DynamoDB TTL**: sesi 30 hari, konfirmasi 5 menit (kedaluwarsa otomatis),
  trace dibatasi retensi log 7 hari (CloudWatch).
- **Presigned upload** hanya prefix `docs/`, whitelist ekstensi, SSE-KMS wajib,
  TTL 10 menit.

## 4. AI Safety

- **Guardrail Bedrock** (`ff25xera9ylt`): filter konten, PII (email, phone, SSN,
  AWS credential), prompt-attack — diuji: injeksi klasik → `GUARDRAIL_INTERVENED`.
- **Konfirmasi dua tahap** untuk operasi destruktif: challenge string acak yang
  harus diketik dua kali, TTL 5 menit, satu pakai.
- **Policy Engine AgentCore**: kebijakan tool-level (mis. larang `iam_*`,
  batasi region). **Evaluations**: penilaian kualitas jawaban berkelanjutan
  (evaluator helpfulness + online evaluation).
- **Clarify-first**: instruksi ambigu → agent mengembalikan opsi (`clarify`)
  alih-alih menebak — mencegah eksekusi salah sasaran.

## 5. Secret Hygiene (Git)

Repositori ini menerapkan praktik berikut — **wajib dipertahankan**:

1. `.gitignore` mengecualikan: `scripts/awsenv.sh` (kredensial AWS),
   `aws/maa-user-credentials.json` (password + secret TOTP), `aws/maa-totp-qr.png`
   (QR berisi secret), `.env*`, `worklog.md` (log internal yang menyebut kredensial).
2. **Riwayat git dibersihkan** sebelum push pertama: commit lama yang pernah
   menyimpan file kredensial tidak ikut didorong (fresh history).
3. Token GitHub (fine-grained PAT) hanya dipakai sekali saat push via URL
   kredensial sementara — **tidak pernah ditulis ke file** atau remote config.
4. Bila kredensial terlanjur terekspos: rotasi segera (IAM access key, password
   Cognito, secret TOTP dengan re-enrollment, revoke PAT).

## 6. Audit & Traceability

- **Live Trace** per sesi (CloudWatch `/maa/agent/trace`): routing decision,
  pemanggilan tool, thinking ringkas, guardrail events — memudahkan forensik.
- DynamoDB `confirmations` menyimpan jejak persetujuan destruktif.
- CloudTrail (akun-level) merekam API call administratif; log Lambda retensi 7 hari.
