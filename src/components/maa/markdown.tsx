'use client';

import { useState } from 'react';

// Renderer markdown ringan (tanpa dependensi eksternal): bold, italic, inline
// code, fenced code + copy, heading, list, tabel, gambar ![alt](url) → <img>
// (max-h 420px, klik buka tab baru), link → target _blank rel noopener.
// Semua warna mengikuti CSS vars tema "MAA Redline".

function safeUrl(u: string): string {
  const t = (u || '').trim();
  if (/^(https?:\/\/|\/)/i.test(t)) return t;
  return '#';
}

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${keyBase}-i${i++}`;
    if (tok.startsWith('**')) {
      nodes.push(<strong key={k} className="font-semibold text-[var(--ink)]">{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith('`')) {
      nodes.push(
        <code
          key={k}
          className="mx-0.5 rounded-md border border-[var(--line-soft)] bg-[var(--accent-soft)] px-1.5 py-0.5 font-mono text-[0.85em] text-[var(--ink)]"
        >
          {tok.slice(1, -1)}
        </code>
      );
    } else if (tok.startsWith('[')) {
      const mm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      const href = safeUrl(mm?.[2] || '');
      nodes.push(
        <a
          key={k}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium underline underline-offset-2"
          style={{ color: 'var(--accent)' }}
        >
          {mm?.[1]}
        </a>
      );
    } else {
      nodes.push(<em key={k} className="italic">{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }).catch(() => {});
  };
  return (
    <div className="my-2.5 overflow-hidden rounded-[10px] border border-[var(--line)] bg-[#0b0b0c] text-zinc-100">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5">
        <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-zinc-400">
          {lang || 'kode'}
        </span>
        <button
          type="button"
          onClick={copy}
          className="rounded-md px-2 py-0.5 text-[10.5px] font-medium text-zinc-300 transition-colors hover:bg-white/10 hover:text-white"
        >
          {copied ? 'tersalin ✓' : 'salin'}
        </button>
      </div>
      <pre className="nice-scroll overflow-x-auto px-3.5 py-3 font-mono text-[12.5px] leading-relaxed text-emerald-100/90">
        {code}
      </pre>
    </div>
  );
}

function MdImage({ alt, src }: { alt: string; src: string }) {
  const url = safeUrl(src);
  if (url === '#') return <span className="text-[var(--muted-fg)]">[gambar tidak valid]</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="mt-2 block w-fit max-w-full">
      <img
        src={url}
        alt={alt || 'Gambar hasil agent'}
        loading="lazy"
        className="max-h-[420px] max-w-full rounded-[10px] border border-[var(--line)] object-contain"
      />
    </a>
  );
}

export function Markdown({ text }: { text: string }) {
  const lines = (text || '').split('\n');
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim();
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) { buf.push(lines[i]); i++; }
      i++;
      blocks.push(<CodeBlock key={key++} lang={lang} code={buf.join('\n')} />);
      continue;
    }

    // gambar ![alt](url) pada baris sendiri
    const img = line.trim().match(/^!\[([^\]]*)\]\(([^)\s]+)\)$/);
    if (img) {
      blocks.push(<MdImage key={key++} alt={img[1]} src={img[2]} />);
      i++;
      continue;
    }

    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      const sizes = ['text-[17px]', 'text-[15.5px]', 'text-[14.5px]', 'text-[14px]'];
      blocks.push(
        <p key={key++} className={`mb-1 mt-3 font-bold tracking-tight text-[var(--ink)] ${sizes[h[1].length - 1]}`}>
          {renderInline(h[2], `h${key}`)}
        </p>
      );
      i++;
      continue;
    }

    if (/^\s*([-*•]|\d+\.)\s+/.test(line)) {
      const items: { text: string; ord: boolean }[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+\.)\s+/.test(lines[i])) {
        const ord = /^\s*\d+\./.test(lines[i]);
        items.push({ text: lines[i].replace(/^\s*([-*•]|\d+\.)\s+/, ''), ord });
        i++;
      }
      blocks.push(
        <ul key={key++} className="my-1.5 space-y-1">
          {items.map((it, j) => (
            <li key={j} className="flex gap-2 text-[14px] leading-relaxed text-[var(--ink)]">
              <span className="mt-[7px] flex h-1.5 w-1.5 shrink-0 items-center justify-center">
                {it.ord ? (
                  <span className="text-[11px] font-semibold leading-none" style={{ color: 'var(--accent)' }}>
                    {j + 1}.
                  </span>
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--accent)', opacity: 0.75 }} />
                )}
              </span>
              <span className="min-w-0 break-words">{renderInline(it.text, `li${key}-${j}`)}</span>
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // tabel markdown
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = lines[i].trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      if (rows.length) {
        const [head, ...body] = rows;
        blocks.push(
          <div key={key++} className="nice-scroll my-2.5 overflow-x-auto rounded-[10px] border border-[var(--line)]">
            <table className="w-full text-[12.5px]">
              {head.length > 0 && (
                <thead>
                  <tr className="border-b border-[var(--line)] bg-[var(--surface)]">
                    {head.map((hd, j) => (
                      <th key={j} className="px-3 py-2 text-left font-semibold text-[var(--ink)]">
                        {renderInline(hd, `th${key}-${j}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              <tbody>
                {body.map((r, j) => (
                  <tr key={j} className="border-b border-[var(--line-soft)] last:border-0">
                    {r.map((c, k) => (
                      <td key={k} className="px-3 py-1.5 text-[var(--ink)]/80">
                        {renderInline(c, `td${key}-${j}-${k}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    if (line.trim() === '') { i++; continue; }

    const buf: string[] = [];
    while (
      i < lines.length && lines[i].trim() !== '' && !lines[i].trim().startsWith('```') &&
      !/^(#{1,4})\s+/.test(lines[i]) && !/^\s*([-*•]|\d+\.)\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith('|') && !/^!\[[^\]]*\]\([^)]+\)$/.test(lines[i].trim())
    ) {
      buf.push(lines[i]); i++;
    }
    blocks.push(
      <p key={key++} className="my-1 text-[14px] leading-relaxed break-words text-[var(--ink)]">
        {renderInline(buf.join(' '), `p${key}`)}
      </p>
    );
  }

  return <div className="min-w-0">{blocks}</div>;
}
