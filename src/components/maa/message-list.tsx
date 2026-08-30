'use client';

import { useMemo, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Copy, Image as ImageIcon, Pencil, RefreshCcw, X } from 'lucide-react';
import type { Attachment, AutoRoute, ChatMessage } from '@/lib/maa';
import { fmtClock } from '@/lib/maa';
import { Markdown } from './markdown';

function useCopy(notify: (msg: string) => void) {
  return (text: string) => {
    navigator.clipboard
      ?.writeText(text)
      .then(() => notify('Tersalin'))
      .catch(() => notify('Gagal menyalin'));
  };
}

/* ---------------- bubble pengguna (edit inline ala ChatGPT) ---------------- */

function UserBubble({
  msg,
  index,
  onResendEdit,
  notify,
}: {
  msg: ChatMessage;
  index: number;
  onResendEdit: (index: number, text: string) => void;
  notify: (msg: string) => void;
}) {
  const copy = useCopy(notify);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const startEdit = () => {
    setDraft(msg.text);
    setEditing(true);
  };

  if (editing) {
    return (
      <div className="animate-msg-in flex justify-end">
        <div className="w-full max-w-[min(680px,85%)] rounded-[10px] border border-[var(--accent)] bg-[var(--bg)] p-2.5 shadow-[var(--shadow-soft)]">
          <textarea
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (draft.trim()) { setEditing(false); onResendEdit(index, draft.trim()); }
              }
              if (e.key === 'Escape') setEditing(false);
            }}
            rows={Math.min(6, draft.split('\n').length + 1)}
            className="nice-scroll w-full resize-none rounded-lg border border-[var(--line-soft)] bg-[var(--surface)] px-3 py-2 text-[14px] leading-relaxed text-[var(--ink)] outline-none focus:border-[var(--accent)]"
            aria-label="Ubah pesan"
          />
          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="maa-btn-ghost px-3 py-1.5 text-[12px] font-medium"
            >
              Batal
            </button>
            <button
              type="button"
              disabled={!draft.trim() || draft === msg.text}
              onClick={() => { setEditing(false); onResendEdit(index, draft.trim()); }}
              className="maa-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[12px]"
            >
              <RefreshCcw className="h-3.5 w-3.5" /> Kirim ulang
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-msg-in group flex justify-end">
      <div className="flex max-w-[min(680px,85%)] items-end gap-1.5">
        <div className="flex flex-col items-end gap-1">
          <div className="rounded-[10px] border border-[var(--line)] bg-[var(--accent-soft)] px-3.5 py-2.5 text-[14px] leading-relaxed break-words whitespace-pre-wrap text-[var(--ink)] shadow-[var(--shadow-soft)]">
            {msg.text}
          </div>
          <div className="flex items-center gap-1 pr-0.5 text-[10px] text-[var(--muted-fg)]">
            {msg.edited && <span className="rounded-full bg-[var(--muted-bg)] px-1.5 py-px font-medium">diedit</span>}
            <span className="font-mono">{fmtClock(msg.ts)}</span>
            <span className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
              <button
                type="button"
                onClick={() => copy(msg.text)}
                aria-label="Salin pesan"
                title="Salin"
                className="rounded p-1 hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
              >
                <Copy className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={startEdit}
                aria-label="Edit pesan"
                title="Edit & kirim ulang"
                className="rounded p-1 hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
              >
                <Pencil className="h-3 w-3" />
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------- bubble asisten (versioning + copy + meta chip) ------------- */

function AssistantBubble({
  msg,
  isLast,
  notify,
  routeChip,
}: {
  msg: ChatMessage;
  isLast: boolean;
  notify: (msg: string) => void;
  routeChip?: React.ReactNode;
}) {
  const copy = useCopy(notify);

  // Kandidat versi: versions[] (lama) + teks aktif (terbaru). Dedupe bila
  // server sudah memasukkan teks aktif sebagai elemen terakhir versions.
  const candidates = useMemo(() => {
    const list: { text: string; ts: number; model?: string }[] = (msg.versions || []).map((v) => ({
      text: v.text, ts: v.ts, model: v.model,
    }));
    if (!list.length || list[list.length - 1].text !== msg.text) {
      list.push({ text: msg.text, ts: msg.ts, model: msg.model });
    }
    return list;
  }, [msg]);

  const [cursor, setCursor] = useState(candidates.length - 1);
  const cur = Math.min(cursor, candidates.length - 1);
  const active = candidates[cur] || { text: msg.text, ts: msg.ts, model: msg.model };
  const many = candidates.length > 1;

  return (
    <div className="animate-msg-in group flex justify-start">
      <div className="flex w-full max-w-[min(680px,85%)] flex-col items-start gap-1">
        <div className="w-full rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3.5 py-2.5 shadow-[var(--shadow-soft)]">
          <Markdown text={active.text} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 pl-0.5 text-[10px] text-[var(--muted-fg)]">
          <span className="font-mono">{fmtClock(active.ts)}</span>
          {many && (
            <span className="flex items-center gap-0.5 rounded-full border border-[var(--line-soft)] bg-[var(--bg)] px-1 py-px">
              <button
                type="button"
                aria-label="Versi sebelumnya"
                disabled={cur === 0}
                onClick={() => setCursor((c) => Math.max(0, c - 1))}
                className="rounded p-0.5 hover:bg-[var(--muted-bg)] disabled:opacity-30"
              >
                <ChevronLeft className="h-3 w-3" />
              </button>
              <span className="font-mono text-[10px] text-[var(--ink)]">
                {cur + 1}/{candidates.length}
              </span>
              <button
                type="button"
                aria-label="Versi berikutnya"
                disabled={cur === candidates.length - 1}
                onClick={() => setCursor((c) => Math.min(candidates.length - 1, c + 1))}
                className="rounded p-0.5 hover:bg-[var(--muted-bg)] disabled:opacity-30"
              >
                <ChevronRight className="h-3 w-3" />
              </button>
            </span>
          )}
          {active.model && (
            <span className="max-w-[220px] truncate rounded-full border border-[var(--line-soft)] bg-[var(--bg)] px-1.5 py-px font-mono text-[9.5px]">
              {active.model}
            </span>
          )}
          <button
            type="button"
            onClick={() => copy(active.text)}
            aria-label="Salin jawaban"
            title="Salin (markdown mentah)"
            className="rounded p-1 hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
          >
            <Copy className="h-3 w-3" />
          </button>
        </div>
        {isLast && routeChip}
      </div>
    </div>
  );
}

/* --------------------------- skeleton loading --------------------------- */

function AssistantSkeleton() {
  return (
    <div className="flex justify-start" aria-label="Agent sedang menjawab">
      <div className="w-full max-w-[min(680px,85%)] rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] px-3.5 py-3 shadow-[var(--shadow-soft)]">
        <div className="space-y-2">
          <div className="skeleton-line h-3 w-3/4 rounded-full" />
          <div className="skeleton-line h-3 w-full rounded-full" />
          <div className="skeleton-line h-3 w-5/6 rounded-full" />
        </div>
        <p className="mt-2.5 flex items-center gap-1.5 text-[10.5px] text-[var(--muted-fg)]">
          <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full" style={{ background: 'var(--accent)' }} />
          Agent sedang bekerja…
        </p>
      </div>
    </div>
  );
}

/* ------------------------------ attachments ------------------------------ */

function AttachmentGallery({ attachments }: { attachments: Attachment[] }) {
  const images = attachments.filter((a) => (a.type || '').startsWith('image') || /\.(png|jpe?g|gif|webp|svg)$/i.test(a.url || ''));
  if (!images.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {images.map((a, i) => (
        <a
          key={i}
          href={a.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group relative block overflow-hidden rounded-[10px] border border-[var(--line)]"
          title={a.name || 'Lampiran gambar'}
        >
          <img
            src={a.url}
            alt={a.name || 'Lampiran'}
            className="h-28 w-40 object-cover transition-transform group-hover:scale-[1.03]"
            loading="lazy"
          />
          <span className="absolute inset-x-0 bottom-0 flex items-center gap-1 bg-black/55 px-2 py-1 text-[9.5px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100">
            <ImageIcon className="h-3 w-3" />
            <span className="truncate">{a.name || 'buka gambar'}</span>
          </span>
        </a>
      ))}
    </div>
  );
}

/* --------------------------------- list --------------------------------- */

export function MessageList({
  messages,
  processing,
  onResendEdit,
  notify,
  clarifySlot,
  attachments,
  autoRoute,
  showSkeleton,
}: {
  messages: ChatMessage[];
  processing: boolean;
  onResendEdit: (index: number, text: string) => void;
  notify: (msg: string) => void;
  clarifySlot?: React.ReactNode;
  attachments?: Attachment[] | null;
  autoRoute?: AutoRoute | null;
  showSkeleton?: boolean;
}) {
  const lastAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === 'assistant') return i;
    return -1;
  }, [messages]);

  const routeChip = (() => {
    if (!autoRoute) return null;
    const { chosen, model, reason } = autoRoute;
    return (
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 rounded-full border border-[var(--line)] bg-[var(--bg)] px-2 py-0.5 text-[10px] font-semibold text-[var(--ink)]">
          {chosen} <span className="text-[var(--muted-fg)]">→</span>{' '}
          <span className="font-mono text-[9.5px] font-medium">{model}</span>
        </span>
        {reason && <span className="text-[10px] italic text-[var(--muted-fg)]">— {reason}</span>}
      </div>
    );
  })();

  return (
    <div className="space-y-4">
      {messages.map((m, i) =>
        m.role === 'user' ? (
          <UserBubble key={`${m.ts}-${i}`} msg={m} index={i} onResendEdit={onResendEdit} notify={notify} />
        ) : (
          <AssistantBubble
            key={`${m.ts}-${i}`}
            msg={m}
            isLast={i === lastAssistant}
            notify={notify}
            routeChip={i === lastAssistant ? routeChip : undefined}
          />
        )
      )}

      {processing && showSkeleton !== false && <AssistantSkeleton />}

      {/* chips klarifikasi + galeri lampiran untuk jawaban terbaru */}
      {clarifySlot}
      {attachments && <AttachmentGallery attachments={attachments} />}
    </div>
  );
}
