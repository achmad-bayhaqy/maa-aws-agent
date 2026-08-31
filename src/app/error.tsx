'use client';

// Error boundary tingkat route: mencegah "Application error: a client-side
// exception" mematikan seluruh app — tampil fallback ramah + tombol muat ulang.
import { useEffect } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // log ke console untuk diagnosis (tanpa membocorkan data sensitif)
    console.error('[MAA] client error:', error?.message);
  }, [error]);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-[var(--bg)] p-6 text-center text-[var(--ink)]">
      <div className="maa-panel flex max-w-sm flex-col items-center gap-3 p-7">
        <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--accent-soft)]">
          <AlertTriangle className="h-6 w-6" style={{ color: 'var(--accent)' }} />
        </span>
        <h1 className="text-[16px] font-bold">Terjadi kesalahan tak terduga</h1>
        <p className="text-[12.5px] leading-relaxed text-[var(--muted-fg)]">
          Antarmuka gagal dirender pada titik ini. Sesi dan riwayat chat Anda tetap aman di server.
          Coba muat ulang halaman.
        </p>
        <div className="mt-1 flex items-center gap-2">
          <Button onClick={reset} className="maa-btn-primary gap-1.5 px-4 text-[12.5px]">
            <RefreshCcw className="h-3.5 w-3.5" /> Coba lagi
          </Button>
          <Button
            variant="outline"
            onClick={() => window.location.reload()}
            className="px-4 text-[12.5px]"
          >
            Muat ulang halaman
          </Button>
        </div>
        {error?.digest && (
          <p className="mt-1 font-mono text-[9.5px] text-[var(--muted-fg)]">ref: {error.digest}</p>
        )}
      </div>
    </main>
  );
}
