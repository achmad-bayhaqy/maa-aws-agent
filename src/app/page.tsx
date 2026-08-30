'use client';

import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { KeyRound, Loader2, ShieldCheck } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  associateSoftwareToken, clearSession, completeMfaSetup, getMe, loadSession,
  login, respondMfaChallenge, saveSession, verifySoftwareToken,
  type MeInfo, type Tokens,
} from '@/lib/maa';
import { ChatApp } from '@/components/maa/chat-app';
import { Logo } from '@/components/maa/logo';
import { initTheme } from '@/components/maa/theme';

type View = 'login' | 'mfa_setup' | 'mfa_challenge' | 'chat';

const inputCls =
  'w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] px-3.5 py-2.5 text-[13.5px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--muted-fg)] focus:border-[var(--accent)]';
const btnCls =
  'maa-btn-primary flex w-full items-center justify-center gap-2 px-4 py-2.5 text-[13.5px] font-semibold';

export default function Home() {
  const { toast } = useToast();
  const [view, setView] = useState<View>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
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

  const doLogin = async () => {
    setBusy(true); setError(''); setInfo('');
    try {
      const r = await login(username.trim(), password);
      if (r.kind === 'tokens') {
        saveSession(username.trim(), r.tokens);
        setTokens(r.tokens); setView('chat');
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

  const doVerifyEnroll = async () => {
    setBusy(true); setError('');
    try {
      const ns = await verifySoftwareToken(authSession, code.trim());
      const t = await completeMfaSetup(ns, username.trim());
      saveSession(username.trim(), t);
      setTokens(t); setInfo('MFA TOTP berhasil didaftarkan!'); setView('chat');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const doMfaChallenge = async () => {
    setBusy(true); setError('');
    try {
      const t = await respondMfaChallenge(authSession, username.trim(), code.trim());
      saveSession(username.trim(), t);
      setTokens(t); setView('chat');
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

  return (
    <main className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-[var(--bg)] p-4 text-[var(--ink)]">
      {/* ilustrasi tipis: grid garis merah */}
      <div aria-hidden className="maa-grid-bg pointer-events-none absolute inset-0" />

      <div className="relative z-10 w-full max-w-sm animate-pop">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="maa-panel mb-4 flex h-16 w-16 items-center justify-center !rounded-2xl">
            <Logo size={40} />
          </span>
          <h1 className="text-[22px] font-bold tracking-tight">
            MAA <span style={{ color: 'var(--accent)' }}>AWS Agent</span>
          </h1>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--muted-fg)]">
            Insinyur cloud otonom — aman, teraudit, tanpa kredensial statis
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5">
            {['TOTP MFA', 'AgentCore Runtime', 'KMS AES-256', 'WAF Shield'].map((c) => (
              <span key={c} className="rounded-full border border-[var(--line-soft)] bg-[var(--surface)] px-2.5 py-1 text-[10px] font-medium text-[var(--muted-fg)]">
                {c}
              </span>
            ))}
          </div>
        </div>

        {view === 'login' && (
          <section aria-label="Login" className="maa-panel p-6">
            {(error || info) && (
              <div
                className={`mb-4 rounded-lg border px-3.5 py-2.5 text-[12.5px] leading-relaxed ${
                  error
                    ? 'border-[var(--danger)] bg-[var(--danger)]/5 text-[var(--danger)]'
                    : 'border-emerald-600 bg-emerald-50 text-emerald-700 dark:border-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-400'
                }`}
              >
                {error || info}
              </div>
            )}
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void doLogin(); }}>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Email / username</span>
                <input className={inputCls} placeholder="architect atau nama@perusahaan.com" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Password</span>
                <input className={inputCls} placeholder="••••••••••••" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </label>
              <button className={btnCls} disabled={busy || !username || !password} type="submit">
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                {busy ? 'Memeriksa…' : 'Masuk'}
              </button>
            </form>
            <p className="mt-4 flex items-center justify-center gap-1.5 text-center text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
              Login wajib MFA TOTP · sesi hangus 15 menit idle
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
    </main>
  );
}
