# MAA AWS Agent — FRONTEND SPEC v3 (2026-08-30)

Task ID: **F3** — baca dulu `/home/z/my-project/worklog.md` (konteks lengkap), lalu kerjakan sesuai spesifikasi ini. Kerjakan HANYA frontend. Backend dibangun paralel oleh agent lain; pakai API contract di bawah apa adanya.

## 0. Konteks & Masalah User (yang harus diselesaikan)
1. UI lama "dark amber" dianggap kurang proporsional → **redesign total**.
2. Tema harus: **merah + garis hitam + latar putih** (default) + opsi ganti warna.
3. Logo z.ai diganti **pin map merah monogram MAA** (outline hitam tipis).
4. Dropdown model MANUAL kosong/tidak jelas → **dropdown lengkap 88 model**, dan **mode AUTO default** yang memilih model otomatis sesuai kompleksitas.
5. Refresh menghilangkan sesi aktif → **URL unik per sesi** seperti ChatGPT.
6. Tidak bisa edit pesan terkirim → **edit pesan user + versioning jawaban + tombol copy**.
7. Baru: menu **Superadmin** (undang user via email), menu **Dokumentasi**, chips klarifikasi dari agent, render gambar hasil tool, Live Trace dari CloudWatch.
8. Bahasa UI: **Indonesia**.

## 1. Batasan Teknis (WAJIB)
- Next.js 15 App Router, **static export** (`output:"export"` diisi oleh deploy script — jangan menambah route handler `src/app/api/**`).
- **TIDAK BOLEH** menambah dependency npm baru. Gunakan yang sudah ada di `package.json` (React, Tailwind, lucide-react, shadcn/ui di `src/components/ui`, `qrcode` renderer sudah ada di page.tsx saat ini — cek dulu; jika `qrcode` tidak ada sebagai dep, gambar QR manual via library yang sudah terpakai saat ini. Cek `package.json`).
- Edit HANYA: `src/app/page.tsx`, `src/app/layout.tsx`, `src/app/globals.css`, `src/lib/maa.ts`, `src/components/maa/**`, `public/logo.svg`. JANGAN sentuh `aws/`, `scripts/`, `package.json`.
- Typecheck: `bunx tsc --noEmit` harus lolos (boleh abaikan error di folder lain).
- Semua fetch ke API via helper `apiFetch` di `src/lib/maa.ts` (sudah ada, perluas).
- Token auth di `sessionStorage` (sudah ada). Idle 15 menit → logout (pertahankan perilaku).

## 2. API CONTRACT v3 (backend AgentCore — endpoint sama, payload baru)

Base: `CONFIG.apiUrl` (https://bklw93lic3.execute-api.us-east-1.amazonaws.com/v1). Header: `Authorization: Bearer <IdToken>`.

| Endpoint | Method | Body/Query | Response |
|---|---|---|---|
| `/chat` | POST | `{message, mode: "AUTO"|"FAST"|"DEEP"|"MANUAL", modelId?, sessionId?, editFrom?}` | `202 {sessionId, status:"processing"}` — Jika `sessionId`+`editFrom` dikirim: edit pesan user index `editFrom` lalu regenerasi (versioning otomatis di server). Tanpa `sessionId` → sesi baru. |
| `/chat/status?sessionId=` | GET | — | `{sessionId, status:"processing"|"done"|"error", mode, modelId, autoRoute?:{chosen:"FAST"|"DEEP"|"MANUAL", model, reason}, title, messages: Msg[], pendingConfirmation?, clarify?:{question, options[]}, err?}` |
| `/chat/confirm` | POST | `{sessionId, confirmToken, typed1, typed2}` | `{status:"executed"|"mismatch"|"error", message?, result?}` |
| `/chat/trace?sessionId=&after=<ms>` | GET | — | `{events:[{ts:"<15-digit-ms>", type, content, model?}]}` — sumber: **CloudWatch** |
| `/chat/sessions` | GET | — | `{sessions:[{sessionId,title,status,mode,createdAt,updatedAt}]}` (terbaru dulu) |
| `/models` | GET | — | `{autoDefaults:{fast,deep}, models:[{modelId,name,provider,group,toolCompatible:bool,cacheSupported:bool,reasoning:bool}]}` — **88 model** |
| `/kb/docs` | GET | — | `{docs:[{key,name,size,updated}]}` |
| `/kb/presign` | POST | `{name,contentType}` | `{uploadUrl,key}` (PUT file ke uploadUrl) |
| `/kb/docs?key=` | DELETE | — | `{deleted}` |
| `/kb/sync` | POST | — | `{jobId,status}` |
| `/me` | GET | — | `{userId,username,email,role:"user"|"superadmin"}` |
| `/admin/users` | GET | — | `{users:[{username,email,status:"CONFIRMED"|"FORCE_CHANGE_PASSWORD"|"UNCONFIRMED",enabled,created,role}]}` (superadmin saja) |
| `/admin/users` | POST | `{email, role:"user"|"superadmin"}` | `{username, tempPasswordSent:true}` — **email undangan dikirim otomatis oleh Cognito** |
| `/admin/users/status` | POST | `{username, enabled:bool}` | `{updated:true}` |
| `/admin/users?username=` | DELETE | — | `{deleted:true}` |
| `/admin/signout` | POST | — | `{signedOut:true}` |

Tipe `Msg`: `{role:"user"|"assistant", text, ts, model?, edited?:bool, versions?: [{text,ts,model}]}`. Untuk pesan assistant yang punya `versions`: text = versi aktif, versions = riwayat versi lain (termasuk lama). UI tampilkan navigasi `‹ k/n ›` + tombol copy.

**Perilaku klarifikasi (structured clarification)**: saat agent ragu, `status.clarify` terisi `{question, options[]}` dan pesan assistant terakhir berisi jawaban meminta klarifikasi. Render **option chips** di bawah pesan; klik chip = kirim teks chip sebagai pesan user.

**Live Trace**: poling `/chat/trace?after=<lastEventTs>` tiap 1.5 dtk saat `status==="processing"`, dan sekali final saat selesai. Tipe event: `user_msg, thinking, tool_call, tool_result, kb_search, web_search, code_interpreter, image_gen, confirm_required, confirm_executed, error, self_heal, response, memory_recall, clarify` — beri ikon + warna berbeda (lihat TRACE_META, perluas).

## 3. Design System — "MAA Redline" (modern profesional)

### 3.1 Token warna (CSS variables di `:root`, switchable)
```
Light (default):
  --bg:#FFFFFF; --surface:#FAFAFA; --ink:#111111; --line:#111111; --line-soft:#E5E5E5;
  --muted:#6B7280; --accent:<preset>; --accent-soft:<preset 10%>; --accent-ink:#FFFFFF;
Dark:
  --bg:#0B0B0C; --surface:#141416; --ink:#F4F4F5; --line:#2E2E32; --line-soft:#232326;
  --muted:#9CA3AF; (accent tetap)
```
8 preset aksen: merah `#DC2626` (default), crimson `#E11D48`, biru `#2563EB`, teal `#0D9488`, hijau `#16A34A`, ungu `#7C3AED`, oranye `#EA580C`, pink `#DB2777`.
Persist di `localStorage["maa.theme"] = {accent:"#DC2626", dark:false}`; terapkan dengan `document.documentElement.style.setProperty` saat mount + saat ganti.
Tailwind: gunakan arbitrary values `bg-[var(--bg)] text-[var(--ink)] border-[var(--line)]` dsb.

### 3.2 Karakter visual "garis hitam"
- Border tegas 1px `--line` pada: header, sidebar kanan/kiri, card utama, input besar; border halus `--line-soft` untuk pemisah sekunder.
- Radius: 10px panel, 8px button/input, full untuk chip. Shadow halus `0 1px 2px rgb(0 0 0/.06)` saja.
- Button primary: `--accent` bg, teks putih, font-medium; secondary: bg putih/`--surface` + border `--line`; ghost: hover `--surface`.
- Heading: tracking-tight, font-semibold; angka/ID pakai `font-mono text-xs`.
- Spacing konsisten: gutter 16/24px; sidebar 264px desktop; trace rail 340px desktop (bisa collapse); bubble chat max-w `min(680px, 85%)`.
- Motion: transisi 150-200ms, `animate-in` subtle untuk pesan baru; skeleton saat loading.

### 3.3 Logo "Pin MAA" (WAJIB persis ini)
Buat `src/components/maa/logo.tsx` berisi komponen `<Logo size={n}/>` dan `<LogoWordmark/>`:
- Bentuk: pin lokasi ala Google Maps. Path pin (rounded pin), fill gradient merah `#DC2626→#991B1B`, stroke `#111111` strokeWidth 2 (tipis tegas), lingkaran dalam putih, monogram **"M"** tebal warna `#111111` di lingkaran (font sans bold).
- SVG standalone juga di-`public/logo.svg` (favicon + meta). Ganti `public/logo.svg` lama.
- Wordmark di header: pin (22px) + teks "MAA" bold + "AWS AGENT" kecil letter-spaced, warna `--ink`.
- Gunakan juga di: login card, sidebar header, favicon (`layout.tsx` icons), loading splash.

### 3.4 Layout (desktop ≥1024px)
```
┌──────────────────────────────────────────────────────────┐
│ HEADER 56px: [LogoWordmark] [chip sesi: title ▾] [mode?] [tema] [user] │
├──────────┬─────────────────────────────────┬─────────────┤
│ SIDEBAR  │  CHAT AREA (center, max 760px)  │ TRACE RAIL  │
│ 264px    │  - messages                     │ 340px (opt) │
│ +New     │  - clarify chips                │ (collapse→) │
│ sessions │  - composer bottom              │             │
│ menu:    │                                 │             │
│ Dokumen  │                                 │             │
│ Admin*   │                                 │             │
│ Tema     │                                 │             │
└──────────┴─────────────────────────────────┴─────────────┘
```
Mobile: sidebar & trace jadi Sheet (sudah ada ui/sheet). Semua proporsional — TIDAK BOLEH ada overflow horizontal; pesan panjang pakai `break-words` + code block `overflow-x-auto`.

## 4. Fitur Detail (semua WAJIB)

### F1 Auth & MFA (rapikan dari page.tsx lama)
- Card login center dengan Logo, ilustrasi tipis (garis grid merah), form email+password, pesan error jelas.
- MFA_SETUP: tampil QR (secret → otpauth URI, render via lib `qrcode` yang sudah dipakai; kalau tidak ada, generate QR via API SVG manual — cari cara tanpa dep baru) + input kode 6 digit.
- MFA challenge: input kode 6 digit.
- Setelah login: fetch `/me` → simpan `role` untuk menu Admin.
- Idle 15 menit → `signOutAll` + clear + redirect "/" dengan toast "Sesi berakhir karena idle".

### F2 Session URL (seperti ChatGPT)
- Baca `location.pathname`: `/c/<id>` → setelah token siap, load session itu (getStatus + trace from beginning).
- Saat membuka/membuat sesi → `history.pushState({}, "", "/c/<id>")`; sesi baru kosong → path `/`.
- Sidebar list sesi klik → pushState + load. Refresh selalu membuka sesi yang sama. Simpan juga `localStorage["maa.last.<userId>"] = sessionId`.

### F3 Composer + Mode + Dropdown 88 Model
- Textarea auto-grow (max 5 baris), Enter=kirim, Shift+Enter=baris baru, tombol kirim ikon panah.
- Selector mode di kiri composer: 4 chip — **AUTO (default)**, FAST, DEEP, MANUAL.
- MANUAL → popover ModelPicker: search box, grouped by `group` (Amazon Nova / Anthropic / OpenAI / Meta / Google / Mistral / AI21 / DeepSeek / Qwen / Lainnya…), tiap item: nama + provider + badge `tools` (emerald, kalau `toolCompatible`) atau `teks` (abu) + `cache`/`reasoning` mini-badges; item aktif ditandai. Menampilkan SEMUA model dari `/models` (±88).
- Setelah tiap jawaban, tampil chip kecil di bawah pesan assistant: mode yang dipakai → model (dari `status.autoRoute` atau `modelId`), mis. `AUTO → DEEP · gpt-oss-120b — pertanyaan multi-langkah & perlu reasoning`.

### F4 Edit pesan + versioning + copy (persis seperti ChatGPT)
- Hover bubble user → ikon ✏️ (edit) & ⧉ (copy). Edit → inline textarea + tombol "Kirim ulang" & "Batal".
- Kirim ulang → `POST /chat {sessionId, editFrom: <index pesan tsb>, message: <teks baru>, mode, modelId}` → status polling seperti biasa. Pesan user tsb dapat `edited:true`.
- Assistant message: tombol ⧉ copy (copy RAW markdown). Jika `versions?.length` → navigasi versi `‹ 2/3 ›` (switch menampilkan versi terpilih; tombol copy menyalin teks versi aktif).
- Toast kecil "Tersalin".

### F5 Klarifikasi (structured clarification)
- Jika `status.clarify` atau pesan assistant terakhir ada blok `[[CLARIFY]]{...}` (fallback parse), render card klarifikasi: pertanyaan + chips opsi (bisa multi-chip). Klik → kirim sebagai pesan user. Jangan render JSON mentahnya di markdown (strip blok dari teks).

### F6 Live Trace (sumber CloudWatch)
- Rail kanan: header "Live Trace" + status dot; event list vertikal dengan garis timeline vertikal, ikon per tipe, waktu (HH:mm:ss dari ts), konten (expandable, pre-wrap, mono utk tool args), badge model.
- Poling saat processing; auto-scroll bila user berada di bawah; tombol "Bersihkan view".
- Di mobile: tombol header ikon activity → Sheet.

### F7 Konfirmasi destruktif (2× ketik challenge)
- Pertahankan modal konfirmasi lama (restyle ke tema baru): tampil operation (tool+input), challenge string mono besar, 2 input ketik, tombol "Eksekusi" disabled sampai keduanya match, countdown TTL 5 menit. Setelah sukses → toast + refresh status.

### F8 Media (gambar hasil agent)
- Markdown renderer: render `![alt](url)` jadi `<img>` (rounded, border --line, max-h 420px, klik = buka tab baru). Link biasa `target=_blank rel=noopener`.
- Jika `status.attachments` ada (array `{type:"image",url,name}`) → galeri kartu di bawah pesan.

### F9 KB Drawer (tombol sidebar "Knowledge Base")
- List dokumen (nama, size, updated), upload via presign (drag&drop area), delete (confirm), tombol "Sync KB sekarang" → POST /kb/sync + toast status job. Tambahkan note: "Agent juga bisa memperbarui KB sendiri — minta di chat".

### F10 Superadmin (hanya role superadmin — dari /me)
- Menu sidebar "Admin" → drawer/halaman: form undang `{email, role}` → toast "Email undangan terkirim ke X dari no-reply@verificationemail.com"; tabel user (username, email, status badge, enabled switch, created); aksi: enable/disable, delete (confirm). Error non-superadmin → toast.

### F11 Dokumentasi (menu "Dokumentasi")
- Drawer full-height / halaman: nav kiri (anchor scroll): Ringkasan, Arsitektur (ASCII/SVG sederhana), Fitur (F01-F04), Panduan Pengguna (login MFA, mode AUTO/FAST/DEEP/MANUAL, konfirmasi destruktif, edit/versioning), Panduan Admin (undang user, KB), Keamanan (MFA TOTP, WAF, STS single-use, guardrail, KMS), Biaya (estimasi idle ~$0, WAF ~$6/bln), FAQ, Changelog v3 (list fitur baru). Konten padat, bahasa Indonesia, kartu-kartu rapi.

### F12 Tema switcher
- Popover "Tema" di header: 8 swatch (lingkaran warna, aktif = ring) + toggle Dark/Light. Ganti langsung terlihat semua (CSS vars). Simpan localStorage.

### F13 Sidebar sesi
- Item sesi: title (truncate 1 baris), waktu relatif ("2 mnt lalu"), status dot (processing spinner / done check / error x). Sesi aktif highlighted (bg --accent-soft + border kiri --accent). Tombol "+ Chat Baru" paling atas.

### F14 Error visibility (pelajaran v1!)
- SEMUA error harus terlihat: top-banner merah di chat area bila error status; toast untuk aksi gagal; composer tidak pernah silent-fail. Tambah retry button pada error banner.

## 5. Struktur file target
```
src/lib/maa.ts                (perluas: type baru, api baru: /me /admin /models v3, editChat, trace meta)
src/app/page.tsx              (auth flow + router sesi URL)
src/app/layout.tsx            (favicon logo, title, meta Indonesia)
src/app/globals.css           (tokens tema, scrollbar, animasi)
src/components/maa/logo.tsx           (BARU: pin MAA svg)
src/components/maa/theme.ts           (BARU: preset + apply/persist)
src/components/maa/theme-switcher.tsx (BARU)
src/components/maa/chat-app.tsx       (rewrite: orchestrasi utama)
src/components/maa/sidebar.tsx        (BARU: sesi + menu)
src/components/maa/composer.tsx       (BARU: textarea + mode + picker)
src/components/maa/model-picker.tsx   (rewrite: 88 model grouped+badges)
src/components/maa/message-list.tsx   (BARU: bubble, edit inline, version nav, copy, clarify chips, attachments)
src/components/maa/markdown.tsx       (perluas: img render, table tetap)
src/components/maa/trace-panel.tsx    (rewrite: tipe baru, timeline)
src/components/maa/confirm-modal.tsx  (restyle)
src/components/maa/drawers.tsx        (rewrite: KB, Docs, Admin, Tema)
src/components/maa/docs-content.tsx   (BARU: konten dokumentasi panjang)
```
Boleh menambah file kecil lain di components/maa — jelaskan di laporan.

## 6. Kualitas (checklist sebelum lapor selesai)
- [ ] `bunx tsc --noEmit` bersih untuk file yang disentuh
- [ ] Tidak ada `console.log` lintah; tidak ada TODO kosong
- [ ] Semua teks UI Indonesia; angka ID mono
- [ ] Empty states: chat baru (saran chip contoh: "List EC2", "Analisis biaya 30 hari", "Buat VPC bernama staging", "Apa runbook insiden database?"), trace kosong, sesi kosong, admin kosong
- [ ] Loading: skeleton pesan saat poll pertama, spinner di tombol
- [ ] Responsive 360px → 1440px; tidak ada overflow; sidebar jadi sheet di <1024px
- [ ] Kontras OK di light & dark (teks muted min 4.5:1 di surface)

## 7. Laporan (WAJIB di akhir)
Append ke `/home/z/my-project/worklog.md` dengan format standar (Task ID: F3), daftar file yang diubah/dibuat, keputusan implementasi, dan hal yang perlu diverifikasi backend. Laporan ke agent induk: ringkas (file + fitur status).
