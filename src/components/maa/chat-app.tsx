'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ChevronDown, LogOut, Menu, MessageSquarePlus, PanelRightClose,
  PanelRightOpen, RefreshCcw, ShieldCheck, Sparkles, X,
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useToast } from '@/hooks/use-toast';
import {
  CONFIG, deleteSession, getModels, getStatus, getSessions, getTrace, loadLastSession,
  presignChatUpload, revokeToken, saveLastSession, sendChat, sessionIdFromPath, signOutAll,
  stripClarifyBlock, translateText, type Attachment, type AutoRoute, type ChatMessage,
  type ChatMode, type ChatStatus, type MeInfo, type MaaModel, type SessionRow,
  type Tokens, type TodoItem, type TraceEvent,
} from '@/lib/maa';
import { Logo, LogoWordmark } from './logo';
import { SidebarContent } from './sidebar';
import { Composer, type PendingUpload } from './composer';
import { MessageList } from './message-list';
import { TracePanel } from './trace-panel';
import { ConfirmModal } from './confirm-modal';
import { TodoPanel } from './todo-panel';
import { AdminDrawer, DocsDrawer, KbDrawer } from './drawers';
import { ThemeDialog, ThemeSwitcher } from './theme-switcher';
import { initTheme, type MaaTheme } from './theme';

const SUGGESTIONS = ['List EC2', 'Analisis biaya 30 hari', 'Buat VPC bernama staging', 'Apa runbook insiden database?'];

type LastAction = { kind: 'send'; text: string } | { kind: 'edit'; text: string; editFrom: number } | { kind: 'regenerate' } | null;

/** Normalisasi status: ekstrak blok [[CLARIFY]] dari pesan terakhir. */
function normalizeStatus(st: ChatStatus): ChatStatus {
  const msgs: ChatMessage[] = [...(st.messages || [])];
  let clarify = st.clarify ?? null;
  if (!clarify && msgs.length) {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') {
        const { text, clarify: c } = stripClarifyBlock(msgs[i].text);
        if (c) {
          msgs[i] = { ...msgs[i], text };
          clarify = c;
        }
        break;
      }
    }
  }
  return { ...st, messages: msgs, clarify };
}

function traceLastTs(events: TraceEvent[]): number {
  let last = 0;
  for (const e of events) {
    const n = Number(e.ts);
    if (Number.isFinite(n) && n > last) last = n;
  }
  return last;
}

export function ChatApp({
  tokens,
  username,
  me,
  onLogout,
}: {
  tokens: Tokens;
  username: string;
  me: MeInfo | null;
  onLogout: (msg?: string) => void;
}) {
  const { toast } = useToast();
  const token = tokens.IdToken;

  // ---- tema ----
  const [theme, setTheme] = useState<MaaTheme>({ accent: '#DC2626', dark: false });
  useEffect(() => {
    setTheme(initTheme());
  }, []);

  // ---- data ----
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [models, setModels] = useState<MaaModel[]>([]);
  const [autoDefaults, setAutoDefaults] = useState<{ fast: string; deep: string } | undefined>(undefined);
  const [mode, setMode] = useState<ChatMode>('AUTO');
  const [manualModel, setManualModel] = useState('');
  const [loadingSession, setLoadingSession] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [errorTop, setErrorTop] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<LastAction>(null);
  const [uploads, setUploads] = useState<PendingUpload[]>([]);
  const [todos, setTodos] = useState<TodoItem[] | null>(null);

  // ---- UI ----
  const [sidebarOpen, setSidebarOpen] = useState(false); // sheet mobile
  const [traceSheetOpen, setTraceSheetOpen] = useState(false); // sheet mobile
  const [traceRailOpen, setTraceRailOpen] = useState(true); // rail desktop
  const [kbOpen, setKbOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const [confirmDismissed, setConfirmDismissed] = useState<string[]>([]);

  // ---- refs / timers ----
  const runIdRef = useRef(0);
  const lastTraceTsRef = useRef(0);
  const pollIvRef = useRef<number | null>(null);
  const traceIvRef = useRef<number | null>(null);
  const pollFailRef = useRef(0);
  const stickRef = useRef(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const idleRef = useRef<number | null>(null);

  const notify = useCallback(
    (msg: string, ok = false) => {
      toast({ description: msg, variant: ok ? undefined : 'destructive', duration: ok ? 3000 : 6000 });
    },
    [toast]
  );

  const clearTimers = useCallback(() => {
    if (pollIvRef.current) { window.clearInterval(pollIvRef.current); pollIvRef.current = null; }
    if (traceIvRef.current) { window.clearInterval(traceIvRef.current); traceIvRef.current = null; }
  }, []);

  // ---------- API helpers ----------

  const refreshSessions = useCallback(async () => {
    try {
      const r = await getSessions(token);
      setSessions((r.sessions || []).slice().sort((a, b) => {
        const ta = Date.parse(a.updatedAt || a.createdAt || '') || 0;
        const tb = Date.parse(b.updatedAt || b.createdAt || '') || 0;
        return tb - ta;
      }));
    } catch {
      /* daftar sesi gagal — tidak fatal */
    }
  }, [token]);

  const loadTrace = useCallback(
    async (run: number, sid: string, fromBeginning = false) => {
      try {
        const after = fromBeginning ? 0 : lastTraceTsRef.current;
        const r = await getTrace(token, sid, after);
        if (run !== runIdRef.current) return;
        const evs = r.events || [];
        if (evs.length) {
          setTrace((prev) => {
            const merged = fromBeginning ? evs : [...prev, ...evs];
            lastTraceTsRef.current = traceLastTs(merged);
            return merged;
          });
        }
      } catch {
        /* trace poling gagal — coba lagi di tick berikutnya */
      }
    },
    [token]
  );

  const startPolling = useCallback(
    (run: number, sid: string) => {
      clearTimers();
      setProcessing(true);
      pollFailRef.current = 0;

      const finish = () => {
        clearTimers();
        setProcessing(false);
        void loadTrace(run, sid); // fetch trace final
        void refreshSessions();
      };

      // poling status
      pollIvRef.current = window.setInterval(async () => {
        if (run !== runIdRef.current) { clearTimers(); return; }
        try {
          const st = await getStatus(token, sid);
          if (run !== runIdRef.current) return;
          pollFailRef.current = 0;
          setStatus(normalizeStatus(st));
          setTodos(st.todos ?? null);
          setErrorTop(null);
          if (st.status !== 'processing') {
            finish();
            if (st.status === 'error') {
              setErrorTop(st.err || 'Agent melaporkan error pada sesi ini.');
            }
          }
        } catch (e) {
          pollFailRef.current += 1;
          if (pollFailRef.current >= 4) {
            finish();
            setErrorTop(`Gagal memuat status sesi: ${(e as Error).message}`);
          }
        }
      }, 1200);

      // poling trace (CloudWatch)
      traceIvRef.current = window.setInterval(() => {
        if (run !== runIdRef.current) { clearTimers(); return; }
        void loadTrace(run, sid);
      }, 1500);
    },
    [clearTimers, loadTrace, refreshSessions, token]
  );

  const openSession = useCallback(
    async (sid: string, opts?: { push?: boolean }) => {
      const run = ++runIdRef.current;
      clearTimers();
      setErrorTop(null);
      setLoadingSession(true);
      setProcessing(false);
      try {
        const st = await getStatus(token, sid);
        if (run !== runIdRef.current) return;
        const norm = normalizeStatus(st);
        setStatus(norm);
        setTodos(norm.todos ?? null);
        setActiveId(sid);
        setTrace([]);
        lastTraceTsRef.current = 0;
        stickRef.current = true;
        if (opts?.push !== false) window.history.pushState({ sid }, '', `/c/${sid}`);
        if (me?.userId) saveLastSession(me.userId, sid);
        if (norm.status === 'processing') startPolling(run, sid);
        else {
          setProcessing(false);
          if (norm.status === 'error') setErrorTop(norm.err || 'Agent melaporkan error pada sesi ini.');
        }
        void loadTrace(run, sid, true);
        void refreshSessions();
      } catch (e) {
        if (run !== runIdRef.current) return;
        window.history.replaceState({}, '', '/');
        setActiveId(null);
        setStatus(null);
        setErrorTop(`Gagal membuka sesi ${sid}: ${(e as Error).message}`);
      } finally {
        if (run === runIdRef.current) setLoadingSession(false);
      }
    },
    [clearTimers, loadTrace, me?.userId, refreshSessions, startPolling, token]
  );

  const newChat = useCallback(() => {
    ++runIdRef.current;
    clearTimers();
    setActiveId(null);
    setStatus(null);
    setTrace([]);
    setTodos(null);
    setProcessing(false);
    setErrorTop(null);
    lastTraceTsRef.current = 0;
    window.history.pushState({}, '', '/');
    setSidebarOpen(false);
  }, [clearTimers]);

  // ---------- upload lampiran (multi-file, presigned S3) ----------

  const removeUpload = useCallback((key: string) => {
    setUploads((prev) => prev.filter((u) => u.key !== key));
  }, []);

  const handleFiles = useCallback(
    (files: File[]) => {
      files.slice(0, 8).forEach((file) => {
        const tempId = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const contentType = file.type || 'application/octet-stream';
        setUploads((prev) => [
          ...prev,
          { key: tempId, name: file.name, size: file.size, contentType, progress: 3 },
        ]);
        void (async () => {
          try {
            const { uploadUrl, key, headers } = await presignChatUpload(token, file.name, contentType, file.size);
            // PUT langsung ke S3 dengan progress via XHR (headers wajib dari presign)
            await new Promise<void>((resolve, reject) => {
              const xhr = new XMLHttpRequest();
              xhr.open('PUT', uploadUrl);
              Object.entries(headers || {}).forEach(([h, v]) => xhr.setRequestHeader(h, v));
              if (!headers || !Object.keys(headers).some((h) => h.toLowerCase() === 'content-type')) {
                xhr.setRequestHeader('Content-Type', contentType);
              }
              xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                  const pct = Math.round((e.loaded / e.total) * 100);
                  setUploads((prev) =>
                    prev.map((u) => (u.key === tempId ? { ...u, progress: Math.max(pct, 5) } : u))
                  );
                }
              };
              xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`S3 ${xhr.status}`)));
              xhr.onerror = () => reject(new Error('jaringan gagal'));
              xhr.send(file);
            });
            setUploads((prev) =>
              prev.map((u) => (u.key === tempId ? { ...u, key, progress: 100 } : u))
            );
          } catch (e) {
            setUploads((prev) =>
              prev.map((u) => (u.key === tempId ? { ...u, error: (e as Error).message } : u))
            );
            notify(`Upload "${file.name}" gagal: ${(e as Error).message}`);
          }
        })();
      });
    },
    [notify, token]
  );

  // ---------- translate EN -> ID ----------

  const handleTranslate = useCallback(
    async (text: string): Promise<string> => {
      const r = await translateText(token, text, activeId || undefined);
      if (r.status !== 'ok' || !r.translation) {
        throw new Error(r.message || 'translate gagal');
      }
      return r.translation;
    },
    [activeId, token]
  );

  // ---------- kirim / edit ----------

  const doSend = useCallback(
    async (text: string, editFrom?: number) => {
      if (processing) { notify('Tunggu respons agent selesai dulu.'); return; }
      const modelId = mode === 'MANUAL' && manualModel ? manualModel : undefined;
      setErrorTop(null);
      setLastAction(editFrom === undefined ? { kind: 'send', text } : { kind: 'edit', text, editFrom });

      // lampiran yang siap (progress 100, tanpa error)
      const readyUploads = editFrom === undefined ? uploads.filter((u) => u.progress >= 100 && !u.error) : [];
      const atts = readyUploads.map((u) => ({
        key: u.key,
        name: u.name,
        contentType: u.contentType,
        size: u.size,
      }));

      const run = ++runIdRef.current;
      setProcessing(true);
      stickRef.current = true;

      try {
        if (!activeId) {
          // sesi baru — tampilkan pesan user secara optimistis
          setStatus({
            sessionId: '', status: 'processing',
            messages: [
              {
                role: 'user', text, ts: Date.now(),
                atts: atts.map((a) => ({ name: a.name, kind: 'upload', size: a.size })),
              },
            ],
          });
          const r = await sendChat(token, { message: text, mode, modelId, attachments: atts });
          if (run !== runIdRef.current) return;
          setActiveId(r.sessionId);
          window.history.pushState({ sid: r.sessionId }, '', `/c/${r.sessionId}`);
          if (me?.userId) saveLastSession(me.userId, r.sessionId);
          startPolling(run, r.sessionId);
        } else {
          const sid = activeId;
          await sendChat(token, {
            message: text, mode, modelId, sessionId: sid,
            ...(atts.length ? { attachments: atts } : {}),
            ...(editFrom !== undefined ? { editFrom } : {}),
          });
          if (run !== runIdRef.current) return;
          startPolling(run, sid);
        }
        setUploads((prev) => prev.filter((u) => !readyUploads.some((r_) => r_.key === u.key)));
        setTodos((prev) => (editFrom === undefined ? [] : prev)); // rencana baru mulai kosong
      } catch (e) {
        if (run !== runIdRef.current) return;
        setProcessing(false);
        setErrorTop(`Gagal mengirim: ${(e as Error).message}`);
      }
    },
    [activeId, manualModel, me?.userId, mode, notify, processing, startPolling, token, uploads]
  );

  // ---------- regenerasi jawaban terakhir ----------

  const doRegenerate = useCallback(
    async () => {
      if (processing) { notify('Tunggu respons agent selesai dulu.'); return; }
      if (!activeId) return;
      setLastAction({ kind: 'regenerate' });
      const run = ++runIdRef.current;
      setProcessing(true);
      stickRef.current = true;
      setErrorTop(null);
      try {
        await sendChat(token, {
          message: '', mode,
          modelId: mode === 'MANUAL' && manualModel ? manualModel : undefined,
          sessionId: activeId, regenerate: true,
        });
        if (run !== runIdRef.current) return;
        startPolling(run, activeId);
      } catch (e) {
        if (run !== runIdRef.current) return;
        setProcessing(false);
        setErrorTop(`Gagal regenerate: ${(e as Error).message}`);
      }
    },
    [activeId, manualModel, mode, notify, processing, setErrorTop, startPolling, token]
  );

  const retryLast = useCallback(() => {
    if (!lastAction) return;
    if (lastAction.kind === 'edit') void doSend(lastAction.text, lastAction.editFrom);
    else if (lastAction.kind === 'regenerate') void doRegenerate();
    else void doSend(lastAction.text);
  }, [doSend, doRegenerate, lastAction]);

  // ---------- hapus sesi ----------

  const handleDeleteSession = useCallback(
    (sid: string) => {
      if (!window.confirm('Hapus sesi ini beserta seluruh riwayat percakapannya?')) return;
      void (async () => {
        try {
          await deleteSession(token, sid);
          notify('Sesi dihapus.');
          void refreshSessions();
          if (sid === activeId) newChat();
        } catch (e) {
          notify(`Gagal menghapus sesi: ${(e as Error).message}`);
        }
      })();
    },
    [activeId, newChat, notify, refreshSessions, token]
  );

  // ---------- efek awal ----------

  useEffect(() => {
    void refreshSessions();
    void (async () => {
      try {
        const r = await getModels(token);
        setModels(r.models || []);
        if (r.autoDefaults) setAutoDefaults(r.autoDefaults);
      } catch (e) {
        notify(`Gagal memuat katalog model: ${(e as Error).message}`);
      }
    })();
  }, [token, refreshSessions, notify]);

  // URL routing: buka sesi dari path saat mount, atau sesi terakhir user
  const bootRef = useRef(false);
  useEffect(() => {
    if (bootRef.current) return;
    bootRef.current = true;
    const sid = sessionIdFromPath(window.location.pathname);
    if (sid) {
      void openSession(sid, { push: false });
    } else {
      const last = me?.userId ? loadLastSession(me.userId) : null;
      if (last) void openSession(last, { push: true });
      else window.history.replaceState({}, '', '/');
    }
  }, [me?.userId]);

  // tombol back/forward browser
  useEffect(() => {
    const onPop = () => {
      const sid = sessionIdFromPath(window.location.pathname);
      if (sid) void openSession(sid, { push: false });
      else newChat();
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [openSession, newChat]);

  // ---------- idle 15 menit → logout ----------

  const doLogout = useCallback(
    async (msg?: string) => {
      clearTimers();
      try { await signOutAll(token); } catch { /* best-effort */ }
      if (tokens.RefreshToken) void revokeToken(tokens.RefreshToken);
      onLogout(msg);
    },
    [clearTimers, onLogout, token, tokens.RefreshToken]
  );

  useEffect(() => {
    const reset = () => {
      if (idleRef.current) window.clearTimeout(idleRef.current);
      idleRef.current = window.setTimeout(() => {
        void doLogout('Sesi berakhir karena idle');
      }, CONFIG.idleTimeoutMs);
    };
    reset();
    const evs: (keyof WindowEventMap)[] = ['mousedown', 'keydown', 'touchstart', 'scroll'];
    evs.forEach((ev) => window.addEventListener(ev, reset, { passive: true }));
    return () => {
      if (idleRef.current) window.clearTimeout(idleRef.current);
      evs.forEach((ev) => window.removeEventListener(ev, reset));
    };
  }, [doLogout]);

  // ---------- auto-scroll chat ----------

  const messages = status?.messages ?? [];
  useEffect(() => {
    if (stickRef.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }
  }, [messages.length, processing]);

  // ---------- turunan render ----------

  const pending = status?.pendingConfirmation || null;
  const showConfirm = !!pending && !confirmDismissed.includes(pending.confirmToken);

  const activeTitle =
    status?.title ||
    sessions.find((s) => s.sessionId === activeId)?.title ||
    (activeId ? 'Sesi' : 'Chat Baru');

  const clarify = status?.clarify && status.clarify.options?.length ? status.clarify : null;
  const attachments: Attachment[] | null =
    status?.status === 'done' && status.attachments?.length ? status.attachments : null;
  // Chip routing di bawah jawaban terakhir: prioritas status.autoRoute;
  // fallback mode→modelId dari status (spesifikasi F3 v3).
  const autoRoute: AutoRoute | null =
    status?.autoRoute ??
    (status?.status === 'done' && status.modelId
      ? { chosen: status.mode || mode, model: status.modelId, reason: undefined }
      : null);

  const sessionMenuItems = useMemo(() => sessions.slice(0, 12), [sessions]);

  const sidebarNode = (
    <SidebarContent
      sessions={sessions}
      activeId={activeId}
      onSelectSession={(id) => { setSidebarOpen(false); void openSession(id); }}
      onDeleteSession={handleDeleteSession}
      onNewChat={() => newChat()}
      onOpenDocs={() => { setSidebarOpen(false); setDocsOpen(true); }}
      onOpenKb={() => { setSidebarOpen(false); setKbOpen(true); }}
      onOpenAdmin={() => { setSidebarOpen(false); setAdminOpen(true); }}
      onOpenTheme={() => { setSidebarOpen(false); setThemeOpen(true); }}
      canAdmin={me?.role === 'superadmin'}
      userName={me?.email || username}
      onLogout={() => void doLogout()}
    />
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-[var(--bg)] text-[var(--ink)]">
      {/* ================= HEADER 56px ================= */}
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-[var(--line)] bg-[var(--bg)] px-3 sm:px-4">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Buka menu"
          className="maa-btn-ghost flex h-9 w-9 items-center justify-center lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <span className="hidden sm:block"><LogoWordmark size={22} /></span>
        <span className="sm:hidden"><Logo size={22} /></span>

        {/* chip sesi: title ▾ */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="maa-btn-ghost mx-1 flex h-9 min-w-0 max-w-[40vw] items-center gap-1.5 border border-[var(--line-soft)] px-3 sm:max-w-[320px]"
              aria-label="Ganti sesi"
            >
              <span className="truncate text-[12.5px] font-medium">{activeTitle}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--muted-fg)]" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-72">
            <DropdownMenuLabel className="text-[11px] uppercase tracking-widest text-[var(--muted-fg)]">
              Sesi terbaru
            </DropdownMenuLabel>
            <DropdownMenuItem onSelect={newChat}>
              <MessageSquarePlus className="h-4 w-4" /> Chat Baru
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {sessionMenuItems.length === 0 && (
              <p className="px-2 py-3 text-center text-[11.5px] text-[var(--muted-fg)]">Belum ada sesi</p>
            )}
            {sessionMenuItems.map((s) => (
              <DropdownMenuItem
                key={s.sessionId}
                onSelect={() => void openSession(s.sessionId)}
                className={s.sessionId === activeId ? 'bg-[var(--accent-soft)]' : ''}
              >
                <span className="min-w-0 flex-1 truncate text-[12.5px]">{s.title || 'Sesi tanpa judul'}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <span className="ml-auto" />

        {/* mode aktif kecil di header (desktop) */}
        <span className="hidden rounded-full border border-[var(--line-soft)] px-2.5 py-1 font-mono text-[10px] font-semibold text-[var(--muted-fg)] md:inline">
          {mode}
        </span>

        <ThemeSwitcher theme={theme} onChange={setTheme} />

        {/* toggle trace rail desktop */}
        <button
          type="button"
          onClick={() => setTraceRailOpen((v) => !v)}
          aria-label={traceRailOpen ? 'Sembunyikan Live Trace' : 'Tampilkan Live Trace'}
          title="Live Trace"
          className="maa-btn-ghost hidden h-9 w-9 items-center justify-center lg:flex"
        >
          {traceRailOpen ? <PanelRightClose className="h-4.5 w-4.5" /> : <PanelRightOpen className="h-4.5 w-4.5" />}
        </button>
        {/* trace sheet mobile */}
        <button
          type="button"
          onClick={() => setTraceSheetOpen(true)}
          aria-label="Buka Live Trace"
          className="maa-btn-ghost flex h-9 w-9 items-center justify-center lg:hidden"
        >
          <Activity className="h-4.5 w-4.5" />
        </button>

        {/* user menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Menu pengguna"
              className="maa-btn-ghost flex h-9 items-center gap-2 px-2"
            >
              <span
                className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-[var(--accent-ink)]"
                style={{ background: 'var(--accent)' }}
              >
                {(me?.username || username || '?').slice(0, 2).toUpperCase()}
              </span>
              <span className="hidden max-w-[140px] truncate text-[12px] font-medium md:inline">
                {me?.username || username}
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel>
              <span className="block truncate text-[12.5px] font-semibold text-[var(--ink)]">
                {me?.email || username}
              </span>
              <span className="mt-0.5 flex items-center gap-1 text-[10.5px] font-medium text-[var(--muted-fg)]">
                {me?.role === 'superadmin' ? (
                  <>
                    <ShieldCheck className="h-3 w-3" style={{ color: 'var(--accent)' }} /> superadmin
                  </>
                ) : (
                  'user'
                )}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void doLogout()} className="text-[var(--danger)]">
              <LogOut className="h-4 w-4" /> Keluar
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      {/* ================= BODY 3 KOLOM ================= */}
      <div className="flex min-h-0 flex-1">
        {/* sidebar desktop */}
        <aside className="hidden w-[264px] shrink-0 border-r border-[var(--line)] lg:block">
          {sidebarNode}
        </aside>

        {/* chat area */}
        <main className="flex min-w-0 flex-1 flex-col">
          {errorTop && (
            <div
              role="alert"
              className="animate-slide-down mx-3 mt-3 flex items-start gap-2.5 rounded-[10px] border border-[var(--danger)] bg-[var(--danger)]/5 px-3.5 py-2.5 sm:mx-4"
            >
              <X className="mt-0.5 h-4 w-4 shrink-0 text-[var(--danger)]" />
              <p className="min-w-0 flex-1 break-words text-[12.5px] leading-relaxed text-[var(--ink)]">{errorTop}</p>
              <button
                type="button"
                onClick={retryLast}
                className="maa-btn-secondary flex shrink-0 items-center gap-1.5 px-2.5 py-1.5 text-[11.5px]"
              >
                <RefreshCcw className="h-3.5 w-3.5" /> Coba lagi
              </button>
              <button
                type="button"
                onClick={() => setErrorTop(null)}
                aria-label="Tutup pesan error"
                className="rounded-md p-1 text-[var(--muted-fg)] hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          <div
            ref={scrollRef}
            onScroll={(e) => {
              const el = e.currentTarget;
              stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            }}
            className="nice-scroll min-h-0 flex-1 overflow-y-auto"
          >
            <div className="mx-auto w-full max-w-[760px] px-4 py-6">
              {loadingSession && messages.length === 0 ? (
                <div className="space-y-4">
                  <div className="skeleton-line h-16 w-3/4 rounded-[10px]" />
                  <div className="skeleton-line h-24 w-full rounded-[10px]" />
                  <div className="skeleton-line h-16 w-2/3 rounded-[10px]" />
                </div>
              ) : messages.length === 0 ? (
                /* ---------- empty state ---------- */
                <div className="flex flex-col items-center py-10 text-center sm:py-16">
                  <Logo size={56} className="mb-4" />
                  <h2 className="text-[20px] font-bold tracking-tight text-[var(--ink)]">
                    Halo, {me?.username || username}
                  </h2>
                  <p className="mt-1.5 max-w-[420px] text-[13px] leading-relaxed text-[var(--muted-fg)]">
                    Insinyur AWS otonom Anda. Tanyakan apa saja — dari listing resource sampai
                    operasi destruktif (dengan konfirmasi ganda).
                  </p>
                  <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => void doSend(s)}
                        className="maa-btn-secondary flex items-center gap-1.5 px-3.5 py-2 text-[12px]"
                      >
                        <Sparkles className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} />
                        {s}
                      </button>
                    ))}
                  </div>
                  {mode === 'MANUAL' && !manualModel && (
                    <p className="mt-4 text-[11.5px] text-[var(--muted-fg)]">
                      Mode MANUAL aktif — pilih model dulu di atas composer.
                    </p>
                  )}
                </div>
              ) : (
                <>
                  {(todos?.length || (processing && todos?.length)) ? <TodoPanel todos={todos} /> : null}
                  <MessageList
                    messages={messages}
                    processing={processing}
                    onResendEdit={(idx, text) => void doSend(text, idx)}
                    notify={notify}
                    onRegenerate={activeId ? () => void doRegenerate() : undefined}
                    onTranslate={handleTranslate}
                    clarifySlot={
                    clarify && !processing ? (
                      <div className="animate-msg-in mt-1 w-full max-w-[min(680px,85%)] rounded-[10px] border border-[var(--accent)] bg-[var(--accent-soft)] p-3.5">
                        <p className="mb-2.5 text-[13px] font-semibold leading-relaxed text-[var(--ink)]">
                          {clarify.question}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {clarify.options.map((opt) => (
                            <button
                              key={opt}
                              type="button"
                              disabled={processing}
                              onClick={() => void doSend(opt)}
                              className="rounded-full border border-[var(--line)] bg-[var(--bg)] px-3 py-1.5 text-[12px] font-medium text-[var(--ink)] transition-colors hover:border-[var(--accent)] disabled:opacity-50"
                            >
                              {opt}
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : undefined
                  }
                    attachments={attachments}
                    autoRoute={autoRoute}
                  />
                </>
              )}
            </div>
          </div>

          {/* composer */}
          <div className="shrink-0 border-t border-[var(--line)] bg-[var(--bg)] px-3 pb-3 pt-3 sm:px-4">
            <div className="mx-auto w-full max-w-[760px]">
              <Composer
                mode={mode}
                onModeChange={setMode}
                manualModel={manualModel}
                onManualModelChange={setManualModel}
                models={models}
                autoDefaults={autoDefaults}
                onSend={(t) => void doSend(t)}
                onFiles={handleFiles}
                uploads={uploads}
                onRemoveUpload={removeUpload}
                disabled={loadingSession}
                busy={processing}
                hint={
                  mode === 'AUTO' && autoDefaults
                    ? `AUTO memilih model otomatis · cepat: ${autoDefaults.fast} · dalam: ${autoDefaults.deep}`
                    : null
                }
              />
            </div>
          </div>
        </main>

        {/* trace rail desktop */}
        {traceRailOpen && (
          <aside className="hidden w-[340px] shrink-0 border-l border-[var(--line)] bg-[var(--bg)] lg:block">
            <TracePanel
              events={trace}
              processing={processing}
              onClear={() => setTrace([])}
            />
          </aside>
        )}
      </div>

      {/* ================= sheets & drawers ================= */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-[280px] gap-0 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Menu</SheetTitle>
          </SheetHeader>
          {sidebarNode}
        </SheetContent>
      </Sheet>

      <Sheet open={traceSheetOpen} onOpenChange={setTraceSheetOpen}>
        <SheetContent side="right" className="w-full max-w-md gap-0 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Live Trace</SheetTitle>
          </SheetHeader>
          <div className="h-full pt-10">
            <TracePanel
              events={trace}
              processing={processing}
              onClear={() => setTrace([])}
              onClose={() => setTraceSheetOpen(false)}
            />
          </div>
        </SheetContent>
      </Sheet>

      <KbDrawer open={kbOpen} onOpenChange={setKbOpen} token={token} notify={notify} />
      <DocsDrawer
        open={docsOpen}
        onOpenChange={setDocsOpen}
        token={token}
        isSuperadmin={me?.role === 'superadmin'}
        notify={notify}
      />
      <AdminDrawer open={adminOpen} onOpenChange={setAdminOpen} token={token} notify={notify} />
      <ThemeDialog theme={theme} onChange={setTheme} open={themeOpen} onOpenChange={setThemeOpen} />

      {showConfirm && pending && activeId && (
        <ConfirmModal
          pending={pending}
          sessionId={activeId}
          token={token}
          notify={notify}
          onDone={() => {
            setConfirmDismissed((prev) => [...prev, pending.confirmToken]);
            const run = ++runIdRef.current;
            clearTimers();
            setProcessing(true);
            startPolling(run, activeId);
          }}
          onCancel={() => {
            setConfirmDismissed((prev) => [...prev, pending.confirmToken]);
            notify('Konfirmasi dibatalkan — operasi destruktif tidak dieksekusi.');
          }}
        />
      )}
    </div>
  );
}
