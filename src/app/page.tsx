'use client';

import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import {
  Boxes, CheckCircle2, Eye, EyeOff, KeyRound, Loader2, Lock, ShieldCheck, Sparkles,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  associateSoftwareToken, clearSession, completeMfaSetup, getMe, loadSession, login,
  respondMfaChallenge, respondNewPasswordRequired, saveSession, verifySoftwareToken,
  type MeInfo, type Tokens,
} from '@/lib/maa';
import { ChatApp } from '@/components/maa/chat-app';
import { Logo } from '@/components/maa/logo';
import { initTheme } from '@/components/maa/theme';

type View = 'login' | 'new_password' | 'mfa_setup' | 'mfa_challenge' | 'chat';

const inputCls =
  'w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] px-3.5 py-2.5 text-[13.5px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--muted-fg)] focus:border-[var(--accent)]';
const btnCls =
  'maa-btn-primary flex w-full items-center justify-center gap-2 px-4 py-2.5 text-[13.5px] font-semibold';

const FEATURES = [
  { icon: <Boxes className="h-3.5 w-3.5" />, text: 'Orkestrasi penuh EC2 · EKS · RDS · S3 · VPC' },
  { icon: <Sparkles className="h-3.5 w-3.5" />, text: 'Multi-agent, todo list live, deck & web app' },
  { icon: <ShieldCheck className="h-3.5 w-3.5" />, text: 'Konfirmasi ganda untuk operasi destruktif' },
  { icon: <Lock className="h-3.5 w-3.5" />, text: 'Zero static credential — STS single-use' },
];

function pwScore(p: string): number {
  let s = 0;
  if (p.length >= 8) s++;
  if (p.length >= 12) s++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) s++;
  if (/\d/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  return s; // 0..5
}

export default function Home() {
  const { toast } = useToast();
  const [view, setView] = useState<View>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(true);
  const [newPw1, setNewPw1] = useState('');
  const [newPw2, setNewPw2] = useState('');
  const [showNewPw, setShowNewPw] = useState(false);
  const [authSession, setAuthSession] = useState('');
  const [secret, setSecret] = useState('');
  const [qrData, setQrData] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [me, setMe] = useState<MeInfo | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    initTheme();
    const saved = typeof window !== 'undefined' && localStorage.getItem('maa.remember.user') === '1';
    if (saved) setRemember(true);
    const s = loadSession();
    if (s) {
      setTokens(s.tokens);
      setUsername(s.username);
      setView('chat');
    } else {
      setBooting(false);
    }
  }, []);

  // Ambil profil (/me) setelah token siap → role untuk menu Admin
  useEffect(() => {
    if (!tokens) return;
    let alive = true;
    void (async () => {
      try {
        const m = await getMe(tokens.IdToken);
        if (alive) setMe({ ...m, role: m.role || 'user' });
      } catch {
        if (alive) {
          // /me belum tersedia — jangan blokir chat; anggap user biasa
          setMe({ userId: username || 'user', username: username || 'user', role: 'user' });
        }
      } finally {
        if (alive) setBooting(false);
      }
    })();
    return () => { alive = false; };
  }, [tokens]);

  const enterChat = (t: Tokens, msg?: string) => {
    saveSession(username.trim(), t, remember);
    localStorage.setItem('maa.remember.user', remember ? '1' : '0');
    setTokens(t);
    setView('chat');
    setInfo(msg || '');
    if (msg) toast({ description: msg, duration: 6000 });
  };

  const doLogin = async () => {
    setBusy(true); setError(''); setInfo('');
    try {
      const r = await login(username.trim(), password);
      if (r.kind === 'tokens') {
        enterChat(r.tokens);
      } else if (r.kind === 'new_password') {
        // User undangan login pertama kali: wajib set password baru
        setAuthSession(r.session);
        setNewPw1(''); setNewPw2('');
        setInfo('Kata sandi sementara terdeteksi. Silakan buat kata sandi baru Anda.');
        setView('new_password');
      } else if (r.kind === 'mfa_setup') {
        setAuthSession(r.session);
        const sec = await associateSoftwareToken(r.session);
        setSecret(sec);
        setQrData(await QRCode.toDataURL(
          `otpauth://totp/MAA-Agent:${encodeURIComponent(username.trim())}?secret=${sec}&issuer=MAA%20AWS%20Agent&algorithm=SHA1&digits=6&period=30`,
          { width: 220, margin: 1, color: { dark: '#111111', light: '#FFFFFF' } }
        ));
        setView('mfa_setup');
      } else {
        setAuthSession(r.session); setView('mfa_challenge');
      }
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  const doNewPassword = async () => {
    if (newPw1.length < 8) { setError('Kata sandi minimal 8 karakter.'); return; }
    if (newPw1 !== newPw2) { setError('Konfirmasi kata sandi tidak cocok.'); return; }
    setBusy(true); setError('');
    try {
      const r = await respondNewPasswordRequired(authSession, username.trim(), newPw1);
      if (r.kind === 'tokens') {
        enterChat(r.tokens, 'Kata sandi baru berhasil disimpan.');
      } else if (r.kind === 'mfa_setup') {
        setAuthSession(r.session);
        const sec = await associateSoftwareToken(r.session);
        setSecret(sec);
        setQrData(await QRCode.toDataURL(
          `otpauth://totp/MAA-Agent:${encodeURIComponent(username.trim())}?secret=${sec}&issuer=MAA%20AWS%20Agent&algorithm=SHA1&digits=6&period=30`,
          { width: 220, margin: 1, color: { dark: '#111111', light: '#FFFFFF' } }
        ));
        setView('mfa_setup');
      } else if (r.kind === 'mfa_challenge') {
        setAuthSession(r.session); setView('mfa_challenge');
      }
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  const doVerifyEnroll = async () => {
    setBusy(true); setError('');
    try {
      const ns = await verifySoftwareToken(authSession, code.trim());
      const t = await completeMfaSetup(ns, username.trim());
      enterChat(t, 'MFA TOTP berhasil didaftarkan!');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const doMfaChallenge = async () => {
    setBusy(true); setError('');
    try {
      const t = await respondMfaChallenge(authSession, username.trim(), code.trim());
      enterChat(t);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  if (view === 'chat' && tokens) {
    if (booting) {
      return (
        <main className="flex min-h-dvh flex-col items-center justify-center bg-[var(--bg)]">
          <div className="animate-pop flex flex-col items-center gap-3">
            <Logo size={44} />
            <p className="flex items-center gap-2 text-[12.5px] text-[var(--muted-fg)]">
              <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
              Memuat profil…
            </p>
          </div>
        </main>
      );
    }
    return (
      <ChatApp
        tokens={tokens}
        username={username}
        me={me}
        onLogout={(msg) => {
          clearSession();
          setTokens(null);
          setMe(null);
          setView('login');
          setCode('');
          setPassword('');
          window.history.replaceState({}, '', '/');
          setInfo(msg || '');
          if (msg) toast({ description: msg, duration: 6000 });
        }}
      />
    );
  }

  const errBox = (error || info) && (
    <div
      className={`mb-4 rounded-lg border px-3.5 py-2.5 text-[12.5px] leading-relaxed ${
        error
          ? 'border-[var(--danger)] bg-[var(--danger)]/5 text-[var(--danger)]'
          : 'border-emerald-600 bg-emerald-50 text-emerald-700 dark:border-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-400'
      }`}
    >
      {error || info}
    </div>
  );

  return (
    <main className="relative flex min-h-dvh bg-[var(--bg)] text-[var(--ink)]">
      <div aria-hidden className="maa-grid-bg pointer-events-none absolute inset-0" />

      {/* ---------- panel kiri: branding (desktop) ---------- */}
      <section className="relative z-10 hidden w-[46%] flex-col justify-between border-r border-[var(--line-soft)] bg-gradient-to-br from-[var(--surface)] via-[var(--bg)] to-[var(--accent-soft)] p-10 lg:flex">
        <div className="flex items-center gap-3">
          <span className="maa-panel flex h-11 w-11 items-center justify-center !rounded-xl">
            <Logo size={28} />
          </span>
          <div>
            <p className="text-[15px] font-bold leading-tight">MAA AWS Agent</p>
            <p className="text-[11px] text-[var(--muted-fg)]">Autonomous Enterprise Cloud Operations</p>
          </div>
        </div>

        <div className="max-w-md">
          <h2 className="text-[30px] font-extrabold leading-[1.15] tracking-tight">
            Insinyur cloud otonom yang{' '}
            <span style={{ color: 'var(--accent)' }}>bekerja untuk Anda</span> 24/7.
          </h2>
          <p className="mt-4 text-[13.5px] leading-relaxed text-[var(--muted-fg)]">
            Rancang, deploy, pantau, dan optimalkan infrastruktur AWS lewat percakapan —
            dengan Live Trace yang transparan, Knowledge Base internal, dan kontrol
            keamanan berlapis.
          </p>
          <ul className="mt-7 space-y-3">
            {FEATURES.map((f) => (
              <li key={f.text} className="flex items-center gap-2.5 text-[13px] text-[var(--ink)]">
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[var(--line-soft)] bg-[var(--bg)]"
                  style={{ color: 'var(--accent)' }}
                >
                  {f.icon}
                </span>
                {f.text}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {['Bedrock AgentCore', 'TOTP MFA', 'KMS AES-256', 'WAF Shield', 'CloudTrail Audit'].map((c) => (
            <span key={c} className="rounded-full border border-[var(--line-soft)] bg-[var(--surface)] px-2.5 py-1 text-[10px] font-medium text-[var(--muted-fg)]">
              {c}
            </span>
          ))}
        </div>
      </section>

      {/* ---------- panel kanan: form ---------- */}
      <section className="relative z-10 flex min-h-dvh w-full flex-col items-center justify-center p-4 lg:w-[54%]">
        <div className="w-full max-w-sm animate-pop">
          {/* header mobile / compact */}
          <div className="mb-6 flex flex-col items-center text-center lg:mb-7">
            <span className="maa-panel mb-4 flex h-16 w-16 items-center justify-center !rounded-2xl lg:hidden">
              <Logo size={40} />
            </span>
            <h1 className="text-[22px] font-bold tracking-tight">
              MAA <span style={{ color: 'var(--accent)' }}>AWS Agent</span>
            </h1>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--muted-fg)]">
              Masuk untuk melanjutkan ke dasbor operasi cloud Anda
            </p>
          </div>

          {view === 'login' && (
            <section aria-label="Login" className="maa-panel p-6">
              {errBox}
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void doLogin(); }}>
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Email / username</span>
                  <input className={inputCls} placeholder="Please input your username/email" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Password</span>
                  <span className="relative block">
                    <input
                      className={inputCls + ' pr-10'}
                      placeholder="••••••••••••"
                      type={showPw ? 'text' : 'password'}
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPw((v) => !v)}
                      aria-label={showPw ? 'Sembunyikan password' : 'Tampilkan password'}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
                    >
                      {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </span>
                </label>

                <div className="flex items-center justify-between pt-0.5">
                  <label className="flex cursor-pointer select-none items-center gap-2 text-[12px] text-[var(--muted-fg)]">
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(e) => setRemember(e.target.checked)}
                      className="h-3.5 w-3.5 accent-[var(--accent)]"
                    />
                    Ingat saya di perangkat ini
                  </label>
                  <span className="flex items-center gap-1 text-[11px] text-[var(--muted-fg)]">
                    <ShieldCheck className="h-3 w-3" style={{ color: 'var(--accent)' }} />
                    MFA TOTP wajib
                  </span>
                </div>

                <button className={btnCls} disabled={busy || !username || !password} type="submit">
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                  {busy ? 'Memeriksa…' : 'Masuk'}
                </button>
              </form>
              <p className="mt-4 flex items-center justify-center gap-1.5 text-center text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
                Sesi hangus otomatis 15 menit idle · "Ingat saya" hanya menyimpan sesi di perangkat Anda
              </p>
            </section>
          )}

          {view === 'new_password' && (
            <section aria-label="Buat password baru" className="maa-panel p-6">
              <div className="mb-4 flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--accent-soft)]">
                  <KeyRound className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                </span>
                <div>
                  <h2 className="text-[15px] font-bold">Buat Password Baru</h2>
                  <p className="text-[11px] text-[var(--muted-fg)]">
                    Akun Anda memakai password sementara dari undangan
                  </p>
                </div>
              </div>
              {errBox}
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void doNewPassword(); }}>
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Password baru</span>
                  <span className="relative block">
                    <input
                      className={inputCls + ' pr-10'}
                      placeholder="Minimal 8 karakter"
                      type={showNewPw ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={newPw1}
                      onChange={(e) => setNewPw1(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPw((v) => !v)}
                      aria-label={showNewPw ? 'Sembunyikan password' : 'Tampilkan password'}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
                    >
                      {showNewPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </span>
                  {/* strength meter */}
                  <span className="mt-2 flex items-center gap-1.5">
                    {[1, 2, 3, 4, 5].map((i) => (
                      <span
                        key={i}
                        className="h-1 flex-1 rounded-full transition-colors"
                        style={{
                          background:
                            i <= pwScore(newPw1)
                              ? pwScore(newPw1) >= 4
                                ? 'var(--accent)'
                                : '#F59E0B'
                              : 'var(--line-soft)',
                        }}
                      />
                    ))}
                    <span className="w-14 text-right text-[10px] text-[var(--muted-fg)]">
                      {newPw1 ? (pwScore(newPw1) >= 4 ? 'kuat' : pwScore(newPw1) >= 2 ? 'sedang' : 'lemah') : ''}
                    </span>
                  </span>
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Konfirmasi password</span>
                  <input
                    className={inputCls}
                    placeholder="Ulangi password baru"
                    type={showNewPw ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={newPw2}
                    onChange={(e) => setNewPw2(e.target.value)}
                  />
                </label>
                <button className={btnCls} disabled={busy || !newPw1 || !newPw2} type="submit">
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                  {busy ? 'Menyimpan…' : 'Simpan & Lanjut'}
                </button>
                <button type="button" className="w-full text-center text-[11px] text-[var(--muted-fg)] transition-colors hover:text-[var(--ink)]" onClick={() => { setView('login'); setError(''); }}>
                  ← kembali ke login
                </button>
              </form>
              <p className="mt-3 text-center text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
                Setelah ini Anda mungkin diminta mendaftarkan MFA TOTP
              </p>
            </section>
          )}

          {view === 'mfa_setup' && (
            <section aria-label="Pendaftaran MFA" className="maa-panel p-6">
              <div className="mb-4 flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--accent-soft)]">
                  <KeyRound className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                </span>
                <div>
                  <h2 className="text-[15px] font-bold">Wajib Daftar MFA TOTP</h2>
                  <p className="text-[11px] text-[var(--muted-fg)]">Akses dasbor terkunci sampai pendaftaran selesai</p>
                </div>
              </div>
              {error && (
                <div className="mb-3 rounded-lg border border-[var(--danger)] bg-[var(--danger)]/5 px-3.5 py-2.5 text-[12.5px] text-[var(--danger)]">{error}</div>
              )}
              <ol className="mb-4 flex items-center gap-2 text-[10.5px] text-[var(--muted-fg)]">
                <li className="flex items-center gap-1.5"><span className="flex h-5 w-5 items-center justify-center rounded-full text-[9.5px] font-bold text-[var(--accent-ink)]" style={{ background: 'var(--accent)' }}>1</span> Pindai QR</li>
                <li className="h-px flex-1 bg-[var(--line-soft)]" />
                <li className="flex items-center gap-1.5"><span className="flex h-5 w-5 items-center justify-center rounded-full border border-[var(--line)] text-[9.5px] font-bold">2</span> Masukkan kode 6 digit</li>
              </ol>
              <div className="flex flex-col items-center gap-3">
                {qrData && <img src={qrData} alt="QR pendaftaran MFA TOTP" width={190} height={190} className="rounded-[10px] border border-[var(--line)] p-1.5" />}
                <div className="w-full">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Secret key (entry manual)</p>
                  <code className="block select-all break-all rounded-lg border border-[var(--line-soft)] bg-[var(--surface)] p-2.5 text-center font-mono text-[11px] text-[var(--ink)]">{secret}</code>
                </div>
                <input className={inputCls + ' text-center font-mono text-xl tracking-[0.45em]'} placeholder="123456" inputMode="numeric"
                  maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} aria-label="Kode TOTP 6 digit" />
                <button className={btnCls} disabled={busy || code.length !== 6} onClick={() => void doVerifyEnroll()}>
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                  {busy ? 'Memverifikasi…' : 'Daftarkan & Masuk'}
                </button>
              </div>
            </section>
          )}

          {view === 'mfa_challenge' && (
            <section aria-label="Validasi MFA" className="maa-panel p-6">
              <div className="mb-4 flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--accent-soft)]">
                  <KeyRound className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                </span>
                <div>
                  <h2 className="text-[15px] font-bold">Kode Authenticator</h2>
                  <p className="text-[11px] text-[var(--muted-fg)]">Masukkan 6 digit kode TOTP (jendela 30 detik)</p>
                </div>
              </div>
              {error && (
                <div className="mb-3 rounded-lg border border-[var(--danger)] bg-[var(--danger)]/5 px-3.5 py-2.5 text-[12.5px] text-[var(--danger)]">{error}</div>
              )}
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void doMfaChallenge(); }}>
                <input className={inputCls + ' text-center font-mono text-xl tracking-[0.45em]'} placeholder="123456"
                  inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} autoFocus aria-label="Kode TOTP 6 digit" />
                <button className={btnCls} disabled={busy || code.length !== 6} type="submit">
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                  {busy ? 'Memvalidasi…' : 'Verifikasi'}
                </button>
                <button type="button" className="w-full text-center text-[11px] text-[var(--muted-fg)] transition-colors hover:text-[var(--ink)]" onClick={() => setView('login')}>
                  ← kembali ke login
                </button>
              </form>
            </section>
          )}
        </div>

        <footer className="relative z-10 mt-8 text-center text-[10px] leading-relaxed text-[var(--muted-fg)]">
          MAA AWS Agent · Zero-Trust · Bedrock AgentCore · STS 5 menit · Audit CloudTrail penuh
        </footer>
      </section>
    </main>
  );
}
