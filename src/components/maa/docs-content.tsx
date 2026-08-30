'use client';

import { useEffect, useState } from 'react';
import { BookOpen, ShieldCheck } from 'lucide-react';

// Konten dokumentasi lengkap (Bahasa Indonesia) untuk drawer/halaman Dokumentasi.

const SECTIONS = [
  { id: 'ringkasan', label: 'Ringkasan' },
  { id: 'arsitektur', label: 'Arsitektur' },
  { id: 'fitur', label: 'Fitur' },
  { id: 'panduan-pengguna', label: 'Panduan Pengguna' },
  { id: 'panduan-admin', label: 'Panduan Admin' },
  { id: 'keamanan', label: 'Keamanan' },
  { id: 'biaya', label: 'Biaya' },
  { id: 'faq', label: 'FAQ' },
  { id: 'changelog', label: 'Changelog v3' },
];

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="maa-panel p-4">
      {title && <h4 className="mb-2 text-[13.5px] font-bold tracking-tight text-[var(--ink)]">{title}</h4>}
      <div className="space-y-2 text-[13px] leading-relaxed text-[var(--ink)]/85">{children}</div>
    </div>
  );
}

function Bullets({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2">
          <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} />
          <span className="min-w-0 break-words">{it}</span>
        </li>
      ))}
    </ul>
  );
}

const ARCH_ASCII = `┌─────────────┐   Cognito (MFA TOTP)   ┌──────────────────┐
│  Browser    │───────────────────────▶│  API Gateway+WAF │
│  (UI MAA)   │  Bearer IdToken        │  bklw93lic3      │
└─────────────┘                        └────────┬─────────┘
                                                │
                                   ┌────────────▼────────────┐
                                   │ Edge Lambda (orchestr.) │
                                   │ sesi·trace·KB·admin     │
                                   └─────┬─────────────┬─────┘
                                         │             │
                        ┌────────────────▼───┐   ┌─────▼──────────┐
                        │ AgentCore Runtime  │   │ DynamoDB       │
                        │ (otak agent, tool) │   │ sesi·trace·conf│
                        │ FAST/DEEP/MANUAL   │   └────────────────┘
                        └──┬──────┬──────┬───┘
                           │      │      │
                 ┌─────────▼┐ ┌───▼───┐ ┌▼──────────┐
                 │ Bedrock  │ │ S3 KB │ │ STS (STS: │
                 │ 88 model │ │Vectors│ │ 5 menit)  │
                 │+Guardrail│ │ +Docs │ └───────────┘
                 └──────────┘ └───────┘`;

export function DocsContent({ compact }: { compact?: boolean }) {
  const [active, setActive] = useState('ringkasan');

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) setActive(en.target.id);
        });
      },
      { rootMargin: '-15% 0px -70% 0px' }
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, []);

  const goto = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className={compact ? '' : 'grid gap-5 md:grid-cols-[190px_1fr]'}>
      {/* nav */}
      {!compact && (
        <nav className="hidden md:block" aria-label="Navigasi dokumentasi">
          <div className="sticky top-2 space-y-0.5 border-l border-[var(--line-soft)]">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => goto(s.id)}
                className={`block w-full border-l-2 py-1.5 pl-3 text-left text-[12px] font-medium transition-colors ${
                  active === s.id
                    ? 'border-[var(--accent)] text-[var(--ink)]'
                    : 'border-transparent text-[var(--muted-fg)] hover:text-[var(--ink)]'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </nav>
      )}
      <div className={`nice-scroll flex gap-1.5 overflow-x-auto pb-1 md:hidden ${compact ? 'hidden' : ''}`}>
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => goto(s.id)}
            className={`shrink-0 rounded-full border px-3 py-1 text-[11px] font-medium ${
              active === s.id
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]'
                : 'border-[var(--line-soft)] text-[var(--muted-fg)]'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* konten */}
      <div className="min-w-0 space-y-5">
        <section id="ringkasan" className="scroll-mt-4">
          <h3 className="mb-2 flex items-center gap-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">
            <BookOpen className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Ringkasan
          </h3>
          <Card>
            <p>
              <strong>MAA AWS Agent</strong> adalah insinyur cloud otonom: Anda bicara bahasa manusia,
              agent menjalankan operasi AWS yang nyata — listing resource, analisis biaya, membuat VPC,
              menghapus bucket, hingga memperbarui Knowledge Base — semuanya teraudit penuh.
            </p>
            <Bullets
              items={[
                <>Otak agent: <strong>Amazon Bedrock AgentCore Runtime</strong> (isolasi per-sesi, tanpa kredensial statis).</>,
                <>88 model chat yang bisa dipilih manual, atau mode <strong>AUTO</strong> yang memilih model otomatis.</>,
                <><strong>Live Trace</strong> transparan: setiap proses berpikir, tool call, dan hasil tampil real-time (sumber CloudWatch).</>,
                <>Operasi destruktif selalu lewat <strong>konfirmasi ganda</strong> (ketik challenge 2×, TTL 5 menit).</>,
                <>Login wajib <strong>MFA TOTP</strong>; sesi hangus otomatis setelah 15 menit idle.</>,
              ]}
            />
          </Card>
        </section>

        <section id="arsitektur" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">Arsitektur</h3>
          <div className="maa-panel p-3">
            <pre className="nice-scroll overflow-x-auto font-mono text-[10.5px] leading-[1.5] text-[var(--ink)]">{ARCH_ASCII}</pre>
          </div>
          <div className="mt-3">
            <Card>
              <Bullets
                items={[
                  <><strong>API Gateway + WAF</strong>: satu pintu HTTPS, rate-limit 2000 req/5 mnt, managed rules, CORS ketat.</>,
                  <><strong>Edge Lambda</strong>: autentikasi Cognito, manajemen sesi &amp; trace, presigned KB, admin API.</>,
                  <><strong>AgentCore Runtime</strong>: sandbox terisolasi tempat agent berpikir &amp; memanggil tool (AWS API via STS single-use).</>,
                  <><strong>DynamoDB</strong>: tabel sesi/trace/konfirmasi dengan TTL otomatis.</>,
                  <><strong>S3 Vectors + S3 Docs</strong>: penyimpanan vektor Knowledge Base (RAG) &amp; dokumen sumber.</>,
                ]}
              />
            </Card>
          </div>
        </section>

        <section id="fitur" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">Fitur</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Card title="F01 · Agent Chat Multi-Mode">
              <p>Empat mode: <strong>AUTO</strong> (default, routing otomatis FAST/DEEP sesuai kompleksitas), <strong>FAST</strong> (nova-micro + prompt caching), <strong>DEEP</strong> (gpt-oss-120b reasoning tinggi), <strong>MANUAL</strong> (pilih dari 88 model dengan badge tools/cache/reasoning).</p>
            </Card>
            <Card title="F02 · Live Trace & Audit">
              <p>Timeline event real-time: berpikir, tool call, hasil tool, pencarian KB, self-heal, konfirmasi — tiap event bertanda waktu &amp; model. Semua jejak tersimpan di DynamoDB/CloudWatch.</p>
            </Card>
            <Card title="F03 · Konfirmasi Ganda Destruktif">
              <p>Operasi berbahaya (hapus resource dll.) memicu modal challenge: ketik kode KONFIRMASI-…-hex dua kali, countdown 5 menit, baru agent mengeksekusi via STS sementara.</p>
            </Card>
            <Card title="F04 · Knowledge Base (RAG)">
              <p>Upload PDF/XLSX/PNG/CSV/MD ke KB → diindeks ke S3 Vectors → agent menjawab berdasarkan dokumen Anda (runbook, SOP, laporan). Agent juga bisa memperbarui KB sendiri bila diminta di chat.</p>
            </Card>
          </div>
          <div className="mt-3">
            <Card title="Fitur tambahan v3">
              <Bullets
                items={[
                  <>Edit pesan terkirim + <strong>versioning jawaban</strong> (navigasi ‹ k/n ›) + tombol copy.</>,
                  <>URL unik per sesi <span className="font-mono text-[11px]">/c/&lt;sessionId&gt;</span> — refresh tetap di sesi yang sama.</>,
                  <>Tema <strong>MAA Redline</strong>: 8 preset aksen + mode gelap.</>,
                  <>Chips <strong>klarifikasi terstruktur</strong> saat agent butuh kejelasan.</>,
                  <>Galeri gambar hasil tool/agent (klik untuk membuka ukuran penuh).</>,
                  <>Menu <strong>Superadmin</strong>: undang user via email, enable/disable, hapus user.</>,
                ]}
              />
            </Card>
          </div>
        </section>

        <section id="panduan-pengguna" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">Panduan Pengguna</h3>
          <div className="space-y-3">
            <Card title="Login & MFA TOTP">
              <Bullets
                items={[
                  <>Masukkan username &amp; password pada halaman login.</>,
                  <>Pendaftaran pertama: pindai QR dengan aplikasi authenticator (Google Authenticator, Authy, 1Password), lalu masukkan kode 6 digit.</>,
                  <>Login berikutnya: masukkan kode TOTP dari aplikasi (berubah tiap 30 detik).</>,
                  <>Sesi hangus otomatis setelah <strong>15 menit</strong> tanpa aktivitas.</>,
                ]}
              />
            </Card>
            <Card title="Mode AUTO / FAST / DEEP / MANUAL">
              <Bullets
                items={[
                  <><strong>AUTO (default)</strong> — agent menilai kompleksitas pertanyaan lalu memilih FAST atau DEEP sendiri. Alasan pemilihan tampil di chip bawah jawaban.</>,
                  <><strong>FAST</strong> — balasan kilat untuk pertanyaan sederhana (Amazon Nova Micro, hemat &amp; prompt-cached).</>,
                  <><strong>DEEP</strong> — reasoning tinggi untuk analisis multi-langkah (GPT-OSS 120B).</>,
                  <><strong>MANUAL</strong> — pilih model apa pun dari 88 katalog; hanya model berbadge <em>tools</em> yang bisa menjalankan tool AWS.</>,
                ]}
              />
            </Card>
            <Card title="Konfirmasi Destruktif">
              <p>Saat Anda meminta operasi berbahaya (mis. “hapus bucket X”), agent berhenti dan memunculkan modal: operasi + input ditampilkan, lalu ketik challenge (contoh <span className="font-mono text-[11px]">KONFIRMASI-HAPUS-7f3a</span>) di dua kolom. Tombol Eksekusi aktif hanya bila keduanya sama persis. TTL 5 menit — lewat itu, minta ulang.</p>
            </Card>
            <Card title="Edit Pesan & Versioning">
              <Bullets
                items={[
                  <>Arahkan kursor ke pesan Anda → ikon <strong>✏️ edit</strong> → ubah teks → <strong>Kirim ulang</strong>. Percakapan setelah titik itu diregenerasi.</>,
                  <>Jawaban lama tidak hilang: gunakan navigasi <span className="font-mono text-[11px]">‹ k/n ›</span> di bawah jawaban untuk membandingkan versi.</>,
                  <>Tombol <strong>⧉</strong> menyalin markdown mentah (jawaban maupun pesan Anda).</>,
                ]}
              />
            </Card>
            <Card title="URL Sesi">
              <p>Setiap sesi punya URL <span className="font-mono text-[11px]">/c/&lt;sessionId&gt;</span>. Bookmark/refresh/salin ke rekan — semua akan membuka percakapan yang sama.</p>
            </Card>
          </div>
        </section>

        <section id="panduan-admin" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">Panduan Admin (Superadmin)</h3>
          <div className="space-y-3">
            <Card title="Mengundang User">
              <Bullets
                items={[
                  <>Buka menu <strong>Admin</strong> di sidebar (hanya tampil untuk role superadmin).</>,
                  <>Masukkan email + role (user / superadmin) → <strong>Undang</strong>.</>,
                  <>Cognito mengirim email berisi username &amp; password sementara dari <span className="font-mono text-[11px]">no-reply@verificationemail.com</span>.</>,
                  <>User wajib mendaftar MFA TOTP saat login pertama.</>,
                ]}
              />
            </Card>
            <Card title="Kelola User">
              <p>Tabel user menampilkan status (CONFIRMED / FORCE_CHANGE_PASSWORD / UNCONFIRMED), switch enable/disable (blokir akses tanpa hapus), dan tombol hapus permanen (dengan dialog konfirmasi).</p>
            </Card>
            <Card title="Kelola Knowledge Base">
              <Bullets
                items={[
                  <>Menu <strong>Knowledge Base</strong> → drag &amp; drop file (PDF/XLSX/PNG/JPG/CSV/JSON/MD/TXT, maks 20 MB).</>,
                  <>Setelah unggah, indeks berjalan otomatis (1–2 menit); tombol <strong>Sync KB sekarang</strong> memaksa sinkronisasi ulang.</>,
                  <>Hapus dokumen lama langsung dari daftar. Agent juga bisa memperbarui KB bila diminta di chat.</>,
                ]}
              />
            </Card>
          </div>
        </section>

        <section id="keamanan" className="scroll-mt-4">
          <h3 className="mb-2 flex items-center gap-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">
            <ShieldCheck className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Keamanan
          </h3>
          <Card>
            <Bullets
              items={[
                <><strong>MFA TOTP wajib</strong> untuk semua user; WAF rate-limit 2000 req/5 mnt + managed rules (SQLi/XSS/log4j) melindungi API.</>,
                <><strong>Zero static credentials</strong> — agent memakai STS single-use: kredensial sementara berumur 900 detik (batas bawah AWS), sekali pakai, lalu dibuang.</>,
                <><strong>Bedrock Guardrail</strong>: filter konten berbahaya, PII, dan prompt injection (terverifikasi GUARDRAIL_INTERVENED pada uji serangan).</>,
                <><strong>Enkripsi KMS AES-256</strong> untuk semua bucket &amp; tabel; TLS-only bucket policy.</>,
                <><strong>Konfirmasi ganda</strong> untuk operasi destruktif + audit CloudTrail penuh.</>,
              ]}
            />
          </Card>
        </section>

        <section id="biaya" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">Biaya</h3>
          <div className="maa-panel overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-[var(--line)] bg-[var(--surface)]">
                  <th className="px-3 py-2 text-left font-semibold">Komponen</th>
                  <th className="px-3 py-2 text-left font-semibold">Biaya idle</th>
                  <th className="px-3 py-2 text-left font-semibold">Catatan</th>
                </tr>
              </thead>
              <tbody className="text-[var(--ink)]/85">
                <tr className="border-b border-[var(--line-soft)]"><td className="px-3 py-1.5">AgentCore / Lambda / API GW</td><td className="px-3 py-1.5 font-mono">~$0</td><td className="px-3 py-1.5">serverless — bayar per panggilan</td></tr>
                <tr className="border-b border-[var(--line-soft)]"><td className="px-3 py-1.5">DynamoDB + S3</td><td className="px-3 py-1.5 font-mono">~$0</td><td className="px-3 py-1.5">TTL + penyimpanan mikro</td></tr>
                <tr className="border-b border-[var(--line-soft)]"><td className="px-3 py-1.5">EC2 demo (2× t3.micro)</td><td className="px-3 py-1.5 font-mono">Rp0</td><td className="px-3 py-1.5">stopped — idle tanpa biaya komputasi</td></tr>
                <tr><td className="px-3 py-1.5">AWS WAF</td><td className="px-3 py-1.5 font-mono">~$6/bln</td><td className="px-3 py-1.5">komponen kontinu satu-satunya</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section id="faq" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">FAQ</h3>
          <div className="space-y-3">
            <Card title="Kenapa jawaban lambat di mode DEEP?">
              <p>DEEP menjalankan reasoning tinggi (chain-of-thought panjang) sebelum menjawab — biasanya 10–40 detik. Pantau progresnya di panel Live Trace.</p>
            </Card>
            <Card title="Chat tidak menjalankan tool padahal saya pilih model di MANUAL?">
              <p>Hanya model berbadge <strong>tools</strong> (tool-compatible) yang bisa memanggil tool AWS. Model berbadge <em>teks</em> hanya menghasilkan teks.</p>
            </Card>
            <Card title="Saya terlanjur ketik challenge salah — bagaimana?">
              <p>Tombol Eksekusi tetap terkunci sampai kedua kolom sama persis dengan challenge. Tantangan juga kedaluwarsa dalam 5 menit; minta ulang operasinya bila lewat.</p>
            </Card>
            <Card title="Apakah data percakaman disimpan?">
              <p>Ya, di DynamoDB dengan TTL otomatis — berguna untuk audit & lanjutkan sesi via URL. Hapus sesi bisa diminta ke agent.</p>
            </Card>
            <Card title="Kenapa saya diminta MFA terus?">
              <p>Setiap login baru meminta kode TOTP (keamanan). Kode berlaku 30 detik; pastikan jam perangkat akurat.</p>
            </Card>
          </div>
        </section>

        <section id="changelog" className="scroll-mt-4">
          <h3 className="mb-2 text-[15px] font-bold tracking-tight text-[var(--ink)]">Changelog v3</h3>
          <Card title="Frontend v3 — redesign total “MAA Redline”">
            <Bullets
              items={[
                <>UI baru: tema merah + garis hitam + latar putih, 8 preset aksen, mode gelap.</>,
                <>Logo baru pin map monogram MAA.</>,
                <>Mode <strong>AUTO</strong> default + dropdown 88 model (search, grouping, badge tools/cache/reasoning).</>,
                <>URL per sesi <span className="font-mono text-[11px]">/c/&lt;sessionId&gt;</span> — refresh aman.</>,
                <>Edit pesan + versioning jawaban + tombol copy.</>,
                <>Chips klarifikasi terstruktur dari agent.</>,
                <>Live Trace sumber CloudWatch dengan tipe event baru (web_search, code_interpreter, image_gen, memory_recall, clarify).</>,
                <>Galeri gambar hasil tool/agent.</>,
                <>Menu Superadmin (undang via email, enable/disable, hapus).</>,
                <>Dokumentasi lengkap in-app (halaman ini).</>,
              ]}
            />
          </Card>
        </section>
      </div>
    </div>
  );
}
