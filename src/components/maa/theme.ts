'use client';

// MAA Redline — preset aksen & mode gelap.
// Diterapkan via CSS variables pada <html> dan dipersist ke
// localStorage["maa.theme"] = { accent: "#DC2626", dark: false }.

export type AccentPreset = {
  id: string;
  name: string;
  hex: string;
};

export const ACCENTS: AccentPreset[] = [
  { id: 'merah', name: 'Merah', hex: '#DC2626' },
  { id: 'crimson', name: 'Crimson', hex: '#E11D48' },
  { id: 'biru', name: 'Biru', hex: '#2563EB' },
  { id: 'teal', name: 'Teal', hex: '#0D9488' },
  { id: 'hijau', name: 'Hijau', hex: '#16A34A' },
  { id: 'ungu', name: 'Ungu', hex: '#7C3AED' },
  { id: 'oranye', name: 'Oranye', hex: '#EA580C' },
  { id: 'pink', name: 'Pink', hex: '#DB2777' },
];

export const DEFAULT_THEME = { accent: '#DC2626', dark: false };

const KEY = 'maa.theme';

export type MaaTheme = { accent: string; dark: boolean };

export function loadTheme(): MaaTheme {
  if (typeof window === 'undefined') return { ...DEFAULT_THEME };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_THEME };
    const t = JSON.parse(raw) as Partial<MaaTheme>;
    const accent = ACCENTS.find((a) => a.hex === t.accent)?.hex || DEFAULT_THEME.accent;
    return { accent, dark: !!t.dark };
  } catch {
    return { ...DEFAULT_THEME };
  }
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const v = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Terapkan tema ke <html>: class dark + CSS vars. Aman dipanggil berulang. */
export function applyTheme(theme: MaaTheme) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('dark', theme.dark);
  const [r, g, b] = hexToRgb(theme.accent);
  root.style.setProperty('--accent', theme.accent);
  root.style.setProperty('--accent-soft', `rgb(${r} ${g} ${b} / ${theme.dark ? 0.16 : 0.1})`);
  try {
    localStorage.setItem(KEY, JSON.stringify({ accent: theme.accent, dark: theme.dark }));
  } catch {
    /* storage penuh / diblokir — abaikan */
  }
}

/** Baca tema tersimpan lalu langsung terapkan (dipanggil saat mount). */
export function initTheme(): MaaTheme {
  const t = loadTheme();
  applyTheme(t);
  return t;
}
