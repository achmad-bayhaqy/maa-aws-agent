'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AtSign, Blocks, Box, Cable, Check, ChevronDown, ClipboardCopy, Cloud, CloudUpload, Cloudy,
  Database, Edit3, Eye, FileText, KeyRound, Loader2, Lock, LogIn, Mail, PencilLine, Plug,
  Plus, RefreshCw, Save, Search, Server, Settings2, ShieldCheck, Sparkles, Table, Trash2,
  UserPlus, UserCog, Users, Webhook, X,
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
  adminDeleteUser, adminInviteUser, adminListUsers, adminRenameUser,
  adminResendInvite, adminSetPassword, adminSetUserRole, adminSetUserStatus,
  createConnector, deleteConnector, deleteKbDoc, exchangeOAuth, fmtBytes, getDocContent,
  getKbDocContent, getOAuthSettings, getSkillContent, listConnectors, listKbDocs, listSiteDocs,
  listSkills, presignUpload, relTime, saveDocContent, saveKbDocContent, saveOAuthSettings,
  startOAuth, syncKb, testConnector, updateConnector,
} from '@/lib/maa';
import type { AdminUser, Connector, MaaSkill, OAuthSettings } from '@/lib/maa';
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
  // v3.5: buka & edit isi dokumen (read/edit/delete dari UI + auto re-index)
  const [viewKey, setViewKey] = useState<string | null>(null);
  const [viewName, setViewName] = useState('');
  const [viewContent, setViewContent] = useState('');
  const [viewDraft, setViewDraft] = useState('');
  const [viewLoading, setViewLoading] = useState(false);
  const [viewEditing, setViewEditing] = useState(false);
  const [viewSaving, setViewSaving] = useState(false);

  const openDoc = async (d: KbDoc) => {
    setViewKey(d.key);
    setViewName(d.name || d.key);
    setViewEditing(false);
    setViewLoading(true);
    try {
      const r = await getKbDocContent(token, d.key);
      setViewContent(r.content || '');
      setViewDraft(r.content || '');
    } catch (e) {
      notify(`Gagal membuka dokumen: ${(e as Error).message}`);
      setViewKey(null);
    } finally {
      setViewLoading(false);
    }
  };

  const saveDoc = async () => {
    if (!viewKey) return;
    setViewSaving(true);
    try {
      const r = await saveKbDocContent(token, viewKey, viewDraft);
      setViewContent(viewDraft);
      setViewEditing(false);
      notify(`Dokumen tersimpan & re-index ${r.ingestion ? `(${r.ingestion})` : 'dimulai'}`, true);
      await refresh();
    } catch (e) {
      notify(`Simpan gagal: ${(e as Error).message}`);
    } finally {
      setViewSaving(false);
    }
  };

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
      const { uploadUrl, headers } = await presignUpload(token, file.name, file.type || 'application/octet-stream');
      const res = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
        headers: { ...(headers || {}) },
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
      if (viewKey === d.key) setViewKey(null);
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
          {viewKey ? (
            /* ---------- v3.5: pembuka/editor dokumen KB ---------- */
            <div className="animate-pop space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setViewKey(null)}
                  className="maa-btn-ghost flex items-center gap-1 px-2 py-1.5 text-[11.5px] font-medium"
                >
                  <X className="h-3.5 w-3.5" /> Kembali ke daftar
                </button>
                {viewEditing ? (
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setViewDraft(viewContent)}
                      disabled={viewSaving}
                      className="maa-btn-ghost px-2 py-1.5 text-[11.5px] font-medium disabled:opacity-50"
                    >
                      Batalkan
                    </button>
                    <button
                      type="button"
                      onClick={() => void saveDoc()}
                      disabled={viewSaving || viewDraft === viewContent}
                      className="maa-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11.5px] disabled:opacity-50"
                    >
                      {viewSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      Simpan & re-index
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setViewEditing(true)}
                    className="maa-btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-[11.5px]"
                  >
                    <Edit3 className="h-3.5 w-3.5" /> Edit isi
                  </button>
                )}
              </div>

              <div className="border-b border-[var(--line-soft)] pb-2">
                <p className="truncate text-[13.5px] font-bold text-[var(--ink)]">{viewName}</p>
                <p className="text-[10.5px] text-[var(--muted-fg)]">
                  {viewEditing ? 'Mode edit — simpan akan memicu re-index KB otomatis' : 'Pratinjau isi dokumen Knowledge Base'}
                </p>
              </div>

              {viewLoading ? (
                <div className="space-y-2">
                  <div className="skeleton-line h-4 w-3/4 rounded" />
                  <div className="skeleton-line h-4 rounded" />
                  <div className="skeleton-line h-4 w-5/6 rounded" />
                </div>
              ) : viewEditing ? (
                <textarea
                  value={viewDraft}
                  onChange={(e) => setViewDraft(e.target.value)}
                  spellCheck={false}
                  className="h-[62vh] w-full resize-y rounded-[10px] border border-[var(--line-soft)] bg-[var(--bg)] p-3 font-mono text-[12px] leading-relaxed text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                  aria-label="Editor isi dokumen KB"
                />
              ) : (
                <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-4">
                  <Markdown text={viewContent || '_(kosong)_'} />
                </div>
              )}
            </div>
          ) : (
          <>
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
                  <button
                    type="button"
                    aria-label={`Buka ${d.name || d.key}`}
                    title="Buka / edit isi dokumen"
                    onClick={() => void openDoc(d)}
                    className="rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
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
            💡 Agent juga bisa membuka/mengubah/menghapus dokumen lewat perintah chat — cukup minta, mis. “buka dokumen X”, “update dokumen Y ganti versi”, atau “hapus dokumen lama tentang Z”.
          </p>
          </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* --------------------------- Skills drawer (v3.5) --------------------------- */

export function SkillsDrawer({
  open, onOpenChange, token, notify,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  token: string;
  notify: (msg: string, ok?: boolean) => void;
}) {
  const [skills, setSkills] = useState<MaaSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [openName, setOpenName] = useState('');
  const [content, setContent] = useState('');
  const [contentLoading, setContentLoading] = useState(false);
  const [query, setQuery] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await listSkills(token);
      setSkills(r.skills || []);
    } catch (e) {
      notify(`Gagal memuat skills: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [token, notify]);

  useEffect(() => {
    if (open) {
      refresh();
      setOpenKey(null);
    }
  }, [open, refresh]);

  const viewSkill = async (s: MaaSkill) => {
    setOpenKey(s.key);
    setOpenName(s.name || s.folder);
    setContentLoading(true);
    try {
      const r = await getSkillContent(token, s.key);
      setContent(r.content || '');
    } catch (e) {
      notify(`Gagal membuka skill: ${(e as Error).message}`);
      setOpenKey(null);
    } finally {
      setContentLoading(false);
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter(
      (s) => s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)
    );
  }, [skills, query]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-md gap-0 p-0">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <Sparkles className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Skills Library
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Panduan eksekusi ahli (format Agent Skills) yang dimuat agent saat tugas cocok.
          </SheetDescription>
        </SheetHeader>

        <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
          {openKey ? (
            <div className="animate-pop space-y-3">
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setOpenKey(null)}
                  className="maa-btn-ghost flex items-center gap-1 px-2 py-1.5 text-[11.5px] font-medium"
                >
                  <X className="h-3.5 w-3.5" /> Kembali
                </button>
                <span className="font-mono text-[10px] text-[var(--muted-fg)]">SKILL.md</span>
              </div>
              <p className="border-b border-[var(--line-soft)] pb-2 text-[13.5px] font-bold text-[var(--ink)]">{openName}</p>
              {contentLoading ? (
                <div className="space-y-2">
                  <div className="skeleton-line h-4 w-3/4 rounded" />
                  <div className="skeleton-line h-4 rounded" />
                  <div className="skeleton-line h-4 w-5/6 rounded" />
                </div>
              ) : (
                <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-4">
                  <Markdown text={content || '_(kosong)_'} />
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="relative mb-3">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-fg)]" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Cari skill…"
                  className="h-9 w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] pl-8 pr-3 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                  aria-label="Cari skill"
                />
              </div>

              {loading ? (
                <div className="space-y-2">
                  <div className="skeleton-line h-12 rounded-[10px]" />
                  <div className="skeleton-line h-12 rounded-[10px]" />
                  <div className="skeleton-line h-12 rounded-[10px]" />
                </div>
              ) : filtered.length === 0 ? (
                <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 text-center">
                  <Sparkles className="mx-auto mb-2 h-6 w-6 text-[var(--muted-fg)]" />
                  <p className="text-[12.5px] font-medium text-[var(--ink)]">Belum ada skill terpasang</p>
                  <p className="text-[11px] leading-relaxed text-[var(--muted-fg)]">
                    Skill inti di-seed otomatis saat deployment. Anda juga bisa minta agent menyimpan skill baru via chat (“simpan pola kerja ini sebagai skill”).
                  </p>
                </div>
              ) : (
                <ul className="space-y-2">
                  {filtered.map((s) => (
                    <li key={s.key}>
                      <button
                        type="button"
                        onClick={() => void viewSkill(s)}
                        className="w-full rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2.5 text-left transition-colors hover:border-[var(--accent)]"
                      >
                        <span className="flex items-center gap-2">
                          <Sparkles className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
                          <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--ink)]">{s.name}</span>
                          <span className="shrink-0 font-mono text-[9.5px] text-[var(--muted-fg)]">{fmtBytes(s.size)}</span>
                        </span>
                        {s.description && (
                          <span className="mt-1 block line-clamp-2 text-[11px] leading-relaxed text-[var(--muted-fg)]">
                            {s.description}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <p className="mt-4 rounded-[10px] border border-[var(--line-soft)] bg-[var(--accent-soft)] px-3 py-2.5 text-[11.5px] leading-relaxed text-[var(--ink)]">
                💡 Agent memuat skill otomatis saat tugas cocok (progressive disclosure). Minta agent menyimpan pola kerja baru: “simpan ini sebagai skill”.
              </p>
            </>
          )}
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

  // ---- Management User v3.5: rename & ganti role ----
  const [renameUser, setRenameUser] = useState<AdminUser | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameBusy, setRenameBusy] = useState(false);

  const submitRename = async () => {
    if (!renameUser) return;
    const name = renameValue.trim();
    if (!name) {
      notify('Nama tampilan tidak boleh kosong');
      return;
    }
    setRenameBusy(true);
    try {
      await adminRenameUser(token, renameUser.username, name);
      setUsers((prev) => prev.map((x) => (x.username === renameUser.username ? { ...x, name } : x)));
      notify(`Nama ${renameUser.username} diubah menjadi "${name}"`, true);
      setRenameUser(null);
    } catch (e) {
      notify(`Rename gagal: ${(e as Error).message}`);
    } finally {
      setRenameBusy(false);
    }
  };

  const doSetRole = async (u: AdminUser, role: 'user' | 'superadmin') => {
    setBusyUser(u.username);
    try {
      await adminSetUserRole(token, u.username, role);
      setUsers((prev) => prev.map((x) => (x.username === u.username ? { ...x, role } : x)));
      notify(`Role ${u.username} → ${role}. Berlaku pada login/token berikutnya.`, true);
    } catch (e) {
      notify(`Gagal ganti role: ${(e as Error).message}`);
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
                          {u.name ? `${u.name} · ` : ''}{u.email || '—'}
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
                        onClick={() => { setRenameUser(u); setRenameValue(u.name || ''); }}
                        className="maa-btn-ghost flex items-center gap-1 px-2 py-1 text-[10.5px] font-medium"
                        title="Ganti nama tampilan user"
                      >
                        <PencilLine className="h-3 w-3" /> Rename
                      </button>
                      <ConfirmAction
                        title={u.role === 'superadmin' ? 'Jadikan user biasa?' : 'Jadikan superadmin?'}
                        description={
                          u.role === 'superadmin'
                            ? `"${u.username}" akan KEHILANGAN akses admin (guardrail & Management User).`
                            : `"${u.username}" akan mendapat akses penuh superadmin (bypass guardrail & kelola user).`
                        }
                        confirmLabel="Ya, ganti role"
                        onConfirm={() => void doSetRole(u, u.role === 'superadmin' ? 'user' : 'superadmin')}
                        trigger={
                          <button
                            type="button"
                            disabled={busyUser === u.username}
                            className="maa-btn-ghost flex items-center gap-1 px-2 py-1 text-[10.5px] font-medium disabled:opacity-50"
                            title="Ganti role user ↔ superadmin"
                          >
                            <UserCog className="h-3 w-3" /> Ganti role
                          </button>
                        }
                      />
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

        {/* ---------- modal rename user (v3.5) ---------- */}
        <AlertDialog
          open={!!renameUser}
          onOpenChange={(v) => { if (!v) setRenameUser(null); }}
        >
          <AlertDialogContent className="max-w-sm">
            <AlertDialogHeader>
              <AlertDialogTitle className="flex items-center gap-2 text-[15px] text-[var(--ink)]">
                <PencilLine className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Rename User
              </AlertDialogTitle>
              <AlertDialogDescription className="text-[12.5px] text-[var(--muted-fg)]">
                Ganti nama tampilan untuk <b className="text-[var(--ink)]">{renameUser?.username}</b>. Username login tidak berubah.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder="Nama tampilan (maks 60 karakter)"
              maxLength={60}
              className="h-9 w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] px-3 text-[13px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
              autoFocus
              aria-label="Nama tampilan baru"
            />
            <AlertDialogFooter>
              <AlertDialogCancel className="rounded-lg border-[var(--line)]">Batal</AlertDialogCancel>
              <AlertDialogAction
                disabled={renameBusy || !renameValue.trim()}
                onClick={(e) => { e.preventDefault(); void submitRename(); }}
                className="maa-btn-primary rounded-lg"
              >
                {renameBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Simpan
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

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


/* ---------------------------- konektor drawer ---------------------------- */

type ConnectorField = {
  key: string;
  label: string;
  placeholder?: string;
  secret?: boolean;
  area?: boolean;
  half?: boolean;
  hint?: string;
  select?: string[];
  /** hanya tampil bila form.authMethod === opt (multi-opsi login) */
  opt?: string;
};

type ConnectorAuthMethod = { key: string; label: string; desc?: string };

const CONNECTOR_META: Record<string, {
  label: string; desc: string; fields: ConnectorField[];
  authMethods?: ConnectorAuthMethod[];
  oauthProvider?: 'google' | 'microsoft';
}> = {
  gdrive: {
    label: 'Google Drive',
    desc: 'Login popup Google (rekomendasi) atau refresh token manual (Google Cloud Console, scope drive.readonly).',
    oauthProvider: 'google',
    authMethods: [
      { key: 'oauth', label: 'Login Google', desc: 'Popup login akun Google — tanpa token manual' },
      { key: 'manual', label: 'Token Manual', desc: 'Tempel refresh token / access token sendiri' },
    ],
    fields: [
      { key: 'accessToken', label: 'Access Token (opsional bila pakai refresh)', secret: true, area: true, opt: 'manual' },
      { key: 'refreshToken', label: 'Refresh Token (opsional)', secret: true, area: true, opt: 'manual' },
      { key: 'clientId', label: 'Client ID (utk refresh)', half: true, opt: 'manual' },
      { key: 'clientSecret', label: 'Client Secret (utk refresh)', secret: true, half: true, opt: 'manual' },
      { key: 'folderId', label: 'Folder ID (opsional — batasi akses ke 1 folder)' },
    ],
  },
  onedrive: {
    label: 'OneDrive',
    desc: 'Login popup Microsoft (rekomendasi, PKCE) atau token manual (Entra ID, scope Files.Read.All).',
    oauthProvider: 'microsoft',
    authMethods: [
      { key: 'oauth', label: 'Login Microsoft', desc: 'Popup login akun Microsoft/Entra — tanpa token manual' },
      { key: 'manual', label: 'Token Manual', desc: 'Tempel refresh token / access token sendiri' },
    ],
    fields: [
      { key: 'accessToken', label: 'Access Token (opsional bila pakai refresh)', secret: true, area: true, opt: 'manual' },
      { key: 'refreshToken', label: 'Refresh Token (opsional)', secret: true, area: true, opt: 'manual' },
      { key: 'clientId', label: 'Client ID (utk refresh)', half: true, opt: 'manual' },
      { key: 'clientSecret', label: 'Client Secret (utk refresh)', secret: true, half: true, opt: 'manual' },
      { key: 'tenant', label: 'Tenant (opsional, default: common)', opt: 'manual' },
    ],
  },
  adls: {
    label: 'ADLS Gen2',
    desc: 'Azure Data Lake Storage Gen2: Service Principal (OAuth), SAS token, atau account key.',
    authMethods: [
      { key: 'sp', label: 'Service Principal', desc: 'OAuth2 client_credentials Entra ID (rekomendasi)' },
      { key: 'sas', label: 'SAS Token' },
      { key: 'key', label: 'Account Key' },
    ],
    fields: [
      { key: 'storageAccount', label: 'Storage Account', half: true, placeholder: 'mydatalake' },
      { key: 'filesystem', label: 'Filesystem (container)', half: true },
      { key: 'tenant', label: 'Tenant ID', half: true, opt: 'sp', placeholder: 'xxxxxxxx-xxxx-...' },
      { key: 'clientId', label: 'Client ID (App registration)', half: true, opt: 'sp' },
      { key: 'clientSecret', label: 'Client Secret', secret: true, opt: 'sp' },
      { key: 'sasToken', label: 'SAS Token', secret: true, area: true, opt: 'sas' },
      { key: 'accountKey', label: 'Account Key', secret: true, area: true, opt: 'key' },
    ],
  },
  gcs: {
    label: 'Google Cloud Storage',
    desc: 'GCS: login popup Google (rekomendasi) atau Service Account JSON dari GCP Console.',
    oauthProvider: 'google',
    authMethods: [
      { key: 'oauth', label: 'Login Google', desc: 'Popup login akun Google — akses project/bucket akun Anda' },
      { key: 'sa', label: 'Service Account', desc: 'JSON key service account (server-to-server)' },
    ],
    fields: [
      { key: 'project', label: 'Project ID (opsional bila isi bucket)', half: true, placeholder: 'my-gcp-project' },
      { key: 'bucket', label: 'Bucket (opsional)', half: true, placeholder: 'my-bucket' },
      { key: 'serviceAccountJson', label: 'Service Account JSON', secret: true, area: true, opt: 'sa', placeholder: '{"type": "service_account", ...}' },
    ],
  },
  bigquery: {
    label: 'Google BigQuery',
    desc: 'BigQuery: login popup Google (rekomendasi) atau Service Account JSON — baca dataset & tabel.',
    oauthProvider: 'google',
    authMethods: [
      { key: 'oauth', label: 'Login Google', desc: 'Popup login akun Google — akses project akun Anda' },
      { key: 'sa', label: 'Service Account', desc: 'JSON key service account (server-to-server)' },
    ],
    fields: [
      { key: 'project', label: 'Project ID', half: true, placeholder: 'my-gcp-project' },
      { key: 'dataset', label: 'Dataset (opsional)', half: true },
      { key: 'serviceAccountJson', label: 'Service Account JSON', secret: true, area: true, opt: 'sa', placeholder: '{"type": "service_account", ...}' },
    ],
  },
  s3: {
    label: 'AWS S3',
    desc: 'S3: IAM user access key (opsional session token utk STS) — browse & baca objek.',
    authMethods: [{ key: 'keys', label: 'Access Key', desc: 'IAM access key + secret (+ session token)' }],
    fields: [
      { key: 'region', label: 'Region', half: true, placeholder: 'us-east-1' },
      { key: 'bucket', label: 'Bucket (opsional)', half: true, placeholder: 'my-bucket' },
      { key: 'accessKey', label: 'Access Key ID', placeholder: 'AKIA...' },
      { key: 'secretAccessKey', label: 'Secret Access Key', secret: true },
      { key: 'sessionToken', label: 'Session Token (opsional, utk STS)', secret: true, area: true },
    ],
  },
  sftp: {
    label: 'SFTP',
    desc: 'Server SFTP: autentikasi password atau private key (PEM). Dipakai agent utk list & baca file.',
    fields: [
      { key: 'host', label: 'Host', half: true, placeholder: 'sftp.example.com' },
      { key: 'port', label: 'Port', half: true, placeholder: '22' },
      { key: 'username', label: 'Username' },
      { key: 'password', label: 'Password (opsional bila pakai key)', secret: true },
      { key: 'privateKey', label: 'Private Key PEM (opsional)', secret: true, area: true },
      { key: 'path', label: 'Path default (opsional, mis. /data)' },
    ],
  },
  api: {
    label: 'REST API Manual',
    desc: 'Endpoint API kustom: agent akan memanggil URL ini saat butuh data (bisa pakai header auth).',
    fields: [
      { key: 'method', label: 'Method', select: ['GET', 'POST', 'PUT', 'PATCH'], half: true },
      { key: 'expectStatus', label: 'Status diharapkan', half: true, placeholder: '2xx atau 200' },
      { key: 'url', label: 'URL', placeholder: 'https://api.example.com/v1/data' },
      { key: 'headers', label: 'Headers (JSON, opsional)', area: true, placeholder: '{"Authorization": "Bearer xxx"}' },
      { key: 'body', label: 'Body (opsional, utk POST/PUT)', area: true },
    ],
  },
  mcp: {
    label: 'MCP Server',
    desc: 'MCP (Model Context Protocol) via Streamable HTTP: agent memakai tools dari server ini.',
    fields: [
      { key: 'url', label: 'URL MCP', placeholder: 'https://mcp.example.com/mcp' },
      { key: 'headers', label: 'Headers (JSON, opsional)', area: true, placeholder: '{"Authorization": "Bearer xxx"}' },
    ],
  },
};

const TYPE_ICON: Record<string, React.ReactNode> = {
  gdrive: <Cloud className="h-4 w-4" />,
  onedrive: <Cloudy className="h-4 w-4" />,
  adls: <Database className="h-4 w-4" />,
  gcs: <Box className="h-4 w-4" />,
  bigquery: <Table className="h-4 w-4" />,
  s3: <Box className="h-4 w-4" />,
  sftp: <Server className="h-4 w-4" />,
  api: <Webhook className="h-4 w-4" />,
  mcp: <Blocks className="h-4 w-4" />,
};

export function ConnectorDrawer({
  open, onOpenChange, token, notify,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  token: string;
  notify: (msg: string, ok?: boolean) => void;
}) {
  const [items, setItems] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [ctype, setCtype] = useState<string>('gdrive');
  const [name, setName] = useState('');
  const [form, setForm] = useState<Record<string, string>>({});
  const [testRes, setTestRes] = useState<{ ok: boolean; message: string; detail: string } | null>(null);
  const [delItem, setDelItem] = useState<Connector | null>(null);
  const [oauthCfg, setOauthCfg] = useState<OAuthSettings | null>(null);
  const [oauthMsg, setOauthMsg] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsForm, setSettingsForm] = useState<Record<string, string>>({});
  const [settingsSaving, setSettingsSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await listConnectors(token);
      setItems(r.connectors || []);
    } catch (e) {
      notify(`Gagal memuat konektor: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [token, notify]);

  useEffect(() => {
    if (open) {
      refresh();
      getOAuthSettings(token).then(setOauthCfg).catch(() => setOauthCfg(null));
    }
  }, [open, refresh, token]);

  // dengarkan hasil dari popup OAuth (public/oauth/callback.html)
  useEffect(() => {
    const onMsg = async (ev: MessageEvent) => {
      const d = ev.data as { source?: string; code?: string; state?: string; error?: string };
      if (!d || d.source !== 'maa-oauth') return;
      if (d.error) {
        setOauthMsg(`Login dibatalkan: ${d.error}`);
        return;
      }
      if (d.code && d.state) {
        setOauthMsg(null);
        setBusy('oauth');
        try {
          const r = await exchangeOAuth(token, { code: d.code, state: d.state, name: name.trim() || undefined });
          notify(`✓ ${r.name} terhubung — ${r.message}`, true);
          setFormOpen(false);
          resetForm();
          refresh();
        } catch (e) {
          setOauthMsg(`Gagal menukar kode OAuth: ${(e as Error).message}`);
        } finally {
          setBusy('');
        }
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [token, notify, name, refresh]);

  const authMethod = form.authMethod || CONNECTOR_META[ctype]?.authMethods?.[0]?.key || '';

  const doOAuthLogin = async () => {
    setOauthMsg(null);
    setBusy('oauth-start');
    try {
      const r = await startOAuth(token, ctype);
      window.open(r.url, 'maa-oauth', 'width=520,height=680,menubar=no,toolbar=no');
    } catch (e) {
      setOauthMsg((e as Error).message);
    } finally {
      setBusy('');
    }
  };

  const doSaveSettings = async () => {
    setSettingsSaving(true);
    try {
      const payload: Record<string, { clientId?: string; clientSecret?: string; tenant?: string }> = {};
      if (settingsForm.gClientId || settingsForm.gClientSecret) {
        payload.google = {};
        if (settingsForm.gClientId) payload.google.clientId = settingsForm.gClientId;
        if (settingsForm.gClientSecret) payload.google.clientSecret = settingsForm.gClientSecret;
      }
      if (settingsForm.mClientId || settingsForm.mClientSecret || settingsForm.mTenant) {
        payload.microsoft = {};
        if (settingsForm.mClientId) payload.microsoft.clientId = settingsForm.mClientId;
        if (settingsForm.mClientSecret) payload.microsoft.clientSecret = settingsForm.mClientSecret;
        if (settingsForm.mTenant) payload.microsoft.tenant = settingsForm.mTenant;
      }
      await saveOAuthSettings(token, payload);
      notify('Pengaturan OAuth app tersimpan', true);
      getOAuthSettings(token).then(setOauthCfg).catch(() => {});
      setSettingsForm({});
    } catch (e) {
      notify(`Gagal simpan pengaturan: ${(e as Error).message}`);
    } finally {
      setSettingsSaving(false);
    }
  };

  const resetForm = () => {
    setEditId(null);
    setCtype('gdrive');
    setName('');
    setForm({});
    setTestRes(null);
    setOauthMsg(null);
  };

  const startEdit = (c: Connector) => {
    setEditId(c.connectorId);
    setCtype(c.type);
    setName(c.name);
    const cfg = Object.fromEntries(Object.entries(c.config || {}).map(([k, v]) => [k, String(v ?? '')]));
    cfg.authMethod = cfg.authMethod || CONNECTOR_META[c.type]?.authMethods?.[0]?.key || '';
    setForm(cfg);
    setTestRes(null);
    setOauthMsg(null);
    setFormOpen(true);
  };

  const collectConfig = () =>
    Object.fromEntries(
      Object.entries(form)
        .filter(([k, v]) => v !== '' && k !== 'authMethod')
        .map(([k, v]) => [k, v]),
    );

  const doTest = async () => {
    setTestRes(null);
    setBusy('test');
    try {
      const r = await testConnector(
        token,
        editId ?? undefined,
        editId ? collectConfig() : { type: ctype, config: collectConfig() },
      );
      setTestRes(r);
    } catch (e) {
      setTestRes({ ok: false, message: (e as Error).message, detail: '' });
    } finally {
      setBusy('');
    }
  };

  const doSave = async () => {
    if (!name.trim()) {
      notify('Nama konektor wajib diisi');
      return;
    }
    setBusy('save');
    try {
      let savedId = editId;
      if (editId) await updateConnector(token, editId, { name, config: collectConfig() });
      else {
        const created = await createConnector(token, name, ctype, collectConfig());
        savedId = created.connectorId;
      }
      // auto test setelah simpan (dengan config final yg tersimpan)
      if (savedId) {
        try {
          const tr = await testConnector(token, savedId);
          notify(tr.ok ? `✓ ${name} — ${tr.message}` : `✗ Test: ${tr.message}`, tr.ok);
        } catch {
          /* test gagal jangan gagalkan simpan */
        }
      } else {
        notify(editId ? 'Konektor diperbarui' : 'Konektor ditambahkan', true);
      }
      setFormOpen(false);
      resetForm();
      refresh();
    } catch (e) {
      notify(`Gagal menyimpan: ${(e as Error).message}`);
    } finally {
      setBusy('');
    }
  };

  const doDelete = async (c: Connector) => {
    setBusy(c.connectorId);
    try {
      await deleteConnector(token, c.connectorId);
      notify(`Konektor "${c.name}" dihapus`, true);
      refresh();
    } catch (e) {
      notify(`Gagal menghapus: ${(e as Error).message}`);
    } finally {
      setBusy('');
    }
  };

  const meta = CONNECTOR_META[ctype];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-xl gap-0 overflow-y-auto p-0 sm:max-w-xl">
        <SheetHeader className="border-b border-[var(--line)] px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-[14px] font-bold text-[var(--ink)]">
            <Cable className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Konektor Data
          </SheetTitle>
          <SheetDescription className="text-[11.5px] text-[var(--muted-fg)]">
            Hubungkan sumber data eksternal (Google Drive, OneDrive, ADLS Gen2, GCS, BigQuery, S3,
            SFTP, API, MCP) — agent bisa menggunakannya di chat. Login popup OAuth tersedia;
            selalu uji koneksi setelah menyimpan.
          </SheetDescription>
        </SheetHeader>

        <div className="px-5 py-4">
          {!formOpen && (
            <button
              type="button"
              onClick={() => { resetForm(); setFormOpen(true); }}
              className="maa-btn-primary mb-4 flex h-9 w-full items-center justify-center gap-2 text-[13px]"
            >
              <Plus className="h-4 w-4" /> Tambah Konektor
            </button>
          )}

          {formOpen && (
            <div className="mb-5 rounded-[12px] border border-[var(--line)] bg-[var(--surface)] p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[12.5px] font-bold text-[var(--ink)]">
                  {editId ? 'Edit Konektor' : 'Konektor Baru'}
                </span>
                <button type="button" onClick={() => { setFormOpen(false); resetForm(); }}
                  className="rounded p-1 text-[var(--muted-fg)] hover:bg-[var(--muted-bg)]">
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* pilih tipe */}
              {!editId && (
                <div className="mb-3 grid grid-cols-3 gap-1.5">
                  {Object.entries(CONNECTOR_META).map(([t, m]) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => { setCtype(t); setForm({}); setTestRes(null); }}
                      className={`flex flex-col items-center gap-1 rounded-[10px] border px-2 py-2 text-[10.5px] font-medium transition-colors ${
                        ctype === t
                          ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]'
                          : 'border-[var(--line-soft)] text-[var(--muted-fg)] hover:border-[var(--line)]'
                      }`}
                    >
                      <span style={{ color: ctype === t ? 'var(--accent)' : undefined }}>{TYPE_ICON[t]}</span>
                      {m.label}
                    </button>
                  ))}
                </div>
              )}

              <p className="mb-3 rounded-lg bg-[var(--accent-soft)] px-2.5 py-1.5 text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
                {meta.desc}
              </p>

              {/* pilih opsi login (bila tipe punya >1 metode auth) */}
              {meta.authMethods && meta.authMethods.length > 1 && (
                <div className="mb-3">
                  <label className="mb-1.5 block text-[11px] font-semibold text-[var(--muted-fg)]">Opsi Login</label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {meta.authMethods.map((m) => (
                      <button
                        key={m.key}
                        type="button"
                        title={m.desc}
                        onClick={() => setForm((s) => ({ ...s, authMethod: m.key }))}
                        className={`flex items-center gap-1.5 rounded-[10px] border px-2.5 py-2 text-left text-[11px] font-medium transition-colors ${
                          authMethod === m.key
                            ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]'
                            : 'border-[var(--line-soft)] text-[var(--muted-fg)] hover:border-[var(--line)]'
                        }`}
                      >
                        {m.key === 'oauth' && meta.oauthProvider === 'google' && <LogIn className="h-3.5 w-3.5 shrink-0" />}
                        {m.key === 'oauth' && meta.oauthProvider === 'microsoft' && <LogIn className="h-3.5 w-3.5 shrink-0" />}
                        {m.key === 'oauth' && !meta.oauthProvider && <KeyRound className="h-3.5 w-3.5 shrink-0" />}
                        {m.key !== 'oauth' && <KeyRound className="h-3.5 w-3.5 shrink-0" />}
                        {m.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* tombol login popup OAuth (rekomendasi) */}
              {meta.oauthProvider && authMethod === 'oauth' && (
                <div className="mb-3 rounded-[12px] border border-[var(--line)] bg-[var(--bg)] p-3">
                  <button
                    type="button"
                    onClick={doOAuthLogin}
                    disabled={busy !== ''}
                    className="maa-btn-primary flex h-9 w-full items-center justify-center gap-2 text-[12.5px] disabled:opacity-50"
                  >
                    {busy.startsWith('oauth') ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
                    {meta.oauthProvider === 'google' ? 'Masuk dengan Google' : 'Masuk dengan Microsoft'}
                  </button>
                  <p className="mt-2 text-[10px] leading-relaxed text-[var(--muted-fg)]">
                    Popup consent penyedia akan terbuka; setelah setuju, koneksi otomatis dibuat + diuji.
                    Token disimpan terenkripsi KMS — tidak pernah tampil di UI.
                  </p>
                  {oauthCfg && !oauthCfg[meta.oauthProvider]?.configured && (
                    <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--danger)]">
                      OAuth app {meta.oauthProvider} belum dikonfigurasi — isi Client ID/Secret di
                      “Pengaturan OAuth App” di bawah.
                    </p>
                  )}
                </div>
              )}

              {oauthMsg && (
                <p className="mb-3 rounded-lg border border-[var(--danger)]/40 bg-[var(--danger)]/10 px-2.5 py-1.5 text-[10.5px] text-[var(--ink)]">
                  {oauthMsg}
                </p>
              )}

              <label className="mb-1.5 block text-[11px] font-semibold text-[var(--muted-fg)]">Nama Konektor</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="mis. Drive Marketing"
                className="mb-3 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
              />

              <div className="mb-3 grid grid-cols-2 gap-2">
                {meta.fields
                  .filter((f) => !f.opt || f.opt === authMethod)
                  .map((f) => (
                  <div key={f.key} className={f.area || f.select ? 'col-span-2' : f.half ? 'col-span-1' : 'col-span-2'}>
                    <label className="mb-1 block text-[11px] font-semibold text-[var(--muted-fg)]">{f.label}</label>
                    {f.select ? (
                      <select
                        value={form[f.key] ?? f.select[0]}
                        onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                        className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      >
                        {f.select.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.area ? (
                      <textarea
                        value={form[f.key] ?? ''}
                        onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                        placeholder={f.secret ? 'kosongkan bila tidak diubah' : f.placeholder}
                        rows={f.key === 'privateKey' ? 4 : 2}
                        className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 font-mono text-[11.5px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      />
                    ) : (
                      <input
                        type={f.secret ? 'password' : 'text'}
                        value={form[f.key] ?? ''}
                        onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                        placeholder={f.placeholder || (f.secret && editId ? '••• (tidak diubah)' : '')}
                        className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      />
                    )}
                  </div>
                ))}
              </div>

              {/* hasil test */}
              {testRes && (
                <div
                  className={`mb-3 rounded-[10px] border px-3 py-2.5 text-[11.5px] ${
                    testRes.ok
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                      : 'border-[var(--danger)]/40 bg-[var(--danger)]/10 text-[var(--ink)]'
                  }`}
                >
                  <span className="font-bold">{testRes.ok ? '✓ Koneksi berhasil' : '✗ Koneksi gagal'}</span>
                  <span className="ml-1.5">{testRes.message}</span>
                  {testRes.detail && (
                    <span className="mt-1 block break-all font-mono text-[10px] opacity-80">{testRes.detail}</span>
                  )}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={doTest}
                  disabled={busy !== ''}
                  className="maa-btn-ghost flex h-9 flex-1 items-center justify-center gap-1.5 text-[12.5px] disabled:opacity-50"
                >
                  {busy === 'test' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plug className="h-3.5 w-3.5" />}
                  Test Koneksi
                </button>
                <button
                  type="button"
                  onClick={doSave}
                  disabled={busy !== ''}
                  className="maa-btn-primary flex h-9 flex-1 items-center justify-center gap-1.5 text-[12.5px] disabled:opacity-50"
                >
                  {busy === 'save' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  {editId ? 'Simpan Perubahan' : 'Simpan Konektor'}
                </button>
              </div>
              <p className="mt-2 text-[10px] text-[var(--muted-fg)]">
                Test koneksi dijalankan dari server (bukan browser) — hasilnya sama seperti saat agent memakainya.
              </p>
            </div>
          )}

          {/* daftar konektor */}
          {loading ? (
            <div className="flex items-center justify-center py-8 text-[var(--muted-fg)]">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : items.length === 0 && !formOpen ? (
            <div className="rounded-[12px] border border-dashed border-[var(--line)] px-4 py-10 text-center">
              <Cable className="mx-auto mb-2 h-6 w-6 text-[var(--muted-fg)]" />
              <p className="text-[12.5px] font-semibold text-[var(--ink)]">Belum ada konektor</p>
              <p className="mt-1 text-[11px] text-[var(--muted-fg)]">
                Hubungkan Google Drive, OneDrive, ADLS Gen2, GCS, BigQuery, S3, SFTP, API manual,
                atau MCP server.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {items.map((c) => {
                const ok = c.status === 'ok';
                const failed = c.status === 'failed';
                return (
                  <div key={c.connectorId} className="rounded-[12px] border border-[var(--line)] bg-[var(--surface)] p-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-start gap-2.5">
                        <span
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--line-soft)] bg-[var(--bg)]"
                          style={{ color: 'var(--accent)' }}
                        >
                          {TYPE_ICON[c.type] || <Plug className="h-4 w-4" />}
                        </span>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate text-[12.5px] font-bold text-[var(--ink)]">{c.name}</span>
                            <span
                              title={c.status === 'ok' ? 'koneksi OK' : failed ? 'test terakhir gagal' : 'belum diuji'}
                              className={`h-2 w-2 shrink-0 rounded-full ${
                                ok ? 'bg-emerald-400' : failed ? 'bg-[var(--danger)]' : 'bg-zinc-500'
                              }`}
                            />
                            {c.owner && <span className="shrink-0 rounded-full bg-[var(--muted-bg)] px-1.5 py-px font-mono text-[9px] text-[var(--muted-fg)]">{c.owner}</span>}
                          </div>
                          <span className="block text-[10.5px] text-[var(--muted-fg)]">
                            {CONNECTOR_META[c.type]?.label || c.type}
                            {c.lastTestMsg ? ` · ${c.lastTestMsg.slice(0, 80)}` : ''}
                            {c.lastTestAt ? ` · ${relTime(c.lastTestAt)}` : ''}
                          </span>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-0.5">
                        <button
                          type="button"
                          title="Test koneksi"
                          disabled={busy !== ''}
                          onClick={async () => {
                            setBusy(c.connectorId);
                            try {
                              const r = await testConnector(token, c.connectorId);
                              notify(r.ok ? `✓ ${r.message}` : `✗ ${r.message}`, r.ok);
                              refresh();
                            } catch (e) {
                              notify(`Gagal test: ${(e as Error).message}`);
                            } finally {
                              setBusy('');
                            }
                          }}
                          className="rounded p-1.5 text-[var(--muted-fg)] hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
                        >
                          {busy === c.connectorId ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                        </button>
                        <button
                          type="button"
                          title="Edit"
                          onClick={() => startEdit(c)}
                          className="rounded p-1.5 text-[var(--muted-fg)] hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
                        >
                          <PencilLine className="h-3.5 w-3.5" />
                        </button>
                        <ConfirmAction
                          trigger={
                            <button type="button" title="Hapus"
                              className="rounded p-1.5 text-[var(--muted-fg)] hover:bg-[var(--muted-bg)] hover:text-[var(--danger)]">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          }
                          title={`Hapus konektor "${c.name}"?`}
                          description="Agent tidak akan bisa lagi mengakses sumber data ini."
                          confirmLabel="Hapus"
                          busy={busy === c.connectorId}
                          onConfirm={() => doDelete(c)}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ---------------- pengaturan OAuth app (superadmin) ---------------- */}
          <div className="mt-4 border-t border-[var(--line)] pt-4">
            <button
              type="button"
              onClick={() => setSettingsOpen((v) => !v)}
              className="flex w-full items-center justify-between text-left"
            >
              <span className="flex items-center gap-2 text-[12px] font-bold text-[var(--ink)]">
                <Settings2 className="h-4 w-4" style={{ color: 'var(--accent)' }} /> Pengaturan OAuth App
                <span className="rounded-full bg-[var(--muted-bg)] px-1.5 py-px font-mono text-[9px] text-[var(--muted-fg)]">admin</span>
              </span>
              <ChevronDown className={`h-4 w-4 text-[var(--muted-fg)] transition-transform ${settingsOpen ? 'rotate-180' : ''}`} />
            </button>
            <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
              Client ID/Secret untuk login popup Google &amp; Microsoft (sekali untuk semua user).
              Secret disimpan terenkripsi KMS.
            </p>
            {settingsOpen && (
              <div className="mt-2 rounded-[12px] border border-[var(--line)] bg-[var(--surface)] p-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-[10.5px] font-semibold text-[var(--muted-fg)]">
                      Google Client ID {oauthCfg?.google?.configured ? '✓' : ''}
                    </label>
                    <input
                      value={settingsForm.gClientId ?? oauthCfg?.google?.clientId ?? ''}
                      onChange={(e) => setSettingsForm((s) => ({ ...s, gClientId: e.target.value }))}
                      placeholder="xxxx.apps.googleusercontent.com"
                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10.5px] font-semibold text-[var(--muted-fg)]">Google Client Secret</label>
                    <input
                      type="password"
                      value={settingsForm.gClientSecret ?? ''}
                      onChange={(e) => setSettingsForm((s) => ({ ...s, gClientSecret: e.target.value }))}
                      placeholder={oauthCfg?.google?.configured ? '••• (tidak diubah)' : 'GOCSPX-...'}
                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10.5px] font-semibold text-[var(--muted-fg)]">
                      Microsoft Client ID {oauthCfg?.microsoft?.configured ? '✓' : ''}
                    </label>
                    <input
                      value={settingsForm.mClientId ?? oauthCfg?.microsoft?.clientId ?? ''}
                      onChange={(e) => setSettingsForm((s) => ({ ...s, mClientId: e.target.value }))}
                      placeholder="App registration ID"
                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10.5px] font-semibold text-[var(--muted-fg)]">Microsoft Client Secret</label>
                    <input
                      type="password"
                      value={settingsForm.mClientSecret ?? ''}
                      onChange={(e) => setSettingsForm((s) => ({ ...s, mClientSecret: e.target.value }))}
                      placeholder={oauthCfg?.microsoft?.configured ? '••• (tidak diubah)' : ''}
                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="mb-1 block text-[10.5px] font-semibold text-[var(--muted-fg)]">Microsoft Tenant (opsional)</label>
                    <input
                      value={settingsForm.mTenant ?? ''}
                      onChange={(e) => setSettingsForm((s) => ({ ...s, mTenant: e.target.value }))}
                      placeholder="common / organizational / tenant-id"
                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                    />
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={doSaveSettings}
                    disabled={settingsSaving}
                    className="maa-btn-primary flex h-8 items-center gap-1.5 px-3 text-[11.5px] disabled:opacity-50"
                  >
                    {settingsSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    Simpan
                  </button>
                  {oauthCfg?.redirectUri && (
                    <button
                      type="button"
                      title="Klik untuk salin"
                      onClick={() => navigator.clipboard?.writeText(oauthCfg.redirectUri)}
                      className="flex min-w-0 items-center gap-1 rounded-lg border border-[var(--line-soft)] px-2 py-1.5 text-[10px] text-[var(--muted-fg)] hover:text-[var(--ink)]"
                    >
                      <ClipboardCopy className="h-3 w-3 shrink-0" />
                      <span className="truncate font-mono">Redirect URI: {oauthCfg.redirectUri}</span>
                    </button>
                  )}
                </div>
                <p className="mt-2 text-[10px] leading-relaxed text-[var(--muted-fg)]">
                  Setup: di Google Cloud Console buat OAuth Client (Web application) + tambahkan redirect URI di atas;
                  di Entra ID buat App registration (Web) + redirect URI, aktifkan ID token tidak wajib.
                  Scope dipakai read-only (least privilege).
                </p>
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
