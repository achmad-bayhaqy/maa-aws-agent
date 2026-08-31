'use client';

// MAA Redline Extended — sistem tema v3.5.
// Diterapkan via CSS variables + data-attribute pada <html>, dipersist ke
// localStorage["maa.theme"]. Struktur: aksen (12 preset), mode permukaan
// (terang/gelap/oled/sepia), bentuk sudut (tajam/standar/bulat), tekstur
// latar (polos/grid/titik), kepadatan (padat/standar/lega), efek glow.

export type AccentPreset = { id: string; name: string; hex: string };

export const ACCENTS: AccentPreset[] = [
  { id: 'merah', name: 'Merah', hex: '#DC2626' },
  { id: 'crimson', name: 'Crimson', hex: '#E11D48' },
  { id: 'biru', name: 'Biru', hex: '#2563EB' },
  { id: 'indigo', name: 'Indigo', hex: '#4F46E5' },
  { id: 'teal', name: 'Teal', hex: '#0D9488' },
  { id: 'cyan', name: 'Cyan', hex: '#0891B2' },
  { id: 'hijau', name: 'Hijau', hex: '#16A34A' },
  { id: 'ungu', name: 'Ungu', hex: '#7C3AED' },
  { id: 'oranye', name: 'Oranye', hex: '#EA580C' },
  { id: 'emas', name: 'Emas', hex: '#D97706' },
  { id: 'pink', name: 'Pink', hex: '#DB2777' },
  { id: 'slate', name: 'Graphite', hex: '#475569' },
];

export type SurfaceMode = 'light' | 'dark' | 'oled' | 'sepia';
export type RadiusMode = 'sharp' | 'normal' | 'round';
export type PatternMode = 'none' | 'grid' | 'dots';
export type DensityMode = 'compact' | 'normal' | 'roomy';

export type MaaTheme = {
  accent: string;
  mode: SurfaceMode;
  radius: RadiusMode;
  pattern: PatternMode;
  density: DensityMode;
  glow: boolean;
};

export const DEFAULT_THEME: MaaTheme = {
  accent: '#DC2626',
  mode: 'light',
  radius: 'normal',
  pattern: 'none',
  density: 'normal',
  glow: false,
};

const KEY = 'maa.theme';

const RADIUS_PX: Record<RadiusMode, string> = { sharp: '3px', normal: '10px', round: '17px' };
const DENSITY_ZOOM: Record<DensityMode, string> = { compact: '0.94', normal: '1', roomy: '1.06' };

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const v = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function isDarkMode(mode: SurfaceMode): boolean {
  return mode === 'dark' || mode === 'oled';
}

export function loadTheme(): MaaTheme {
  if (typeof window === 'undefined') return { ...DEFAULT_THEME };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_THEME };
    const t = JSON.parse(raw) as Partial<MaaTheme> & { dark?: boolean };
    const accent =
      ACCENTS.find((a) => a.hex.toLowerCase() === (t.accent || '').toLowerCase())?.hex ||
      DEFAULT_THEME.accent;
    // migrasi tema lama { accent, dark } → mode
    const mode: SurfaceMode =
      t.mode === 'dark' || t.mode === 'oled' || t.mode === 'sepia'
        ? t.mode
        : t.dark
          ? 'dark'
          : 'light';
    return {
      accent,
      mode,
      radius: t.radius === 'sharp' || t.radius === 'round' ? t.radius : 'normal',
      pattern: t.pattern === 'grid' || t.pattern === 'dots' ? t.pattern : 'none',
      density: t.density === 'compact' || t.density === 'roomy' ? t.density : 'normal',
      glow: !!t.glow,
    };
  } catch {
    return { ...DEFAULT_THEME };
  }
}

/** Terapkan tema ke <html>: class dark + CSS vars + data-attribute. Aman dipanggil berulang. */
export function applyTheme(theme: MaaTheme) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const dark = isDarkMode(theme.mode);
  const [r, g, b] = hexToRgb(theme.accent);

  root.classList.toggle('dark', dark);
  root.dataset.maaMode = theme.mode;
  root.dataset.maaPattern = theme.pattern;
  root.dataset.maaDensity = theme.density;

  root.style.setProperty('--accent', theme.accent);
  root.style.setProperty(
    '--accent-soft',
    `rgb(${r} ${g} ${b} / ${dark ? 0.16 : 0.1})`
  );
  root.style.setProperty('--radius', RADIUS_PX[theme.radius]);
  root.style.setProperty('--glow', theme.glow ? `0 0 16px rgb(${r} ${g} ${b} / 0.45)` : 'none');

  // mode permukaan khusus (meng-overrides :root/.dark di globals.css)
  if (theme.mode === 'oled') {
    root.style.setProperty('--bg', '#000000');
    root.style.setProperty('--surface', '#0a0a0b');
    root.style.setProperty('--muted-bg', '#121214');
    root.style.setProperty('--popover', '#0a0a0b');
    root.style.setProperty('--line', '#26262a');
    root.style.setProperty('--line-soft', '#1a1a1d');
  } else if (theme.mode === 'sepia') {
    root.style.setProperty('--bg', '#f6f1e7');
    root.style.setProperty('--surface', '#efe8d8');
    root.style.setProperty('--muted-bg', '#eae2cf');
    root.style.setProperty('--popover', '#faf6ec');
    root.style.setProperty('--ink', '#3b3226');
    root.style.setProperty('--line', '#3b3226');
    root.style.setProperty('--line-soft', '#ddd2ba');
    root.style.setProperty('--muted-fg', '#7d6f58');
  } else {
    // light/dark: kembalikan ke nilai stylesheet (hapus override inline)
    for (const v of ['--bg', '--surface', '--muted-bg', '--popover', '--ink', '--line', '--line-soft', '--muted-fg']) {
      root.style.removeProperty(v);
    }
  }

  // zoom kepadatan (Chrome/Edge/Safari native; Firefox 126+)
  (root.style as CSSStyleDeclaration & { zoom?: string }).zoom = DENSITY_ZOOM[theme.density];

  try {
    localStorage.setItem(KEY, JSON.stringify(theme));
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
