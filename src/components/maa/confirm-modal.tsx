'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, ShieldCheck, Timer, X } from 'lucide-react';
import { confirmDestructive, type PendingConfirm } from '@/lib/maa';

export function ConfirmModal({
  pending,
  sessionId,
  onDone,
  onCancel,
  token,
  notify,
}: {
  pending: PendingConfirm;
  sessionId: string;
  token: string;
  onDone: () => void;
  onCancel: () => void;
  notify: (msg: string, ok?: boolean) => void;
}) {
  const [typed1, setTyped1] = useState('');
  const [typed2, setTyped2] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [left, setLeft] = useState(300); // TTL tantangan 5 menit

  useEffect(() => {
    const iv = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(iv);
  }, []);

  const ok1 = typed1.trim() === pending.challenge;
  const ok2 = typed2.trim() === pending.challenge;
  const canExec = ok1 && ok2 && !busy && left > 0;

  const exec = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await confirmDestructive(token, sessionId, pending.confirmToken, typed1.trim(), typed2.trim());
      if (r.status === 'executed') {
        notify('Operasi destruktif berhasil dieksekusi', true);
        onDone();
      } else {
        setMsg(r.message || 'Konfirmasi gagal dieksekusi.');
      }
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const mm = String(Math.floor(left / 60)).padStart(1, '0');
  const ss = String(left % 60).padStart(2, '0');

  return (
    <div
      className="animate-fade fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Konfirmasi operasi destruktif"
    >
      <div className="animate-pop maa-panel w-full max-w-lg overflow-hidden !rounded-[10px] border-[var(--danger)]">
        <div className="flex items-center gap-3 border-b border-[var(--danger)] bg-[var(--danger)]/5 px-5 py-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border border-[var(--danger)]/40 bg-[var(--danger)]/10">
            <AlertTriangle className="h-5 w-5 text-[var(--danger)]" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-[15px] font-bold tracking-tight text-[var(--ink)]">Operasi Destruktif</h3>
            <p className="text-[11.5px] text-[var(--muted-fg)]">
              Butuh konfirmasi ganda — ketik tantangan yang sama di dua kolom.
            </p>
          </div>
          <span
            className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2 py-1 font-mono text-[11px] ${
              left > 60
                ? 'border-[var(--line-soft)] text-[var(--muted-fg)]'
                : 'border-[var(--danger)] text-[var(--danger)]'
            }`}
          >
            <Timer className="h-3.5 w-3.5" />
            {mm}:{ss}
          </span>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Tutup"
            className="rounded-md p-1.5 text-[var(--muted-fg)] hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-3">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">Operasi</p>
            <p className="font-mono text-[13px] font-semibold text-[var(--ink)]">
              {pending.operation?.tool || 'tool'}
            </p>
            <pre className="nice-scroll mt-2 max-h-32 overflow-auto rounded-lg border border-[var(--line-soft)] bg-[#0b0b0c] p-2.5 font-mono text-[11px] leading-relaxed text-emerald-100/90">
              {JSON.stringify(pending.operation?.input || {}, null, 2)}
            </pre>
          </div>

          <div>
            <p className="mb-2 text-[12.5px] leading-relaxed text-[var(--muted-fg)]">
              Ketik ulang tantangan berikut di{' '}
              <span className="font-semibold text-[var(--ink)]">kedua</span> kolom:
            </p>
            <code className="my-2 block select-all rounded-lg border border-[var(--danger)] bg-[var(--danger)]/5 px-3 py-2 text-center font-mono text-[16px] font-bold tracking-wide text-[var(--ink)]">
              {pending.challenge}
            </code>
            <div className="mt-2.5 space-y-2">
              <div className="relative">
                <input
                  value={typed1}
                  onChange={(e) => setTyped1(e.target.value)}
                  placeholder="Baris 1: ketik ulang tantangan"
                  aria-label="Konfirmasi pertama"
                  className={`w-full rounded-lg border bg-[var(--bg)] px-3.5 py-2.5 font-mono text-[13px] text-[var(--ink)] outline-none transition-colors placeholder:font-sans placeholder:text-[var(--muted-fg)] ${
                    typed1 === '' ? 'border-[var(--line-soft)] focus:border-[var(--accent)]' : ok1 ? 'border-emerald-600' : 'border-[var(--danger)]'
                  }`}
                />
                {typed1 !== '' && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-semibold">
                    {ok1 ? <span className="text-emerald-600 dark:text-emerald-400">cocok</span> : <span className="text-[var(--danger)]">belum sama</span>}
                  </span>
                )}
              </div>
              <div className="relative">
                <input
                  value={typed2}
                  onChange={(e) => setTyped2(e.target.value)}
                  placeholder="Baris 2: ulangi lagi (verifikasi kedua)"
                  aria-label="Konfirmasi kedua"
                  className={`w-full rounded-lg border bg-[var(--bg)] px-3.5 py-2.5 font-mono text-[13px] text-[var(--ink)] outline-none transition-colors placeholder:font-sans placeholder:text-[var(--muted-fg)] ${
                    typed2 === '' ? 'border-[var(--line-soft)] focus:border-[var(--accent)]' : ok2 ? 'border-emerald-600' : 'border-[var(--danger)]'
                  }`}
                />
                {typed2 !== '' && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-semibold">
                    {ok2 ? <span className="text-emerald-600 dark:text-emerald-400">cocok</span> : <span className="text-[var(--danger)]">belum sama</span>}
                  </span>
                )}
              </div>
            </div>
          </div>

          {msg && (
            <p className="rounded-lg border border-[var(--danger)] bg-[var(--danger)]/5 px-3 py-2 text-[12px] text-[var(--danger)]">
              {msg}
            </p>
          )}
          {left === 0 && (
            <p className="rounded-lg border border-amber-500 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700 dark:text-amber-400">
              Tantangan kedaluwarsa. Kirim ulang perintah untuk memulai konfirmasi baru.
            </p>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onCancel}
              className="maa-btn-secondary flex-1 px-4 py-2.5 text-[13px]"
            >
              Batalkan
            </button>
            <button
              type="button"
              onClick={exec}
              disabled={!canExec}
              className="maa-btn-primary flex flex-[1.4] items-center justify-center gap-2 border border-[var(--danger)] bg-[var(--danger)] px-4 py-2.5 text-[13px] font-bold"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              {busy ? 'Mengeksekusi…' : 'Eksekusi Operasi'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
