'use client';

import { BookOpen, Cable, Check, Database, FileText, Loader2, LogOut, Moon, Palette, Plus, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react';
import type { SessionRow } from '@/lib/maa';
import { relTime } from '@/lib/maa';
import { LogoWordmark } from './logo';

function StatusDot({ status }: { status?: string }) {
  if (status === 'processing')
    return <Loader2 className="h-3 w-3 shrink-0 animate-spin" style={{ color: 'var(--accent)' }} />;
  if (status === 'error') return <X className="h-3 w-3 shrink-0 text-[var(--danger)]" />;
  return <Check className="h-3 w-3 shrink-0 text-emerald-600 dark:text-emerald-400" />;
}

export function SidebarContent({
  sessions,
  activeId,
  onSelectSession,
  onDeleteSession,
  onNewChat,
  onOpenDocs,
  onOpenKb,
  onOpenSkills,
  onOpenConnectors,
  onOpenAdmin,
  onOpenTheme,
  canAdmin,
  userName,
  onLogout,
}: {
  sessions: SessionRow[];
  activeId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNewChat: () => void;
  onOpenDocs: () => void;
  onOpenKb: () => void;
  onOpenSkills: () => void;
  onOpenConnectors: () => void;
  onOpenAdmin: () => void;
  onOpenTheme: () => void;
  canAdmin: boolean;
  userName: string;
  onLogout: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-[var(--line)] px-4 py-3.5">
        <LogoWordmark size={24} />
      </div>

      <div className="p-3">
        <button
          type="button"
          onClick={onNewChat}
          className="maa-btn-primary flex h-10 w-full items-center justify-center gap-2 text-[13px]"
        >
          <Plus className="h-4 w-4" /> Chat Baru
        </button>
      </div>

      {/* daftar sesi */}
      <nav className="nice-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-2" aria-label="Daftar sesi">
        <p className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-fg)]">
          Sesi ({sessions.length})
        </p>
        {sessions.length === 0 ? (
          <p className="px-1 py-3 text-[11.5px] leading-relaxed text-[var(--muted-fg)]">
            Belum ada sesi. Mulai percakapan pertama Anda — agent siap 24/7.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {sessions.map((s) => {
              const active = s.sessionId === activeId;
              return (
                <li key={s.sessionId} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelectSession(s.sessionId)}
                    aria-current={active ? 'page' : undefined}
                    className={`flex w-full items-center gap-2 rounded-lg border-l-2 px-2.5 py-2 text-left transition-colors ${
                      active
                        ? 'border-l-[var(--accent)] bg-[var(--accent-soft)]'
                        : 'border-l-transparent hover:bg-[var(--muted-bg)]'
                    }`}
                  >
                    <StatusDot status={s.status} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium text-[var(--ink)]">
                        {s.title || 'Sesi tanpa judul'}
                      </span>
                      <span className="block text-[10px] text-[var(--muted-fg)]">
                        {relTime(s.updatedAt || s.createdAt)}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Hapus sesi: ${s.title || s.sessionId}`}
                    title="Hapus sesi"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(s.sessionId);
                    }}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md bg-[var(--surface)] p-1.5 text-[var(--muted-fg)] opacity-0 shadow-sm transition-opacity hover:bg-[var(--danger-soft,var(--muted-bg))] hover:text-[var(--danger)] focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* menu bawah */}
      <div className="space-y-0.5 border-t border-[var(--line-soft)] p-3">
        {[
          { icon: <FileText className="h-4 w-4" />, label: 'Dokumentasi', onClick: onOpenDocs },
          { icon: <Database className="h-4 w-4" />, label: 'Knowledge Base', onClick: onOpenKb },
          { icon: <Sparkles className="h-4 w-4" />, label: 'Skills Library', onClick: onOpenSkills },
          { icon: <Cable className="h-4 w-4" />, label: 'Konektor Data', onClick: onOpenConnectors },
          ...(canAdmin
            ? [{ icon: <ShieldCheck className="h-4 w-4" />, label: 'Management User', onClick: onOpenAdmin }]
            : []),
          { icon: <Palette className="h-4 w-4" />, label: 'Tema', onClick: onOpenTheme },
        ].map((it) => (
          <button
            key={it.label}
            type="button"
            onClick={it.onClick}
            className="maa-btn-ghost flex w-full items-center gap-2.5 px-2.5 py-2 text-[12.5px] font-medium"
          >
            {it.icon}
            {it.label}
          </button>
        ))}
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-[var(--line-soft)] pt-2.5">
          <span className="min-w-0 truncate text-[11.5px] font-medium text-[var(--muted-fg)]" title={userName}>
            {userName}
          </span>
          <button
            type="button"
            onClick={onLogout}
            aria-label="Keluar"
            title="Keluar"
            className="maa-btn-ghost flex items-center gap-1.5 px-2 py-1.5 text-[11.5px] font-medium text-[var(--muted-fg)] hover:text-[var(--ink)]"
          >
            <LogOut className="h-3.5 w-3.5" /> Keluar
          </button>
        </div>
      </div>

      <div className="hidden items-center gap-1.5 border-t border-[var(--line-soft)] px-4 py-2 text-[9.5px] text-[var(--muted-fg)] lg:flex">
        <BookOpen className="h-3 w-3" /> AgentCore · Guardrail · STS 5 mnt
        <Moon className="ml-auto h-3 w-3" aria-hidden />
      </div>
    </div>
  );
}
