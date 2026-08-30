# Frontend v3 — MAA Redline

Frontend Next.js 15 (App Router, TypeScript, Tailwind) dengan desain **MAA Redline**:
aksen merah (`#DC2626`), garis hitam (`#111`), latar putih — modern, tegas, mobile-first.

Spesifikasi mengikat: `aws/FRONTEND-SPEC-V3.md`. Kode: `src/`.

## 1. Desain Sistem

- **Token CSS** di `:root` (light) + `.dark`: `--bg #FFF`, `--line #111`,
  `--accent` (preset aktif), radius 10/8 px, shadow lembut, bubble chat
  `max-w: min(680px, 85%)`, sidebar 264 px, trace rail 340 px, header 56 px.
- **8 preset aksen** (merah default): switcher tema tersimpan di
  `localStorage["maa.theme"]` dan diterapkan via `documentElement.style.setProperty`
  — ganti warna tanpa reload.
- **Logo MAA** (`components/maa/logo.tsx` + `public/logo.svg`): pin gradient merah
  `#DC2626→#991B1B`, stroke hitam 2.4, lingkaran putih, monogram **M** — dipakai di
  header, sidebar, login, splash, favicon.

## 2. Peta Komponen

| Komponen | Tanggung Jawab |
|---|---|
| `app/page.tsx` | Auth (login + challenge TOTP + MFA_SETUP QR), splash, boot chat-app |
| `chat-app.tsx` | Orkestrasi utama: state sesi, polling status/trace, routing URL `/c/<id>`, edit pesan, kirim/confirm |
| `composer.tsx` | Input + pilih mode (AUTO/FAST/DEEP/MANUAL) + picker model |
| `model-picker.tsx` | Dropdown 88 model, searchable, pengelompokan, badge default (`autoDefaults`) |
| `message-list.tsx` | Render pesan + `versions[]` (navigasi versi) + aksi copy/edit |
| `markdown.tsx` | Markdown lengkap (tabel, code w/ copy, list) + strip blok clarify |
| `trace-panel.tsx` | Live Trace timeline (expandable, incremental `?after=`) |
| `confirm-modal.tsx` | Konfirmasi destruktif 2 tahap + timer TTL challenge |
| `drawers.tsx` | Drawer KB (upload presigned + sync), drawer sesi, admin |
| `sidebar.tsx` | Navigasi sesi + menu (Dokumentasi, Admin, Tema) |
| `theme-switcher.tsx` | 8 preset aksen + dark mode |
| `docs-content.tsx` | Konten menu Documentation in-app |
| `lib/maa.ts` | Klien API (kontrak v3) + tipe + parser URL sesi |

## 3. Perilaku Kunci

### URL sesi (F06)
- Buka sesi → `history.pushState({sid}, '', '/c/<sessionId>')`.
- Refresh di URL itu → frontend parse path (`lib/maa.ts`) → muat sesi yang sama
  (Amplify rewrite path tanpa ekstensi → `/index.html`, status 200).
- Kembali ke beranda → `pushState('/')` → sesi baru.

### Mode & model (F02)
- Default **AUTO**; jawaban menampilkan chip rute: `autoRoute.chosen` + model +
  alasan (dari status polling).
- MANUAL membuka picker 88 model; badge "default" menandai `autoDefaults`
  FAST/DEEP dari `/models`.

### Edit pesan & versioning (F09)
- Tombol edit pada pesan user terakhir → isi composer dengan teks lama →
  kirim dengan `editFrom` (indeks) + `sessionId` → regenerasi.
- Pesan user menyimpan `versions[]` versi lama; UI menyediakan navigasi versi;
  input/output punya tombol copy.

### Clarify (F13/F14)
- `status.clarify` atau blok `[[CLARIFY]]{json}` pada pesan assistant terakhir
  di-strip dari markdown dan dirender sebagai kartu opsi; memilih opsi mengirim
  pesan balasan baru.

### Konfirmasi destruktif (F03)
- `status.pendingConfirmation` → modal dengan challenge yang harus diketik 2x,
  countdown TTL 5 menit; kedaluwarsa → tombol mati, minta ulang lewat chat.

### Live Trace (F04)
- Polling `/chat/trace?after=<ts>` tiap 1,5 s saat sesi aktif; event baru
  dianimasikan masuk; tiap event expandable (detail tool/JSON).

### Auth & sesi (F01)
- Login → challenge `SOFTWARE_TOKEN_MFA` (TOTP) → pada `MFA_SETUP` tampilkan QR.
- Token disimpan di memori (bukan localStorage); idle 15 m → logout + toast.

### Admin (F11) & Documentation (F12)
- Menu Admin tampil bila `/me.role === "superadmin"`: daftar user, tambah via
  email (undangan terkirim otomatis oleh Cognito), enable/disable, hapus.
- Menu Documentation merender `docs-content.tsx` (panduan penggunaan in-app).

## 4. Build & Deploy

Static export (tanpa server component API):

```bash
python3 aws/deploy_amplify.py   # menyiapkan build dir + .env.production
                                # → next build (output: "export") → zip → Amplify
```

Catatan: folder `src/app/api` dikecualikan dari build dir karena route handler
tidak kompatibel dengan static export; semua call langsung ke API Gateway.
`typescript.ignoreBuildErrors` sengaja aktif untuk iterasi cepat demo — untuk
produksi ketat, matikan dan perbaiki semua error tipe.
