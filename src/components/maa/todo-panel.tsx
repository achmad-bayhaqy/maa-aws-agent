'use client';

import { useMemo } from 'react';
import { CheckCircle2, Circle, CircleDashed, ListTodo, Loader2 } from 'lucide-react';
import type { TodoItem } from '@/lib/maa';

/** Panel todo list live (tampil saat agent bekerja tugas multi-langkah). */
export function TodoPanel({ todos }: { todos: TodoItem[] | null | undefined }) {
  const items = useMemo(() => (todos || []).slice(0, 20), [todos]);
  if (!items.length) return null;

  const done = items.filter((t) => t.status === 'completed').length;
  const pct = Math.round((done / items.length) * 100);
  const allDone = done === items.length;

  return (
    <div className="maa-panel mb-4 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[12px] font-bold text-[var(--ink)]">
          <ListTodo className="h-4 w-4" style={{ color: 'var(--accent)' }} />
          Rencana Tugas
          <span className="rounded-full border border-[var(--line-soft)] px-1.5 py-px text-[10px] font-semibold text-[var(--muted-fg)]">
            {done}/{items.length}
          </span>
        </p>
        {allDone && (
          <span className="flex items-center gap-1 text-[10.5px] font-semibold text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5" /> selesai
          </span>
        )}
      </div>

      {/* progress bar */}
      <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[var(--muted-bg)]">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: 'var(--accent)' }}
        />
      </div>

      <ul className="space-y-2">
        {items.map((t, i) => {
          const st = t.status || 'pending';
          return (
            <li key={i} className="flex items-start gap-2.5 text-[13px]">
              <span className="mt-0.5 shrink-0">
                {st === 'completed' ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                ) : st === 'in_progress' ? (
                  <Loader2 className="h-4 w-4 animate-spin" style={{ color: 'var(--accent)' }} />
                ) : (
                  <CircleDashed className="h-4 w-4 text-[var(--muted-fg)]" />
                )}
              </span>
              <span
                className={`leading-snug ${
                  st === 'completed'
                    ? 'text-[var(--muted-fg)] line-through decoration-[var(--muted-fg)]/50'
                    : st === 'in_progress'
                      ? 'font-medium text-[var(--ink)]'
                      : 'text-[var(--ink)]'
                }`}
              >
                {t.content}
              </span>
              {st === 'in_progress' && (
                <span className="ml-auto shrink-0 rounded-full px-1.5 py-px text-[9.5px] font-bold uppercase tracking-wide" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
                  berjalan
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
