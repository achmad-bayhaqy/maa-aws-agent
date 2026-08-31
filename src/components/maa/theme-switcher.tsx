'use client';

import { useState } from 'react';
import { Moon, Palette, Sparkles, Sun, SunMoon } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { ACCENTS, applyTheme, type MaaTheme, type PatternMode, type RadiusMode, type DensityMode, type SurfaceMode } from './theme';

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
      {children}
    </p>
  );
}

function OptionGrid<T extends string>({
  options,
  value,
  onPick,
  cols,
}: {
  options: { id: T; label: string }[];
  value: T;
  onPick: (v: T) => void;
  cols: number;
}) {
  return (
    <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={value === o.id}
          onClick={() => onPick(o.id)}
          className={`rounded-lg border px-2 py-1.5 text-[11.5px] font-medium transition-colors ${
            value === o.id
              ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]'
              : 'border-[var(--line-soft)] text-[var(--muted-fg)] hover:bg-[var(--muted-bg)]'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Panel isi: 12 aksen + mode permukaan + sudut + tekstur + kepadatan + glow. */
export function ThemePanel({ theme, onChange }: { theme: MaaTheme; onChange: (t: MaaTheme) => void }) {
  const set = (t: MaaTheme) => {
    applyTheme(t);
    onChange(t);
  };

  const surfaces: { id: SurfaceMode; label: string; icon?: React.ReactNode }[] = [
    { id: 'light', label: 'Terang' },
    { id: 'dark', label: 'Gelap' },
    { id: 'oled', label: 'OLED' },
    { id: 'sepia', label: 'Sepia' },
  ];

  return (
    <div className="nice-scroll max-h-[70vh] space-y-4 overflow-y-auto pr-1">
      <div>
        <SectionLabel>Warna aksen</SectionLabel>
        <div className="grid grid-cols-6 gap-2">
          {chunk(ACCENTS, 6).map((row, i) => (
            <div key={i} className="col-span-6 grid grid-cols-6 gap-2">
              {row.map((a) => {
                const active = a.hex.toLowerCase() === theme.accent.toLowerCase();
                return (
                  <button
                    key={a.id}
                    type="button"
                    aria-label={`Aksen ${a.name}`}
                    aria-pressed={active}
                    title={a.name}
                    onClick={() => set({ ...theme, accent: a.hex })}
                    className="group flex justify-center"
                  >
                    <span
                      className={`h-6 w-6 rounded-full border border-[var(--line)] transition-shadow ${
                        active ? 'ring-2 ring-[var(--accent)] ring-offset-2 ring-offset-[var(--bg)]' : ''
                      }`}
                      style={{ background: a.hex }}
                    />
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div>
        <SectionLabel>Mode permukaan</SectionLabel>
        <OptionGrid
          cols={4}
          options={surfaces.map((s) => ({ id: s.id, label: s.label }))}
          value={theme.mode}
          onPick={(v) => set({ ...theme, mode: v })}
        />
        <p className="mt-1.5 flex items-center gap-1 text-[10px] leading-relaxed text-[var(--muted-fg)]">
          {theme.mode === 'oled' ? (
            <><Moon className="h-3 w-3" /> Hitam pekat — hemat daya layar OLED/AMOLED.</>
          ) : theme.mode === 'sepia' ? (
            <><SunMoon className="h-3 w-3" /> Kertas hangat — nyaman untuk membaca lama.</>
          ) : theme.mode === 'dark' ? (
            <><Moon className="h-3 w-3" /> Gelap standar untuk kondisi cahaya rendah.</>
          ) : (
            <><Sun className="h-3 w-3" /> Terang standar MAA Redline.</>
          )}
        </p>
      </div>

      <div>
        <SectionLabel>Bentuk sudut</SectionLabel>
        <OptionGrid<RadiusMode>
          cols={3}
          options={[
            { id: 'sharp', label: 'Tajam' },
            { id: 'normal', label: 'Standar' },
            { id: 'round', label: 'Bulat' },
          ]}
          value={theme.radius}
          onPick={(v) => set({ ...theme, radius: v })}
        />
      </div>

      <div>
        <SectionLabel>Tekstur latar</SectionLabel>
        <OptionGrid<PatternMode>
          cols={3}
          options={[
            { id: 'none', label: 'Polos' },
            { id: 'grid', label: 'Grid' },
            { id: 'dots', label: 'Titik' },
          ]}
          value={theme.pattern}
          onPick={(v) => set({ ...theme, pattern: v })}
        />
      </div>

      <div>
        <SectionLabel>Kepadatan tampilan</SectionLabel>
        <OptionGrid<DensityMode>
          cols={3}
          options={[
            { id: 'compact', label: 'Padat' },
            { id: 'normal', label: 'Standar' },
            { id: 'roomy', label: 'Lega' },
          ]}
          value={theme.density}
          onPick={(v) => set({ ...theme, density: v })}
        />
      </div>

      <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line-soft)] px-3 py-2.5">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--ink)]">
            <Sparkles className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} /> Efek glow aksen
          </p>
          <p className="text-[10.5px] leading-relaxed text-[var(--muted-fg)]">
            Tombol utama & elemen aktif berpendar mengikuti warna aksen.
          </p>
        </div>
        <Switch
          checked={theme.glow}
          onCheckedChange={(v) => set({ ...theme, glow: v })}
          aria-label="Aktif/nonaktif efek glow"
        />
      </div>

      <button
        type="button"
        onClick={() => set({ accent: '#DC2626', mode: 'light', radius: 'normal', pattern: 'none', density: 'normal', glow: false })}
        className="maa-btn-ghost w-full border border-[var(--line-soft)] py-1.5 text-[11px] text-[var(--muted-fg)]"
      >
        <Palette className="mr-1 inline h-3 w-3" /> Kembalikan ke default MAA Redline
      </button>
    </div>
  );
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
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
      <PopoverContent align="end" className="w-80">
        <p className="mb-3 text-[13px] font-semibold text-[var(--ink)]">Tampilan — MAA Redline Extended</p>
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
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[15px] font-semibold text-[var(--ink)]">Tema tampilan</DialogTitle>
        </DialogHeader>
        <ThemePanel theme={theme} onChange={onChange} />
      </DialogContent>
    </Dialog>
  );
}
