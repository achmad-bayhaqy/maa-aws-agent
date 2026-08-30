'use client';

import { useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Cpu, Search, Wrench, Zap } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { MaaModel } from '@/lib/maa';

export const PROVIDER_LABEL: Record<string, string> = {
  amazon: 'Amazon Nova', anthropic: 'Anthropic Claude', openai: 'OpenAI',
  openai_os: 'OpenAI-OS', google: 'Google', meta: 'Meta Llama', mistral: 'Mistral AI',
  deepseek: 'DeepSeek', qwen: 'Alibaba Qwen', zai: 'Z.ai GLM',
  moonshot: 'Moonshot Kimi', moonshotai: 'Moonshot Kimi', nvidia: 'NVIDIA',
  minimax: 'MiniMax', ai21: 'AI21', cohere: 'Cohere', writer: 'Writer',
  '01-ai': '01.AI', other: 'Lainnya',
};

/** Urutan grup yang stabil & mudah dipindai. */
const GROUP_ORDER = [
  'amazon', 'anthropic', 'openai', 'openai_os', 'google', 'meta', 'mistral',
  'deepseek', 'qwen', 'zai', 'moonshot', 'moonshotai', 'minimax', 'nvidia',
  'ai21', 'cohere', 'writer', '01-ai', 'other',
];

function groupKey(m: MaaModel): string {
  if (m.group) return m.group;
  return PROVIDER_LABEL[m.provider] ? m.provider : 'other';
}

function groupLabel(key: string): string {
  return PROVIDER_LABEL[key] || key.charAt(0).toUpperCase() + key.slice(1);
}

function MiniBadge({ tone, children }: { tone: 'emerald' | 'gray' | 'amber' | 'violet'; children: React.ReactNode }) {
  const cls =
    tone === 'emerald'
      ? 'border-emerald-600/30 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400'
      : tone === 'amber'
        ? 'border-amber-600/30 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400'
        : tone === 'violet'
          ? 'border-violet-600/30 bg-violet-50 text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-400'
          : 'border-[var(--line-soft)] bg-[var(--muted-bg)] text-[var(--muted-fg)]';
  return (
    <span className={`inline-flex items-center gap-0.5 rounded-full border px-1.5 py-px text-[9.5px] font-semibold leading-[14px] ${cls}`}>
      {children}
    </span>
  );
}

export function ModelPicker({
  models,
  value,
  onChange,
  disabled,
  autoDefaults,
}: {
  models: MaaModel[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
  autoDefaults?: { fast: string; deep: string };
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  // Reset pencarian + fokus setiap kali popover dibuka (tanpa effect).
  const handleOpenChange = (v: boolean) => {
    setOpen(v);
    if (v) {
      setQ('');
      setTimeout(() => searchRef.current?.focus(), 60);
    }
  };

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = models.filter((m) => {
      if (!needle) return true;
      return (
        m.modelId.toLowerCase().includes(needle) ||
        (m.name || '').toLowerCase().includes(needle) ||
        (m.provider || '').toLowerCase().includes(needle) ||
        groupLabel(groupKey(m)).toLowerCase().includes(needle)
      );
    });
    const g = new Map<string, MaaModel[]>();
    filtered.forEach((m) => {
      const k = groupKey(m);
      if (!g.has(k)) g.set(k, []);
      g.get(k)!.push(m);
    });
    const keys = [...g.keys()].sort((a, b) => {
      const ia = GROUP_ORDER.indexOf(a);
      const ib = GROUP_ORDER.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
    return keys.map((k) => ({ key: k, items: g.get(k)! }));
  }, [models, q]);

  const sel = models.find((m) => m.modelId === value);

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className="flex h-9 max-w-[220px] items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 text-left transition-colors hover:bg-[var(--surface)] disabled:opacity-50 sm:max-w-[280px]"
          aria-label="Pilih model"
        >
          <Cpu className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
          <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--ink)]">
            {sel ? sel.name : 'Pilih model…'}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--muted-fg)]" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-[min(420px,calc(100vw-2rem))] p-0">
        <div className="border-b border-[var(--line-soft)] p-2.5">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-fg)]" />
            <input
              ref={searchRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`Cari di ${models.length} model…`}
              className="h-9 w-full rounded-lg border border-[var(--line-soft)] bg-[var(--bg)] pl-8 pr-3 text-[13px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--muted-fg)] focus:border-[var(--accent)]"
            />
          </div>
        </div>
        <div className="nice-scroll max-h-[340px] overflow-y-auto overscroll-contain">
          {groups.length === 0 && (
            <p className="px-4 py-8 text-center text-[12.5px] text-[var(--muted-fg)]">
              Tidak ada model yang cocok dengan “{q}”.
            </p>
          )}
          {groups.map(({ key, items }) => (
            <div key={key}>
              <p className="sticky top-0 z-10 border-b border-[var(--line-soft)] bg-[var(--popover)]/95 px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-widest text-[var(--muted-fg)] backdrop-blur">
                {groupLabel(key)}
                <span className="ml-1.5 font-mono text-[9.5px] normal-case tracking-normal">
                  ({items.length})
                </span>
              </p>
              <ul className="py-0.5">
                {items.map((m) => {
                  const active = m.modelId === value;
                  return (
                    <li key={m.modelId}>
                      <button
                        type="button"
                        onClick={() => {
                          onChange(m.modelId);
                          setOpen(false);
                        }}
                        className={`flex w-full items-start gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--accent-soft)] ${
                          active ? 'bg-[var(--accent-soft)]' : ''
                        }`}
                      >
                        <span className="mt-0.5 shrink-0">
                          {active ? (
                            <Check className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                          ) : (
                            <span className="block h-4 w-4" />
                          )}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline gap-1.5">
                            <span className="truncate text-[13px] font-medium text-[var(--ink)]">
                              {m.name || m.modelId}
                            </span>
                            <span className="hidden shrink-0 font-mono text-[9.5px] text-[var(--muted-fg)] sm:inline">
                              {m.modelId}
                            </span>
                          </span>
                          <span className="mt-1 flex flex-wrap items-center gap-1">
                            {m.toolCompatible ? (
                              <MiniBadge tone="emerald">
                                <Wrench className="h-2.5 w-2.5" /> tools
                              </MiniBadge>
                            ) : (
                              <MiniBadge tone="gray">teks</MiniBadge>
                            )}
                            {m.cacheSupported && <MiniBadge tone="amber">cache</MiniBadge>}
                            {m.reasoning && <MiniBadge tone="violet">reasoning</MiniBadge>}
                            {(m.modelId === autoDefaults?.fast || m.modelId === autoDefaults?.deep) && (
                              <MiniBadge tone="gray">
                                <Zap className="h-2.5 w-2.5" />
                                {m.modelId === autoDefaults?.fast ? 'default FAST' : 'default DEEP'}
                              </MiniBadge>
                            )}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <div className="border-t border-[var(--line-soft)] px-3 py-2">
          <p className="text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
            <span className="font-semibold">tools</span> = bisa menjalankan tool AWS ·{" "}
            <span className="font-semibold">cache</span> = dukung prompt caching ·{" "}
            <span className="font-semibold">reasoning</span> = mode penalaran
          </p>
        </div>
      </PopoverContent>
    </Popover>
  );
}
