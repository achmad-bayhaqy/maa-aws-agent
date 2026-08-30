'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Activity, AlertTriangle, Brain, BookOpen, CheckSquare, ChevronDown, Eraser,
  FileCode2, Globe, HelpCircle, History, Image as ImageIcon, Loader2, MessageSquareText,
  RefreshCcw, ShieldAlert, ShieldCheck, Sparkles, Terminal, User, Wrench, type LucideIcon,
} from 'lucide-react';
import { TRACE_META, traceLabel, type TraceEvent } from '@/lib/maa';
import { fmtClock } from '@/lib/maa';

const TRACE_ICONS: Record<string, LucideIcon> = {
  user_msg: User,
  thinking: Brain,
  tool_call: Wrench,
  tool_result: CheckSquare,
  kb_search: BookOpen,
  web_search: Globe,
  code_interpreter: Terminal,
  image_gen: ImageIcon,
  memory_recall: History,
  clarify: HelpCircle,
  iac: FileCode2,
  confirm_required: ShieldAlert,
  confirm_executed: ShieldCheck,
  self_heal: RefreshCcw,
  error: AlertTriangle,
  response: MessageSquareText,
};

export function TracePanel({
  events,
  processing,
  onClear,
  onClose,
  embedded,
}: {
  events: TraceEvent[];
  processing?: boolean;
  onClear?: () => void;
  onClose?: () => void;
  embedded?: boolean;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    if (stick.current) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [events.length]);

  const toggle = (i: number) =>
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(i)) n.delete(i);
      else n.add(i);
      return n;
    });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={`flex shrink-0 items-center gap-2 border-b border-[var(--line)] px-4 py-3 ${embedded ? '' : ''}`}>
        <Activity className="h-4 w-4" style={{ color: 'var(--accent)' }} />
        <h3 className="text-[13px] font-semibold tracking-tight text-[var(--ink)]">Live Trace</h3>
        <span className="rounded-full border border-[var(--line-soft)] bg-[var(--surface)] px-2 py-0.5 font-mono text-[10px] font-medium text-[var(--muted-fg)]">
          {events.length} event
        </span>
        {processing && (
          <span className="flex items-center gap-1 rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--ink)]">
            <Loader2 className="h-3 w-3 animate-spin" style={{ color: 'var(--accent)' }} />
            live
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          {events.length > 0 && onClear && (
            <button
              type="button"
              onClick={onClear}
              title="Bersihkan view"
              className="rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
            >
              <Eraser className="h-3.5 w-3.5" />
            </button>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              title="Tutup"
              className="rounded-md p-1.5 text-[var(--muted-fg)] transition-colors hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          )}
        </span>
      </div>

      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        }}
        className="nice-scroll min-h-0 flex-1 overflow-y-auto px-4 py-3"
      >
        {events.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-2.5 text-center">
            <div className="rounded-[10px] border border-[var(--line-soft)] bg-[var(--surface)] p-3">
              <Activity className="h-5 w-5 text-[var(--muted-fg)]" />
            </div>
            <p className="max-w-[230px] text-[11.5px] leading-relaxed text-[var(--muted-fg)]">
              Belum ada event. Setiap langkah agent — berpikir, tool call, hasil, KB, konfirmasi — tampil
              transparan di sini (sumber: CloudWatch).
            </p>
          </div>
        )}

        <div className="relative space-y-1.5">
          {events.length > 1 && (
            <span className="absolute bottom-2 left-[11px] top-2 w-px bg-[var(--line-soft)]" aria-hidden />
          )}
          {events.map((e, i) => {
            const meta = TRACE_META[e.type] || {
              label: e.type,
              tint: 'text-[var(--ink)]',
              dot: 'bg-[var(--muted-fg)]',
            };
            const Icon = TRACE_ICONS[e.type] || Sparkles;
            const isOpen = expanded.has(i);
            return (
              <div key={`${e.ts}-${i}`} className="relative flex gap-2.5 py-0.5">
                <span className={`relative z-10 mt-1 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border border-[var(--line-soft)] bg-[var(--bg)] ${meta.tint}`}>
                  <Icon className="h-3 w-3" />
                </span>
                <button
                  type="button"
                  onClick={() => toggle(i)}
                  className="min-w-0 flex-1 rounded-lg px-2 py-1 text-left transition-colors hover:bg-[var(--surface)]"
                  aria-expanded={isOpen}
                >
                  <span className="flex items-center gap-1.5">
                    <span className={`text-[11px] font-semibold ${meta.tint}`}>{traceLabel(e.type)}</span>
                    <span className="font-mono text-[9.5px] text-[var(--muted-fg)]">{fmtClock(e.ts)}</span>
                    {e.model && (
                      <span className="max-w-[110px] truncate rounded-full border border-[var(--line-soft)] bg-[var(--bg)] px-1.5 font-mono text-[9px] text-[var(--muted-fg)]">
                        {e.model}
                      </span>
                    )}
                  </span>
                  <span
                    className={`mt-0.5 block whitespace-pre-wrap font-mono text-[10.5px] leading-relaxed text-[var(--muted-fg)] ${
                      isOpen ? '' : 'line-clamp-2'
                    }`}
                  >
                    {e.content || '—'}
                  </span>
                  {isOpen && e.content && e.content.length > 120 && (
                    <span className="mt-1 block border-t border-[var(--line-soft)] pt-1 text-[9.5px] text-[var(--muted-fg)]">
                      klik untuk tutup
                    </span>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
