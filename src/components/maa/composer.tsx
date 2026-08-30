'use client';

import { useEffect, useRef, useState } from 'react';
import {
  ArrowUp, Brain, Clapperboard, Code2, Eye, EyeOff, Gauge, Loader2, Paperclip,
  Route, SlidersHorizontal, Timer, X,
} from 'lucide-react';
import type { ChatMode, MaaModel } from '@/lib/maa';
import { fmtBytes } from '@/lib/maa';
import { ModelPicker } from './model-picker';

const MODES: { id: ChatMode; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'AUTO', label: 'AUTO', icon: <Route className="h-3.5 w-3.5" />, hint: 'Model dipilih otomatis sesuai kompleksitas' },
  { id: 'FAST', label: 'FAST', icon: <Gauge className="h-3.5 w-3.5" />, hint: 'Balasan cepat & hemat' },
  { id: 'DEEP', label: 'DEEP', icon: <Brain className="h-3.5 w-3.5" />, hint: 'Reasoning untuk soal kompleks' },
  { id: 'LONG', label: 'LONG', icon: <Timer className="h-3.5 w-3.5" />, hint: 'Tugas besar multi-langkah + todo list live' },
  { id: 'FULLSTACK', label: 'FULLSTACK', icon: <Code2 className="h-3.5 w-3.5" />, hint: 'Bangun aplikasi web lengkap + preview URL' },
  { id: 'PRESENTATION', label: 'PRESENT', icon: <Clapperboard className="h-3.5 w-3.5" />, hint: 'Susun slide deck profesional otomatis' },
  { id: 'MANUAL', label: 'MANUAL', icon: <SlidersHorizontal className="h-3.5 w-3.5" />, hint: 'Anda pilih modelnya sendiri' },
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
  hint,
  placeholder = 'Tanya apa saja tentang AWS Anda…',
}: {
  mode: ChatMode;
  onModeChange: (m: ChatMode) => void;
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
  hint?: string | null;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const [showHints, setShowHints] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // auto-grow
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_H)}px`;
  }, [text]);

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

  const activeMode = MODES.find((m) => m.id === mode)!;
  const hintLine =
    hint ||
    (mode === 'MANUAL'
      ? manualModel
        ? 'Model dipilih manual — jalankan tool hanya pada model berbadge "tools"'
        : 'Pilih model dulu untuk mode MANUAL'
      : activeMode.hint);

  return (
    <div className="w-full">
      {/* pilihan mode */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="Mode agent">
        {MODES.map((m) => {
          const active = m.id === mode;
          return (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={active}
              title={m.hint}
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

        {mode === 'MANUAL' && (
          <ModelPicker
            models={models}
            value={manualModel}
            onChange={onManualModelChange}
            disabled={disabled}
            autoDefaults={autoDefaults}
          />
        )}
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

      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-1">
        <p className="flex items-center gap-1.5 text-[10.5px] text-[var(--muted-fg)]">
          {hintLine}
          <button
            type="button"
            onClick={() => setShowHints((v) => !v)}
            className="inline-flex items-center gap-0.5 rounded px-1 hover:text-[var(--ink)]"
            aria-expanded={showHints}
          >
            {showHints ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
            contoh
          </button>
        </p>
        <p className="hidden text-[10.5px] text-[var(--muted-fg)] sm:block">
          <kbd className="font-mono">Enter</kbd> kirim · <kbd className="font-mono">Shift+Enter</kbd> baris baru
        </p>
      </div>
      {showHints && (
        <div className="mt-1.5 flex flex-wrap gap-1.5 px-1">
          {[
            'Kamu bisa apa?',
            'Analisis CSV ini lalu buat chart',
            'Buatkan dashboard monitoring (FULLSTACK)',
            'Buat deck presentasi biaya AWS (PRESENT)',
            'Riset harga terbaru EC2 lalu rekomendasikan (LONG)',
          ].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setText(s);
                taRef.current?.focus();
              }}
              className="rounded-full border border-[var(--line-soft)] bg-[var(--surface)] px-2.5 py-1 text-[10.5px] text-[var(--muted-fg)] transition-colors hover:border-[var(--accent)] hover:text-[var(--ink)]"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
