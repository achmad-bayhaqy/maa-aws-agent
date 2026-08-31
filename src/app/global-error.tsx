'use client';

// Global-error: jaring pengaman terakhir bila error.tsx pun gagal render
// (mis. error di layout akar). Wajib punya <html>/<body> sendiri.
import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[MAA] fatal client error:', error?.message);
  }, [error]);

  return (
    <html lang="id">
      <body
        style={{
          margin: 0, minHeight: '100vh', display: 'flex', alignItems: 'center',
          justifyContent: 'center', background: '#fafafa', color: '#18181b',
          fontFamily: 'system-ui, -apple-system, sans-serif', textAlign: 'center', padding: 24,
        }}
      >
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700 }}>Terjadi kesalahan tak terduga</h1>
          <p style={{ fontSize: 13, color: '#71717a', marginTop: 8 }}>
            Sesi Anda tetap aman. Silakan muat ulang halaman untuk melanjutkan.
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: 16, padding: '9px 20px', borderRadius: 10, border: 'none',
              background: '#DC2626', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}
          >
            Muat ulang
          </button>
        </div>
      </body>
    </html>
  );
}
