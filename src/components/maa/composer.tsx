'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Brain, Gauge, Loader2, Route, SlidersHorizontal } from 'lucide-react';
import type { ChatMode, MaaModel } from '@/lib/maa';
import { ModelPicker } from './model-picker';

const MODES: { id: ChatMode; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'AUTO', label: 'AUTO', icon: <Route className="h-3.5 w-3.5" />, hint: 'Model dipilih otomatis sesuai kompleksitas' },
  { id: 'FAST', label: 'FAST', icon: <Gauge className="h-3.5 w-3.5" />, hint: 'Balasan cepat & hemat' },
  { id: 'DEEP', label: 'DEEP', icon: <Brain className="h-3.5 w-3.5" />, hint: 'Reasoning untuk soal kompleks' },
  { id: 'MANUAL', label: 'MANUAL', icon: <SlidersHorizontal className="h-3.5 w-3.5" />, hint: 'Anda pilih modelnya sendiri' },
];

const MAX_H = 5 * 24 + 16; // ±5 baris

export function Composer({
  mode,
  onModeChange,
  manualModel,
  onManualModelChange,
  models,
  autoDefaults,
  onSend,
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
  disabled?: boolean;
  busy?: boolean;
  hint?: string | null;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const taRef = useRef<HTMLTextAreaElement>(null);

  // auto-grow
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_H)}px`;
  }, [text]);

  const canSend = !!text.trim() && !disabled && !busy;

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText('');
    requestAnimationFrame(() => taRef.current?.focus());
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

      {/* input besar bergaris */}
      <div
        className={`maa-panel flex items-end gap-2 p-2 transition-shadow focus-within:shadow-[0_0_0_1px_var(--accent)] ${
          disabled ? 'opacity-70' : ''
        }`}
      >
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
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4.5 w-4.5" />}
        </button>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-1">
        <p className="text-[10.5px] text-[var(--muted-fg)]">{hintLine}</p>
        <p className="hidden text-[10.5px] text-[var(--muted-fg)] sm:block">
          <kbd className="font-mono">Enter</kbd> kirim · <kbd className="font-mono">Shift+Enter</kbd> baris baru
        </p>
      </div>
    </div>
  );
}
