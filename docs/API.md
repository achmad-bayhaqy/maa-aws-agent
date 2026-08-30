# Kontrak API v3 — MAA AWS Agent

Base URL: `https://bklw93lic3.execute-api.us-east-1.amazonaws.com/v1`
Autentikasi: header `Authorization: Bearer <Cognito ID token>` (semua endpoint kecuali OPTIONS).
Semua respons JSON menyertakan header CORS (`Access-Control-Allow-Origin: *`).

Sumber kebenaran implementasi: `aws/lambda_edge/handler.py`.

## 1. Identity

### `GET /me`
Identitas pemanggil dari klaim token + fallback `admin_get_user`.

```json
{ "userId": "1428c498-…", "username": "architect",
  "email": "architect@maa.internal", "role": "superadmin" }
```

`role` = `superadmin` bila token memuat grup Cognito `superadmin`, selain itu
nilai `custom:role` (default `user`). UI memakai field ini untuk menampilkan menu Admin.

## 2. Chat

### `POST /chat` → `202`
```json
{ "message": "Hapus bucket demo lalu buat ulang", "mode": "AUTO",
  "modelId": null, "sessionId": null, "editFrom": null }
```
- `mode`: `AUTO` (default) | `FAST` | `DEEP` | `MANUAL`.
- Sesi baru: `sessionId` diabaikan → dibuat `chat-<hex>`, record DynamoDB berisi
  `title` (80 char pertama), TTL 30 hari.
- **Edit pesan**: kirim `sessionId` + `editFrom` (indeks versi) + `message` baru →
  runtime meregenerasi jawaban; pesan user mendapat `versions[]`.
- Validasi: pesan wajib, maks 6000 char.

### `GET /chat/status?sessionId=…`
Respons utama polling (interval UI 1,2 s):

```json
{ "sessionId": "chat-…", "status": "done|processing|error",
  "mode": "AUTO", "modelId": "amazon.nova-micro-v1:0",
  "autoRoute": { "chosen": "FAST", "model": "amazon.nova-micro-v1:0",
                 "reason": "pertanyaan ringkas/operasional…" },
  "title": "…", "messages": [
    { "role": "user", "text": "…", "ts": 1788100000000,
      "versions": [ { "text": "versi lama", "ts": … } ] },
    { "role": "assistant", "text": "…", "ts": …, "model": "…" } ],
  "pendingConfirmation": null }
```

`pendingConfirmation` terisi saat operasi destruktif menunggu konfirmasi:
```json
{ "confirmToken": "…", "challenge": "KONFIRMASI-hapus-bucket-a1b2",
  "operation": { "tool": "s3_delete_bucket", "params": { "bucket": "…" } } }
```

`clarify` (dari status atau blok `[[CLARIFY]]{json}` di pesan assistant) memicu UI
pertanyaan-opsi: `{ "question": "…", "options": ["…", "…"] }`.

### `POST /chat/confirm`
```json
{ "sessionId": "chat-…", "confirmToken": "…",
  "typed1": "KONFIRMASI-hapus-bucket-a1b2",
  "typed2": "KONFIRMASI-hapus-bucket-a1b2" }
```
Tahap 1: verifikasi → runtime menyetel konfirmasi tahap 2 (challenge baru).
Tahap 2: verifikasi → eksekusi tool destruktif via STS single-use.
Challenge salah / TTL (>5 m) lewat → ditolak.

### `GET /chat/trace?sessionId=…&after=0`
Live Trace dari CloudWatch `/maa/agent/trace`. `after` = timestamp ms terakhir yang
sudah dirender (incremental). Event: `{ts, type, content, model}`; `type` antara lain
`route`, `tool`, `thinking`, `guardrail`, `clarify`, `self_heal`, `iac`, `info`.

### `GET /chat/sessions`
25 sesi terakhir user (GSI `user-index`): `{sessionId, title, status, mode, createdAt, updatedAt}`.
URL sesi di UI: `/c/<sessionId>` (rewrite Amplify → `index.html`).

## 3. Models

### `GET /models`
Katalog 88 model Bedrock yang **lolos probe nyata** (tool-compatible):

```json
{ "autoDefaults": { "fast": "amazon.nova-micro-v1:0",
                    "deep": "openai.gpt-oss-120b-1:0" },
  "total": 88, "generatedAt": "…",
  "models": [ { "id": "…", "name": "GLM-5", "group": "…", "tools": true } ] }
```
Cache lambda 5 menit; sumber: `s3://maa-agent-artifacts-*/models/allowed-chat-models.json`.

## 4. Knowledge Base

| Endpoint | Method | Fungsi |
|---|---|---|
| `/kb/docs` | GET | Daftar dokumen (`docs/` prefix) |
| `/kb/presign` | POST | `{name, contentType}` → `{uploadUrl, key}` (SSE-KMS, 10 m) |
| `/kb/sync` | POST | Memicu ingestion job Knowledge Base |
| `/kb/docs?key=docs/…` | DELETE | Hapus dokumen |

Format didukung: PDF, XLSX/XLS, PNG/JPG, CSV, JSON, MD, TXT. Ingestion multimodal
(Nova) menganalisis diagram/gambar, bukan sekadar teks.

## 5. Superadmin

Semua endpoint di bawah menolak non-superadmin (`403 khusus superadmin`).

| Endpoint | Method | Fungsi |
|---|---|---|
| `/admin/users` | GET | Daftar user (paging sampai 200) |
| `/admin/users` | POST | `{email, role}` → buat user + **email undangan otomatis** (password sementara dari Cognito default sender) |
| `/admin/users/status` | POST | `{username, enabled}` enable/disable |
| `/admin/users?username=…` | DELETE | Hapus user (tidak bisa diri sendiri) |
| `/admin/signout` | POST | Global sign out pemanggil |

## 6. Kode Error Umum

| Status | Penyebab |
|---|---|
| 400 | Payload tidak valid / pesan kosong / email tidak valid |
| 401 | Token hilang/kedaluwarsa (authorizer Cognito) |
| 403 | Bukan pemilik sesi, atau bukan superadmin |
| 404 | Route/method tidak ada |
| 429 | Throttling stage (40 rps / burst 80) atau WAF |
| 500 | Kesalahan internal (detail `error` di body) |
