'use client';

import { useEffect, useRef, useState } from 'react';
import {
  ArrowUp, Brain, Check, Clapperboard, Code2, Gauge, ListTodo, Loader2,
  Paperclip, Route, SlidersHorizontal, Sparkles, Timer, Users, X, Zap,
} from 'lucide-react';
import type { AgentMode, ChatMode, MaaModel } from '@/lib/maa';
import { fmtBytes } from '@/lib/maa';
import { ModelPicker } from './model-picker';

/** Mode pemilihan model — hanya 4 (routing model). */
const MODES: { id: ChatMode; label: string; icon: React.ReactNode }[] = [
  { id: 'AUTO', label: 'AUTO', icon: <Route className="h-3.5 w-3.5" /> },
  { id: 'FAST', label: 'FAST', icon: <Gauge className="h-3.5 w-3.5" /> },
  { id: 'DEEP', label: 'DEEP', icon: <Brain className="h-3.5 w-3.5" /> },
  { id: 'MANUAL', label: 'MANUAL', icon: <SlidersHorizontal className="h-3.5 w-3.5" /> },
];

/** Mode tugas agent — gaya kerja, TERPISAH dari pemilihan model. */
const AGENT_MODES: { id: AgentMode; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: 'STANDARD', label: 'Standar', icon: <Sparkles className="h-4 w-4" />, desc: 'Percakapan normal — jawaban cepat dan langsung' },
  { id: 'LONG', label: 'Tugas Panjang', icon: <Timer className="h-4 w-4" />, desc: 'Long-running task besar multi-langkah dengan todo list live (24 iterasi)' },
  { id: 'FULLSTACK', label: 'Full-Stack', icon: <Code2 className="h-4 w-4" />, desc: 'Bangun aplikasi web lengkap + URL preview langsung' },
  { id: 'PRESENTATION', label: 'Presentasi', icon: <Clapperboard className="h-4 w-4" />, desc: 'Susun slide deck profesional otomatis' },
  { id: 'TODO', label: 'Todo List', icon: <ListTodo className="h-4 w-4" />, desc: 'Rencana langkah tampil sebagai checklist live yang diperbarui agent' },
  { id: 'MULTI', label: 'Multi-Agent', icon: <Users className="h-4 w-4" />, desc: 'Delegasi ke subagent spesialis (riset, arsitek, coder, reviewer) lalu sintesis' },
];

const MAX_H = 5 * 24 + 16; // ±5 baris
const MAX_FILE_MB = 200;

export type PendingUpload = {
  key: string;
  name: string;
  size: number;
  contentType: string;
  progress: number; // 0..100
  error?: string;
};

export function Composer({
  mode,
  onModeChange,
  agentMode,
  onAgentModeChange,
  manualModel,
  onManualModelChange,
  models,
  autoDefaults,
  onSend,
  onFiles,
  uploads,
  onRemoveUpload,
  disabled,
  busy,
  placeholder = 'Tanya apa saja tentang AWS Anda…',
}: {
  mode: ChatMode;
  onModeChange: (m: ChatMode) => void;
  agentMode: AgentMode;
  onAgentModeChange: (m: AgentMode) => void;
  manualModel: string;
  onManualModelChange: (id: string) => void;
  models: MaaModel[];
  autoDefaults?: { fast: string; deep: string };
  onSend: (text: string) => void;
  onFiles?: (files: File[]) => void;
  uploads?: PendingUpload[];
  onRemoveUpload?: (key: string) => void;
  disabled?: boolean;
  busy?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const [agentOpen, setAgentOpen] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const agentRef = useRef<HTMLDivElement>(null);

  // auto-grow
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_H)}px`;
  }, [text]);

  // tutup popover mode tugas saat klik di luar
  useEffect(() => {
    if (!agentOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (agentRef.current && !agentRef.current.contains(e.target as Node)) setAgentOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [agentOpen]);

  const uploadsReady = (uploads || []).filter((u) => !u.error && u.progress >= 100);
  const uploadingNow = (uploads || []).some((u) => u.progress < 100 && !u.error);
  const canSend = !!text.trim() && !disabled && !busy && !uploadingNow;

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText('');
    requestAnimationFrame(() => taRef.current?.focus());
  };

  const pickFiles = () => fileRef.current?.click();

  const handleFiles = (list: FileList | null) => {
    if (!list || !onFiles) return;
    const files = Array.from(list);
    const bad = files.filter((f) => f.size > MAX_FILE_MB * 1024 * 1024);
    if (bad.length) {
      alert(`File terlalu besar (maks ${MAX_FILE_MB} MB): ${bad.map((b) => b.name).join(', ')}`);
    }
    const ok = files.filter((f) => f.size <= MAX_FILE_MB * 1024 * 1024);
    if (ok.length) onFiles(ok);
    if (fileRef.current) fileRef.current.value = '';
  };

  const activeAgent = AGENT_MODES.find((m) => m.id === agentMode) || AGENT_MODES[0];

  return (
    <div className="w-full">
      {/* baris mode: routing model + mode tugas agent */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="Mode model">
          {MODES.map((m) => {
            const active = m.id === mode;
            return (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={disabled}
                onClick={() => onModeChange(m.id)}
                className={`flex h-8 items-center gap-1.5 rounded-full border px-3 text-[11.5px] font-semibold tracking-wide transition-colors disabled:opacity-50 ${
                  active
                    ? 'border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-ink)]'
                    : 'border-[var(--line-soft)] bg-[var(--bg)] text-[var(--muted-fg)] hover:border-[var(--line)] hover:text-[var(--ink)]'
                }`}
              >
                {m.icon}
                {m.label}
              </button>
            );
          })}
        </div>

        {mode === 'MANUAL' && (
          <ModelPicker
            models={models}
            value={manualModel}
            onChange={onManualModelChange}
            disabled={disabled}
            autoDefaults={autoDefaults}
          />
        )}

        {/* mode tugas agent: dropdown ringkas ala toolbar */}
        <div className="relative ml-auto" ref={agentRef}>
          <button
            type="button"
            disabled={disabled}
            onClick={() => setAgentOpen((v) => !v)}
            aria-haspopup="listbox"
            aria-expanded={agentOpen}
            title="Mode tugas agent (gaya kerja)"
            className={`flex h-8 items-center gap-1.5 rounded-full border px-3 text-[11.5px] font-semibold transition-colors disabled:opacity-50 ${
              agentMode !== 'STANDARD'
                ? 'border-[var(--accent)] text-[var(--accent)]'
                : 'border-[var(--line-soft)] bg-[var(--bg)] text-[var(--muted-fg)] hover:border-[var(--line)] hover:text-[var(--ink)]'
            }`}
          >
            <span className="inline-flex h-3.5 w-3.5 items-center justify-center">{activeAgent.icon}</span>
            {activeAgent.label}
            <Zap className="h-3 w-3 opacity-60" />
          </button>
          {agentOpen && (
            <div
              role="listbox"
              aria-label="Mode tugas agent"
              className="maa-panel absolute bottom-10 right-0 z-40 w-[290px] p-1.5 shadow-[var(--shadow-soft)]"
            >
              <p className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
                Mode tugas agent
              </p>
              {AGENT_MODES.map((m) => {
                const active = m.id === agentMode;
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => {
                      onAgentModeChange(m.id);
                      setAgentOpen(false);
                    }}
                    className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-[var(--muted-bg)] ${
                      active ? 'bg-[var(--accent-soft)]' : ''
                    }`}
                  >
                    <span className="mt-0.5 shrink-0" style={{ color: active ? 'var(--accent)' : 'var(--muted-fg)' }}>
                      {m.icon}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-[var(--ink)]">
                        {m.label}
                        {active && <Check className="h-3 w-3" style={{ color: 'var(--accent)' }} />}
                      </span>
                      <span className="mt-0.5 block text-[10.5px] leading-snug text-[var(--muted-fg)]">{m.desc}</span>
                    </span>
                  </button>
                );
              })}
              <p className="mt-1 border-t border-[var(--line-soft)] px-2.5 py-1.5 text-[9.5px] leading-relaxed text-[var(--muted-fg)]">
                Mode tugas menentukan <em>cara kerja</em> agent; pemilihan model tetap lewat AUTO/FAST/DEEP/MANUAL.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* chips lampiran yang sedang diunggah / siap kirim */}
      {!!uploads?.length && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {uploads.map((u) => (
            <span
              key={u.key}
              className={`flex max-w-[240px] items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${
                u.error
                  ? 'border-[var(--danger)] bg-[var(--danger)]/5 text-[var(--danger)]'
                  : 'border-[var(--line)] bg-[var(--surface)] text-[var(--ink)]'
              }`}
              title={u.error || u.name}
            >
              {u.progress < 100 ? (
                <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
              ) : (
                <Paperclip className="h-3 w-3 shrink-0" />
              )}
              <span className="truncate">{u.name}</span>
              <span className="shrink-0 font-mono text-[9.5px] text-[var(--muted-fg)]">
                {u.error ? 'gagal' : u.progress < 100 ? `${u.progress}%` : fmtBytes(u.size)}
              </span>
              <button
                type="button"
                aria-label={`Batalkan ${u.name}`}
                onClick={() => onRemoveUpload?.(u.key)}
                className="rounded-full p-0.5 hover:bg-[var(--muted-bg)]"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* input besar bergaris */}
      <div
        onDragOver={(e) => {
          if (onFiles) e.preventDefault();
        }}
        onDrop={(e) => {
          if (!onFiles) return;
          e.preventDefault();
          handleFiles(e.dataTransfer.files);
        }}
        className={`maa-panel flex items-end gap-2 p-2 transition-shadow focus-within:shadow-[0_0_0_1px_var(--accent)] ${
          disabled ? 'opacity-70' : ''
        }`}
      >
        {onFiles && (
          <>
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
            <button
              type="button"
              onClick={pickFiles}
              disabled={disabled}
              aria-label="Lampirkan file"
              title="Lampirkan file (banyak file, maks 200 MB/file) — atau tarik-lepas di sini"
              className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] text-[var(--muted-fg)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
            >
              <Paperclip className="h-4 w-4" />
            </button>
          </>
        )}
        <textarea
          ref={taRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="Pesan untuk agent"
          className="nice-scroll max-h-[136px] min-h-[40px] w-full resize-none bg-transparent px-2.5 py-2 text-[14px] leading-relaxed text-[var(--ink)] outline-none placeholder:text-[var(--muted-fg)] disabled:cursor-not-allowed"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          aria-label="Kirim pesan"
          className="maa-btn-primary mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center"
        >
          {busy || uploadingNow ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4.5 w-4.5" />}
        </button>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center justify-end gap-x-3 gap-y-1 px-1">
        <p className="text-[10.5px] text-[var(--muted-fg)]">
          <kbd className="font-mono">Enter</kbd> kirim · <kbd className="font-mono">Shift+Enter</kbd> baris baru
        </p>
      </div>
    </div>
  );
}
