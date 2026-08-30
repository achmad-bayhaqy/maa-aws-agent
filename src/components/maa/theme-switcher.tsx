'use client';

import { useState } from 'react';
import { Moon, Palette, Sun } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { ACCENTS, applyTheme, type MaaTheme } from './theme';

/** Panel isi: 8 swatch aksen + toggle gelap/terang. */
export function ThemePanel({ theme, onChange }: { theme: MaaTheme; onChange: (t: MaaTheme) => void }) {
  const set = (t: MaaTheme) => {
    applyTheme(t);
    onChange(t);
  };
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
          Warna aksen
        </p>
        <div className="grid grid-cols-4 gap-2">
          {ACCENTS.map((a) => {
            const active = a.hex.toLowerCase() === theme.accent.toLowerCase();
            return (
              <button
                key={a.id}
                type="button"
                aria-label={`Aksen ${a.name}`}
                aria-pressed={active}
                onClick={() => set({ ...theme, accent: a.hex })}
                className={`group flex flex-col items-center gap-1.5 rounded-lg p-2 transition-colors hover:bg-[var(--muted-bg)] ${
                  active ? 'bg-[var(--accent-soft)]' : ''
                }`}
              >
                <span
                  className={`h-7 w-7 rounded-full border border-[var(--line)] transition-shadow ${
                    active ? 'ring-2 ring-[var(--accent)] ring-offset-2 ring-offset-[var(--bg)]' : ''
                  }`}
                  style={{ background: a.hex }}
                />
                <span className="text-[10px] font-medium text-[var(--muted-fg)]">{a.name}</span>
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
          Mode tampilan
        </p>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            aria-pressed={!theme.dark}
            onClick={() => set({ ...theme, dark: false })}
            className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-[12.5px] font-medium transition-colors ${
              !theme.dark
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]'
                : 'border-[var(--line-soft)] text-[var(--muted-fg)] hover:bg-[var(--muted-bg)]'
            }`}
          >
            <Sun className="h-4 w-4" /> Terang
          </button>
          <button
            type="button"
            aria-pressed={theme.dark}
            onClick={() => set({ ...theme, dark: true })}
            className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-[12.5px] font-medium transition-colors ${
              theme.dark
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]'
                : 'border-[var(--line-soft)] text-[var(--muted-fg)] hover:bg-[var(--muted-bg)]'
            }`}
          >
            <Moon className="h-4 w-4" /> Gelap
          </button>
        </div>
      </div>
    </div>
  );
}

/** Tombol tema di header (popover). */
export function ThemeSwitcher({ theme, onChange }: { theme: MaaTheme; onChange: (t: MaaTheme) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Pengaturan tema"
          className="flex h-9 items-center gap-1.5 rounded-lg border border-transparent px-2.5 text-[var(--muted-fg)] transition-colors hover:border-[var(--line-soft)] hover:bg-[var(--muted-bg)] hover:text-[var(--ink)]"
        >
          <Palette className="h-4 w-4" />
          <span className="hidden text-[12.5px] font-medium md:inline">Tema</span>
          <span className="h-2.5 w-2.5 rounded-full border border-black/10" style={{ background: theme.accent }} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72">
        <p className="mb-3 text-[13px] font-semibold text-[var(--ink)]">Tampilan</p>
        <ThemePanel theme={theme} onChange={onChange} />
      </PopoverContent>
    </Popover>
  );
}

/** Dialog tema (dipakai item menu "Tema" di sidebar). */
export function ThemeDialog({
  theme,
  onChange,
  open,
  onOpenChange,
}: {
  theme: MaaTheme;
  onChange: (t: MaaTheme) => void;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <button type="button" className="hidden" aria-hidden tabIndex={-1} />
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-[15px] font-semibold text-[var(--ink)]">Tema tampilan</DialogTitle>
        </DialogHeader>
        <ThemePanel theme={theme} onChange={onChange} />
      </DialogContent>
    </Dialog>
  );
}
