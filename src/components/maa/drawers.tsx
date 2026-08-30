'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AtSign, Check, ChevronDown, ClipboardCopy, CloudUpload, Database, Edit3, Eye,
  FileText, KeyRound, Loader2, Lock, LogIn, Mail, RefreshCw, Save, Search,
  ShieldCheck, Trash2, UserPlus, Users, X,
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
  adminDeleteUser, adminInviteUser, adminListUsers, adminResendInvite,
  adminSetPassword, adminSetUserStatus, deleteKbDoc, fmtBytes, getDocContent,
  listKbDocs, listSiteDocs, presignUpload, relTime, saveDocContent, syncKb,
} from '@/lib/maa';
import type { AdminUser } from '@/lib/maa';
import { DocsContent } from './docs-content';
import { Markdown } from './markdown';

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

type SiteDoc = { key: string; name: string; size: number; updated?: string };

export function DocsDrawer({
  open, onOpenChange, token, isSuperadmin, notify,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  token: string;
  isSuperadmin: boolean;
  notify?: (msg: string, ok?: boolean) => void;
}) {
  const [docs, setDocs] = useState<SiteDoc[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [content, setContent] = useState<string>('');
  const [draft, setDraft] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [err, setErr] = useState('');

  const refreshList = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const r = await listSiteDocs(token);
      setDocs(r.docs || []);
      if (r.docs?.length && !activeKey) setActiveKey(r.docs[0].key);
    } catch {
      setDocs([]); // fallback konten statis
    } finally {
      setLoading(false);
    }
  }, [token, activeKey]);

  useEffect(() => {
    if (open) {
      setEditing(false);
      void refreshList();
    }
  }, [open, refreshList]);

  useEffect(() => {
    if (!activeKey || !token) return;
    setLoading(true);
    setErr('');
    void (async () => {
      try {
        const r = await getDocContent(token, activeKey);
        setContent(r.content || '');
        setDraft(r.content || '');
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [activeKey, token]);

  const save = async () => {
    if (!activeKey) return;
    setSaving(true);
    try {
      await saveDocContent(token, activeKey, draft);
      setContent(draft);
      setEditing(false);
      notify?.('Dokumentasi tersimpan.', true);
      void refreshList();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-4xl gap-0 p-0 sm:max-w-4xl">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <FileText className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Dokumentasi
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Markdown{isSuperadmin ? ' · Anda bisa mengedit (superadmin)' : ' · hanya superadmin yang bisa mengedit'}
          </SheetDescription>
        </SheetHeader>

        {!token || docs.length === 0 ? (
          /* fallback: konten statis bawaan */
          <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
            <DocsContent />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1">
            {/* daftar dokumen */}
            <nav className="w-48 shrink-0 overflow-y-auto border-r border-[var(--line-soft)] p-3">
              {docs.map((d) => (
                <button
                  key={d.key}
                  type="button"
                  onClick={() => { setActiveKey(d.key); setEditing(false); }}
                  className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] transition-colors ${
                    activeKey === d.key
                      ? 'bg-[var(--accent-soft)] font-semibold text-[var(--ink)]'
                      : 'text-[var(--muted-fg)] hover:bg-[var(--surface)] hover:text-[var(--ink)]'
                  }`}
                >
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{d.name.replace(/\.md$/, '')}</span>
                </button>
              ))}
            </nav>

            {/* konten / editor */}
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <div className="flex items-center justify-between gap-2 border-b border-[var(--line-soft)] px-4 py-2.5">
                <p className="truncate text-[11.5px] text-[var(--muted-fg)]">
                  {activeKey?.split('/').pop()} · {editing ? 'mode edit (markdown)' : 'mode baca'}
                </p>
                <div className="flex items-center gap-1.5">
                  {isSuperadmin && !editing && (
                    <button
                      type="button"
                      onClick={() => { setDraft(content); setEditing(true); }}
                      className="maa-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[11.5px] font-medium"
                    >
                      <Edit3 className="h-3.5 w-3.5" /> Edit
                    </button>
                  )}
                  {isSuperadmin && editing && (
                    <>
                      <button
                        type="button"
                        onClick={() => setShowPreview((v) => !v)}
                        className="maa-btn-ghost flex items-center gap-1 px-2 py-1.5 text-[11px]"
                        title="Toggle preview"
                      >
                        {showPreview ? <Eye className="h-3.5 w-3.5" /> : <Edit3 className="h-3.5 w-3.5" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditing(false)}
                        className="maa-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[11.5px]"
                      >
                        <X className="h-3.5 w-3.5" /> Batal
                      </button>
                      <button
                        type="button"
                        onClick={() => void save()}
                        disabled={saving || draft === content}
                        className="maa-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11.5px] disabled:opacity-50"
                      >
                        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                        Simpan
                      </button>
                    </>
                  )}
                </div>
              </div>

              {err && (
                <p className="border-b border-[var(--danger)]/20 bg-[var(--danger)]/5 px-4 py-2 text-[11.5px] text-[var(--danger)]">{err}</p>
              )}

              {loading ? (
                <div className="space-y-2 p-5">
                  <div className="skeleton-line h-4 w-2/3 rounded" />
                  <div className="skeleton-line h-4 w-full rounded" />
                  <div className="skeleton-line h-4 w-5/6 rounded" />
                </div>
              ) : editing ? (
                <div className="flex min-h-0 flex-1">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    spellCheck={false}
                    className={`nice-scroll min-h-0 flex-1 resize-none bg-[var(--bg)] p-4 font-mono text-[12.5px] leading-relaxed text-[var(--ink)] outline-none ${
                      showPreview ? 'border-r border-[var(--line-soft)]' : ''
                    }`}
                    aria-label="Editor markdown"
                  />
                  {showPreview && (
                    <div className="nice-scroll min-h-0 w-1/2 overflow-y-auto p-4">
                      <Markdown text={draft || '_kosong_'} />
                    </div>
                  )}
                </div>
              ) : (
                <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
                  <Markdown text={content} />
                </div>
              )}
            </div>
          </div>
        )}
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

function genPassword(): string {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  const num = '23456789';
  const sym = '!@#$%&*';
  const pick = (s: string, n: number) =>
    Array.from(crypto.getRandomValues(new Uint32Array(n)), (v) => s[v % s.length]).join('');
  return pick(abc, 4) + pick(num, 3) + pick(sym, 2) + pick(abc + num, 5);
}

type InviteStep = 'form' | 'done';

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
  const [query, setQuery] = useState('');
  const [delUser, setDelUser] = useState<AdminUser | null>(null);

  // ---- undang (wizard 2 langkah) ----
  const [inviteOpen, setInviteOpen] = useState(false);
  const [invEmail, setInvEmail] = useState('');
  const [invRole, setInvRole] = useState<'user' | 'superadmin'>('user');
  const [invMode, setInvMode] = useState<'email' | 'instant'>('email');
  const [invBusy, setInvBusy] = useState(false);
  const [invStep, setInvStep] = useState<InviteStep>('form');
  const [invResult, setInvResult] = useState<{ username: string; email: string; password?: string } | null>(null);
  const [copied, setCopied] = useState('');

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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) => u.username.toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q)
    );
  }, [users, query]);

  const stats = useMemo(
    () => ({
      total: users.length,
      active: users.filter((u) => u.enabled && u.status === 'CONFIRMED').length,
      admins: users.filter((u) => u.role === 'superadmin').length,
      pending: users.filter((u) => u.status === 'FORCE_CHANGE_PASSWORD' || u.status === 'UNCONFIRMED').length,
    }),
    [users]
  );

  const copy = (text: string, label: string) => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(label);
      setTimeout(() => setCopied(''), 1600);
    });
  };

  const submitInvite = async () => {
    const em = invEmail.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) {
      notify('Masukkan email yang valid');
      return;
    }
    setInvBusy(true);
    try {
      if (invMode === 'email') {
        const r = await adminInviteUser(token, em, invRole);
        setInvResult({ username: r.username || em, email: em });
        notify(`Email undangan terkirim ke ${em} (user ${r.username || em})`, true);
      } else {
        // buat user via email dulu, lalu set password instan yang kuat
        const created = await adminInviteUser(token, em, invRole);
        const username = created.username || em;
        const pw = genPassword();
        await adminSetPassword(token, username, pw);
        setInvResult({ username, email: em, password: pw });
        notify('User dibuat dengan password instan — bagikan via kanal aman.', true);
      }
      setInvStep('done');
      await refresh();
    } catch (e) {
      notify(`Undangan gagal: ${(e as Error).message}`);
    } finally {
      setInvBusy(false);
    }
  };

  const closeInvite = () => {
    setInviteOpen(false);
    setInvStep('form');
    setInvResult(null);
    setInvEmail('');
    setCopied('');
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

  const doResend = async (u: AdminUser) => {
    setBusyUser(u.username);
    try {
      await adminResendInvite(token, u.username);
      notify(`Undangan dikirim ulang ke ${u.email || u.username}`, true);
    } catch (e) {
      notify(`Resend gagal: ${(e as Error).message}`);
    } finally {
      setBusyUser('');
    }
  };

  const doInstantPassword = async (u: AdminUser) => {
    setBusyUser(u.username);
    try {
      const pw = genPassword();
      await adminSetPassword(token, u.username, pw);
      setInvResult({ username: u.username, email: u.email || '', password: pw });
      setInviteOpen(true);
      setInvStep('done');
    } catch (e) {
      notify(`Set password gagal: ${(e as Error).message}`);
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

  const statCards = [
    { label: 'Total', value: stats.total, icon: <Users className="h-3.5 w-3.5" /> },
    { label: 'Aktif', value: stats.active, icon: <Check className="h-3.5 w-3.5" /> },
    { label: 'Superadmin', value: stats.admins, icon: <ShieldCheck className="h-3.5 w-3.5" /> },
    { label: 'Pending', value: stats.pending, icon: <AtSign className="h-3.5 w-3.5" /> },
  ];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-xl gap-0 p-0 sm:max-w-xl">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <Users className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Manajemen User
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Khusus superadmin — undang, audit, dan kelola akses MAA AWS Agent.
          </SheetDescription>
        </SheetHeader>

        <div className="nice-scroll min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {/* kartu statistik */}
          <section className="grid grid-cols-4 gap-2">
            {statCards.map((c) => (
              <div key={c.label} className="maa-panel flex flex-col items-center gap-0.5 p-3 text-center">
                <span className="mb-0.5" style={{ color: 'var(--accent)' }}>{c.icon}</span>
                <span className="text-[18px] font-extrabold leading-none text-[var(--ink)]">{c.value}</span>
                <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--muted-fg)]">{c.label}</span>
              </div>
            ))}
          </section>

          {/* aksi utama */}
          <section className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => { setInviteOpen(true); setInvStep('form'); }}
              className="maa-btn-primary flex flex-1 items-center justify-center gap-1.5 px-4 py-2.5 text-[12.5px]"
            >
              <UserPlus className="h-4 w-4" /> Undang User Baru
            </button>
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-fg)]" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Cari username / email…"
                className="h-[42px] w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] pl-8 pr-3 text-[13px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                aria-label="Cari user"
              />
            </div>
          </section>

          {/* tabel user */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
                User ({filtered.length}{query && ` / ${users.length}`})
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
            ) : filtered.length === 0 ? (
              <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 text-center">
                <Users className="mx-auto mb-2 h-6 w-6 text-[var(--muted-fg)]" />
                <p className="text-[12.5px] font-medium text-[var(--ink)]">
                  {query ? 'Tidak ada hasil' : 'Belum ada user terdaftar'}
                </p>
                <p className="text-[11px] text-[var(--muted-fg)]">
                  {query ? 'Coba kata kunci lain.' : 'Undang user pertama lewat tombol di atas.'}
                </p>
              </div>
            ) : (
              <ul className="space-y-2">
                {filtered.map((u) => (
                  <li key={u.username} className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2.5">
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] font-medium text-[var(--ink)]">
                          <span className="truncate">{u.username}</span>
                          {u.role === 'superadmin' && (
                            <span className="inline-flex items-center gap-0.5 rounded-full border border-[var(--accent)] px-1.5 text-[9px] font-bold uppercase" style={{ color: 'var(--accent)' }}>
                              <ShieldCheck className="h-2.5 w-2.5" /> superadmin
                            </span>
                          )}
                          {u.status && (
                            <span className={`inline-block rounded-full border px-1.5 py-px text-[9.5px] font-semibold ${STATUS_BADGE[u.status] || STATUS_BADGE.UNCONFIRMED}`}>
                              {STATUS_LABEL[u.status] || u.status}
                            </span>
                          )}
                        </p>
                        <p className="truncate text-[11px] text-[var(--muted-fg)]">
                          {u.email || '—'}
                          {u.created ? ` · dibuat ${relTime(u.created)}` : ''}
                        </p>
                      </div>
                      <label className="flex shrink-0 items-center gap-1.5" title={u.enabled ? 'Aktif' : 'Nonaktif'}>
                        <Switch
                          checked={!!u.enabled}
                          disabled={busyUser === u.username}
                          onCheckedChange={(v) => toggleEnabled(u, v)}
                          aria-label={`Aktifkan/nonaktifkan ${u.username}`}
                        />
                      </label>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-[var(--line-soft)] pt-2">
                      <button
                        type="button"
                        disabled={busyUser === u.username}
                        onClick={() => void doResend(u)}
                        className="maa-btn-ghost flex items-center gap-1 px-2 py-1 text-[10.5px] font-medium disabled:opacity-50"
                        title="Kirim ulang email undangan Cognito (password sementara baru)"
                      >
                        <Mail className="h-3 w-3" /> Resend undangan
                      </button>
                      <button
                        type="button"
                        disabled={busyUser === u.username}
                        onClick={() => void doInstantPassword(u)}
                        className="maa-btn-ghost flex items-center gap-1 px-2 py-1 text-[10.5px] font-medium disabled:opacity-50"
                        title="Set password permanen baru (tampil sekali untuk dibagikan)"
                      >
                        <KeyRound className="h-3 w-3" /> Password instan
                      </button>
                      <span className="flex-1" />
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
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p className="flex items-start gap-2 rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2.5 text-[11.5px] leading-relaxed text-[var(--muted-fg)]">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Semua aksi admin tervalog di CloudTrail. User nonaktif tetap tersimpan tapi tidak bisa login; hapus bersifat permanen.
          </p>
        </div>

        {/* ---------- modal undang 2 langkah ---------- */}
        <AlertDialog open={inviteOpen} onOpenChange={(v) => { if (!v) closeInvite(); }}>
          <AlertDialogContent className="max-w-md">
            {invStep === 'form' ? (
              <>
                <AlertDialogHeader>
                  <AlertDialogTitle className="flex items-center gap-2 text-[15px] text-[var(--ink)]">
                    <UserPlus className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Undang User Baru
                  </AlertDialogTitle>
                  <AlertDialogDescription className="text-[12.5px] text-[var(--muted-fg)]">
                    Pilih metode undangan. Keduanya diakhiri pendaftaran MFA TOTP saat login pertama.
                  </AlertDialogDescription>
                </AlertDialogHeader>

                <div className="space-y-3">
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Email</span>
                    <input
                      type="email"
                      value={invEmail}
                      onChange={(e) => setInvEmail(e.target.value)}
                      placeholder="nama@perusahaan.com"
                      className="h-9 w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] px-3 text-[13px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      autoFocus
                    />
                  </label>

                  <div>
                    <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Role</span>
                    <div className="flex overflow-hidden rounded-lg border border-[var(--line)]">
                      {(['user', 'superadmin'] as const).map((r) => (
                        <button
                          key={r}
                          type="button"
                          onClick={() => setInvRole(r)}
                          className={`flex flex-1 items-center justify-center gap-1 px-3 py-2 text-[11.5px] font-semibold transition-colors ${
                            invRole === r ? 'bg-[var(--accent)] text-[var(--accent-ink)]' : 'bg-[var(--bg)] text-[var(--muted-fg)] hover:bg-[var(--surface)]'
                          }`}
                        >
                          {r === 'superadmin' ? <ShieldCheck className="h-3 w-3" /> : <LogIn className="h-3 w-3" />}
                          {r}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Metode</span>
                    <div className="space-y-1.5">
                      {([
                        { id: 'email', title: 'Email undangan Cognito', desc: 'Password sementara dikirim otomatis; user wajib ganti saat login pertama.' },
                        { id: 'instant', title: 'Password instan (tanpa email)', desc: 'Password kuat dibuat sekarang — Anda salin & bagikan via kanal aman.' },
                      ] as const).map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => setInvMode(m.id)}
                          className={`flex w-full items-start gap-2 rounded-lg border p-2.5 text-left transition-colors ${
                            invMode === m.id ? 'border-[var(--accent)] bg-[var(--accent-soft)]' : 'border-[var(--line-soft)] bg-[var(--bg)] hover:border-[var(--line)]'
                          }`}
                        >
                          <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${invMode === m.id ? 'border-[var(--accent)]' : 'border-[var(--line)]'}`}>
                            {invMode === m.id && <span className="h-2 w-2 rounded-full" style={{ background: 'var(--accent)' }} />}
                          </span>
                          <span>
                            <span className="block text-[12px] font-semibold text-[var(--ink)]">{m.title}</span>
                            <span className="block text-[10.5px] leading-relaxed text-[var(--muted-fg)]">{m.desc}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <AlertDialogFooter>
                  <AlertDialogCancel className="rounded-lg border-[var(--line)]">Batal</AlertDialogCancel>
                  <AlertDialogAction
                    disabled={invBusy || !invEmail.trim()}
                    onClick={(e) => { e.preventDefault(); void submitInvite(); }}
                    className="maa-btn-primary rounded-lg"
                  >
                    {invBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                    Buat & Undang
                  </AlertDialogAction>
                </AlertDialogFooter>
              </>
            ) : (
              <>
                <AlertDialogHeader>
                  <AlertDialogTitle className="flex items-center gap-2 text-[15px] text-[var(--ink)]">
                    <Check className="h-4 w-4 text-emerald-600" /> User Berhasil Dibuat
                  </AlertDialogTitle>
                  <AlertDialogDescription className="text-[12.5px] text-[var(--muted-fg)]">
                    {invMode === 'email' && !invResult?.password
                      ? 'Email undangan Cognito (password sementara) sudah dikirim ke alamat berikut.'
                      : 'Password di bawah hanya ditampilkan SEKALI — salin dan bagikan via kanal aman.'}
                  </AlertDialogDescription>
                </AlertDialogHeader>

                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2 rounded-lg border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2">
                    <span className="text-[11px] text-[var(--muted-fg)]">Username</span>
                    <code className="font-mono text-[12px] text-[var(--ink)]">{invResult?.username}</code>
                  </div>
                  {invResult?.password && (
                    <div className="flex items-center justify-between gap-2 rounded-lg border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-2">
                      <span className="text-[11px] text-[var(--muted-fg)]">Password</span>
                      <code className="select-all font-mono text-[12.5px] font-bold text-[var(--ink)]">{invResult.password}</code>
                      <button
                        type="button"
                        onClick={() => copy(invResult.password!, 'pw')}
                        className="maa-btn-ghost flex items-center gap-1 px-2 py-1 text-[10.5px]"
                      >
                        {copied === 'pw' ? <Check className="h-3 w-3" /> : <ClipboardCopy className="h-3 w-3" />}
                        {copied === 'pw' ? 'tersalin' : 'salin'}
                      </button>
                    </div>
                  )}
                  <p className="rounded-lg bg-[var(--surface)] px-3 py-2 text-[11px] leading-relaxed text-[var(--muted-fg)]">
                    Login pertama: buka aplikasi → masukkan username + password → (bila metode email, buat password baru) → pindai QR MFA TOTP dengan Google Authenticator/Authy.
                  </p>
                </div>

                <AlertDialogFooter>
                  <AlertDialogAction onClick={closeInvite} className="maa-btn-primary m-0 w-full rounded-lg">
                    Selesai
                  </AlertDialogAction>
                </AlertDialogFooter>
              </>
            )}
          </AlertDialogContent>
        </AlertDialog>
      </SheetContent>
    </Sheet>
  );
}
