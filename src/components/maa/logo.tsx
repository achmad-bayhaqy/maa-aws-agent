'use client';

import { useId } from 'react';

// Logo "Pin MAA" — pin lokasi ala Google Maps: gradient merah, outline hitam
// tipis, lingkaran putih, monogram "M" tebal. Dipakai di header, sidebar,
// login card, splash, dan favicon (public/logo.svg).

export function Logo({ size = 28, className = '' }: { size?: number; className?: string }) {
  // id gradient unik per instance (aman SSR/hydration)
  const rid = useId();
  const gid = `maaPin${rid.replace(/[^a-zA-Z0-9]/g, '')}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="Logo MAA"
      className={className}
      style={{ display: 'block' }}
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#DC2626" />
          <stop offset="1" stopColor="#991B1B" />
        </linearGradient>
      </defs>
      <path
        d="M24 3C15.7 3 9 9.7 9 18c0 4.6 2.4 9.1 5.4 13.1 3 4 6.5 7.4 8.4 9.2a2.4 2.4 0 0 0 3.3 0c1.9-1.8 5.4-5.2 8.4-9.2C37.6 27.1 40 22.6 40 18 40 9.7 32.3 3 24 3Z"
        fill={`url(#${gid})`}
        stroke="#111111"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="17.5" r="8" fill="#FFFFFF" stroke="#111111" strokeWidth="1.6" />
      <path
        d="M19.6 21.5v-8l4.4 4.6 4.4-4.6v8"
        fill="none"
        stroke="#111111"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LogoWordmark({ size = 22 }: { size?: number }) {
  return (
    <span className="flex items-center gap-2" aria-label="MAA AWS Agent">
      <Logo size={size} />
      <span className="flex flex-col leading-none">
        <span className="text-[15px] font-bold tracking-tight text-[var(--ink)]">MAA</span>
        <span className="text-[8.5px] font-semibold uppercase tracking-[0.22em] text-[var(--muted-fg)]">
          AWS Agent
        </span>
      </span>
    </span>
  );
}
