'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CloudUpload, Database, FileText, Loader2, Lock, LogIn, Mail, RefreshCw,
  ShieldCheck, Trash2, UserPlus, Users,
} from 'lucide-react';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Switch } from '@/components/ui/switch';
import {
  adminDeleteUser, adminInviteUser, adminListUsers, adminSetUserStatus,
  deleteKbDoc, fmtBytes, listKbDocs, presignUpload, relTime, syncKb,
} from '@/lib/maa';
import type { AdminUser } from '@/lib/maa';
import { DocsContent } from './docs-content';

/* ------------------------- dialog konfirmasi hapus ------------------------- */

function ConfirmAction({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  busy,
}: {
  trigger: React.ReactNode;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <span onClick={() => setOpen(true)}>{trigger}</span>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="text-[15px] text-[var(--ink)]">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-[13px] text-[var(--muted-fg)]">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="rounded-lg border-[var(--line)]">Batal</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            onClick={(e) => {
              e.preventDefault();
              setOpen(false);
              onConfirm();
            }}
            className="maa-btn-primary rounded-lg border border-[var(--danger)] bg-[var(--danger)]"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/* ------------------------------ KB drawer ------------------------------ */

type KbDoc = { key: string; name: string; size: number; updated?: string };

export function KbDrawer({
  open, onOpenChange, token, notify,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  token: string;
  notify: (msg: string, ok?: boolean) => void;
}) {
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [delTarget, setDelTarget] = useState<KbDoc | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await listKbDocs(token);
      setDocs(r.docs || []);
    } catch (e) {
      notify(`Gagal memuat dokumen: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [token, notify]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const upload = async (file: File) => {
    const okExt = /\.(pdf|xlsx|xls|png|jpe?g|csv|json|md|txt)$/i.test(file.name);
    if (!okExt) {
      notify('Format harus PDF/XLSX/PNG/JPG/CSV/JSON/MD/TXT');
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      notify('Ukuran maksimal 20 MB');
      return;
    }
    setBusy('Mengunggah…');
    try {
      const { uploadUrl } = await presignUpload(token, file.name, file.type || 'application/octet-stream');
      const res = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
      });
      if (!res.ok) throw new Error(`S3 upload ${res.status}`);
      setBusy('Menyinkronkan indeks…');
      await syncKb(token);
      notify(`"${file.name}" terunggah — KB sedang mengindeks (1–2 menit)`, true);
      await refresh();
    } catch (e) {
      notify(`Upload gagal: ${(e as Error).message}`);
    } finally {
      setBusy('');
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const doSync = async () => {
    setBusy('Sinkronisasi…');
    try {
      const r = await syncKb(token);
      notify(`Sinkronisasi dimulai (job ${r.jobId || '-'} status ${r.status || '-'})`, true);
    } catch (e) {
      notify(`Sync gagal: ${(e as Error).message}`);
    } finally {
      setBusy('');
    }
  };

  const doDelete = async (d: KbDoc) => {
    try {
      await deleteKbDoc(token, d.key);
      notify(`"${d.name}" dihapus. Jalankan sinkronisasi untuk memperbarui indeks.`, true);
      await refresh();
    } catch (e) {
      notify(`Hapus gagal: ${(e as Error).message}`);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-md gap-0 p-0">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <Database className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Knowledge Base
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Dokumen RAG yang dipakai agent menjawab berdasarkan konten Anda.
          </SheetDescription>
        </SheetHeader>

        <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
          {/* area unggah drag&drop */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files?.[0];
              if (f && !busy) upload(f);
            }}
            className={`mb-4 rounded-[10px] border-2 border-dashed p-5 text-center transition-colors ${
              dragOver ? 'border-[var(--accent)] bg-[var(--accent-soft)]' : 'border-[var(--line-soft)] bg-[var(--surface)]'
            }`}
          >
            <CloudUpload className="mx-auto mb-2 h-6 w-6 text-[var(--muted-fg)]" />
            <p className="text-[12.5px] text-[var(--ink)]">
              {busy ? busy : 'Tarik & lepas file di sini,'}
            </p>
            <p className="mb-3 text-[11px] text-[var(--muted-fg)]">
              atau pilih manual · PDF/XLSX/PNG/CSV/JSON/MD/TXT · maks 20 MB
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.xlsx,.xls,.png,.jpg,.jpeg,.csv,.json,.md,.txt"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f && !busy) upload(f);
              }}
            />
            <button
              type="button"
              disabled={!!busy}
              onClick={() => fileRef.current?.click()}
              className="maa-btn-secondary px-3.5 py-1.5 text-[12px] disabled:opacity-50"
            >
              Pilih file
            </button>
          </div>

          <div className="mb-4 flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
              Dokumen ({docs.length})
            </p>
            <button
              type="button"
              disabled={!!busy || loading}
              onClick={doSync}
              className="maa-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[11.5px] font-medium disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${busy.includes('Sinkron') ? 'animate-spin' : ''}`} />
              Sync KB sekarang
            </button>
          </div>

          {loading ? (
            <div className="space-y-2">
              <div className="skeleton-line h-12 rounded-[10px]" />
              <div className="skeleton-line h-12 rounded-[10px]" />
              <div className="skeleton-line h-12 rounded-[10px]" />
            </div>
          ) : docs.length === 0 ? (
            <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 text-center">
              <FileText className="mx-auto mb-2 h-6 w-6 text-[var(--muted-fg)]" />
              <p className="text-[12.5px] font-medium text-[var(--ink)]">Belum ada dokumen</p>
              <p className="text-[11px] text-[var(--muted-fg)]">
                Unggah runbook/SOP agar agent bisa menjawab berdasar dokumen internal.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {docs.map((d) => (
                <li key={d.key} className="flex items-center gap-3 rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2.5">
                  <FileText className="h-4 w-4 shrink-0 text-[var(--muted-fg)]" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12.5px] font-medium text-[var(--ink)]">{d.name || d.key}</p>
                    <p className="font-mono text-[10px] text-[var(--muted-fg)]">
                      {fmtBytes(d.size)}
                      {d.updated ? ` · ${relTime(d.updated)}` : ''}
                    </p>
                  </div>
                  <ConfirmAction
                    title="Hapus dokumen?"
                    description={`"${d.name || d.key}" akan dihapus dari Knowledge Base. Jalankan sync setelahnya.`}
                    confirmLabel="Hapus"
                    onConfirm={() => doDelete(d)}
                    trigger={
                      <button
                        type="button"
                        aria-label={`Hapus ${d.name || d.key}`}
                        className="rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--danger)]/10 hover:text-[var(--danger)]"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    }
                  />
                </li>
              ))}
            </ul>
          )}

          <p className="mt-4 rounded-[10px] border border-[var(--line-soft)] bg-[var(--accent-soft)] px-3 py-2.5 text-[11.5px] leading-relaxed text-[var(--ink)]">
            💡 Agent juga bisa memperbarui KB sendiri — cukup minta di chat, mis. “ringkas dokumen X dan tambahkan ke KB”.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ----------------------------- Docs drawer ----------------------------- */

export function DocsDrawer({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-3xl gap-0 p-0 sm:max-w-3xl">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <FileText className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Dokumentasi
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Semua yang perlu Anda tahu tentang MAA AWS Agent.
          </SheetDescription>
        </SheetHeader>
        <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
          <DocsContent />
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ----------------------------- Admin drawer ----------------------------- */

const STATUS_BADGE: Record<string, string> = {
  CONFIRMED: 'border-emerald-600/40 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  FORCE_CHANGE_PASSWORD: 'border-amber-600/40 bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  UNCONFIRMED: 'border-[var(--line-soft)] bg-[var(--muted-bg)] text-[var(--muted-fg)]',
};
const STATUS_LABEL: Record<string, string> = {
  CONFIRMED: 'aktif',
  FORCE_CHANGE_PASSWORD: 'password baru',
  UNCONFIRMED: 'belum konfirmasi',
};

export function AdminDrawer({
  open, onOpenChange, token, notify,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  token: string;
  notify: (msg: string, ok?: boolean) => void;
}) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyUser, setBusyUser] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'user' | 'superadmin'>('user');
  const [inviting, setInviting] = useState(false);
  const [delUser, setDelUser] = useState<AdminUser | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminListUsers(token);
      setUsers(r.users || []);
    } catch (e) {
      notify(`Gagal memuat user: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [token, notify]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const invite = async () => {
    const em = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) {
      notify('Masukkan email yang valid');
      return;
    }
    setInviting(true);
    try {
      const r = await adminInviteUser(token, em, role);
      notify(`Email undangan terkirim ke ${em} dari no-reply@verificationemail.com (user ${r.username || em})`, true);
      setEmail('');
      await refresh();
    } catch (e) {
      notify(`Undangan gagal: ${(e as Error).message}`);
    } finally {
      setInviting(false);
    }
  };

  const toggleEnabled = async (u: AdminUser, enabled: boolean) => {
    setBusyUser(u.username);
    try {
      await adminSetUserStatus(token, u.username, enabled);
      setUsers((prev) => prev.map((x) => (x.username === u.username ? { ...x, enabled } : x)));
      notify(`${u.username} ${enabled ? 'diaktifkan' : 'dinonaktifkan'}`, true);
    } catch (e) {
      notify(`Gagal mengubah status: ${(e as Error).message}`);
    } finally {
      setBusyUser('');
    }
  };

  const doDelete = async (u: AdminUser) => {
    setBusyUser(u.username);
    try {
      await adminDeleteUser(token, u.username);
      setUsers((prev) => prev.filter((x) => x.username !== u.username));
      notify(`User ${u.username} dihapus`, true);
    } catch (e) {
      notify(`Hapus gagal: ${(e as Error).message}`);
    } finally {
      setBusyUser('');
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-lg gap-0 p-0">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <Users className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Manajemen User
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Khusus superadmin — undang & kelola akses ke MAA AWS Agent.
          </SheetDescription>
        </SheetHeader>

        <div className="nice-scroll min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {/* form undang */}
          <section className="maa-panel p-4">
            <h4 className="mb-1 flex items-center gap-1.5 text-[13px] font-bold text-[var(--ink)]">
              <UserPlus className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} /> Undang user baru
            </h4>
            <p className="mb-3 text-[11.5px] text-[var(--muted-fg)]">
              Cognito mengirim email berisi password sementara dari <span className="font-mono">no-reply@verificationemail.com</span>.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <Mail className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-fg)]" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && invite()}
                  placeholder="nama@perusahaan.com"
                  className="h-9 w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] pl-8 pr-3 text-[13px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                  aria-label="Email user baru"
                />
              </div>
              <div className="flex overflow-hidden rounded-lg border border-[var(--line)]">
                {(['user', 'superadmin'] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setRole(r)}
                    className={`flex items-center gap-1 px-3 text-[11.5px] font-semibold transition-colors ${
                      role === r ? 'bg-[var(--accent)] text-[var(--accent-ink)]' : 'bg-[var(--bg)] text-[var(--muted-fg)] hover:bg-[var(--surface)]'
                    }`}
                  >
                    {r === 'superadmin' ? <ShieldCheck className="h-3 w-3" /> : <LogIn className="h-3 w-3" />}
                    {r}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={invite}
                disabled={inviting || !email.trim()}
                className="maa-btn-primary flex h-9 items-center gap-1.5 px-4 text-[12.5px]"
              >
                {inviting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
                Undang
              </button>
            </div>
          </section>

          {/* tabel user */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
                User terdaftar ({users.length})
              </p>
              <button
                type="button"
                onClick={refresh}
                disabled={loading}
                className="maa-btn-ghost flex items-center gap-1 px-2 py-1 text-[11px]"
              >
                <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
              </button>
            </div>

            {loading ? (
              <div className="space-y-2">
                <div className="skeleton-line h-14 rounded-[10px]" />
                <div className="skeleton-line h-14 rounded-[10px]" />
              </div>
            ) : users.length === 0 ? (
              <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 text-center">
                <Users className="mx-auto mb-2 h-6 w-6 text-[var(--muted-fg)]" />
                <p className="text-[12.5px] font-medium text-[var(--ink)]">Belum ada user terdaftar</p>
                <p className="text-[11px] text-[var(--muted-fg)]">Undang user pertama lewat form di atas.</p>
              </div>
            ) : (
              <ul className="space-y-2">
                {users.map((u) => (
                  <li key={u.username} className="flex items-center gap-3 rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] font-medium text-[var(--ink)]">
                        <span className="truncate">{u.username}</span>
                        {u.role === 'superadmin' && (
                          <span className="inline-flex items-center gap-0.5 rounded-full border border-[var(--accent)] px-1.5 text-[9px] font-bold uppercase" style={{ color: 'var(--accent)' }}>
                            <ShieldCheck className="h-2.5 w-2.5" /> superadmin
                          </span>
                        )}
                      </p>
                      <p className="truncate text-[11px] text-[var(--muted-fg)]">
                        {u.email || '—'}
                        {u.created ? ` · dibuat ${relTime(u.created)}` : ''}
                      </p>
                      {u.status && (
                        <span className={`mt-1 inline-block rounded-full border px-1.5 py-px text-[9.5px] font-semibold ${STATUS_BADGE[u.status] || STATUS_BADGE.UNCONFIRMED}`}>
                          {STATUS_LABEL[u.status] || u.status}
                        </span>
                      )}
                    </div>
                    <label className="flex shrink-0 items-center gap-1.5" title={u.enabled ? 'Aktif' : 'Nonaktif'}>
                      <Switch
                        checked={!!u.enabled}
                        disabled={busyUser === u.username}
                        onCheckedChange={(v) => toggleEnabled(u, v)}
                        aria-label={`Aktifkan/nonaktifkan ${u.username}`}
                      />
                    </label>
                    <ConfirmAction
                      title="Hapus user?"
                      description={`User "${u.username}" akan dihapus permanen dari Cognito dan kehilangan akses.`}
                      confirmLabel="Hapus"
                      onConfirm={() => doDelete(u)}
                      trigger={
                        <button
                          type="button"
                          aria-label={`Hapus ${u.username}`}
                          className="rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--danger)]/10 hover:text-[var(--danger)]"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p className="flex items-start gap-2 rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2.5 text-[11.5px] leading-relaxed text-[var(--muted-fg)]">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Semua aksi admin tervalog. User nonaktif tetap tersimpan tapi tidak bisa login; hapus bersifat permanen.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
