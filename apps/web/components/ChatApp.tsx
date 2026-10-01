"use client";

import { useLiveQuery } from "dexie-react-hooks";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { USANDO_MOCK } from "@/lib/agent-client";
import { db } from "@/lib/db";
import { obterSessao } from "@/lib/session";
import { useChat } from "@/lib/use-chat";
import ChatWindow from "./ChatWindow";
import ConversationList from "./ConversationList";
import StorageNotice from "./StorageNotice";

export default function ChatApp() {
  const params = useParams<{ conversaId?: string }>();
  const conversaId = params.conversaId ?? null;
  const chat = useChat();
  const [menuAberto, setMenuAberto] = useState(false);

  const titulo = useLiveQuery(
    async () => (conversaId ? (await db.conversas.get(conversaId))?.titulo : undefined),
    [conversaId],
  );

  // Primeira visita: gera o session_id e pede armazenamento persistente.
  useEffect(() => {
    obterSessao();
  }, []);

  useEffect(() => {
    document.title = titulo ? `${titulo} · CineDetetive` : "CineDetetive";
  }, [titulo]);

  return (
    <div className="relative z-10 flex h-dvh overflow-hidden">
      {menuAberto && (
        <div className="fixed inset-0 z-20 bg-black/60 md:hidden" onClick={() => setMenuAberto(false)} aria-hidden />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-line bg-film transition-transform md:static md:translate-x-0 ${
          menuAberto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pb-2 pt-4">
          <Link href="/" className="font-display text-xl" onClick={() => setMenuAberto(false)}>
            Cine<span className="text-marquee">Detetive</span>
          </Link>
        </div>
        <div className="px-3 pb-2">
          <Link
            href="/"
            onClick={() => setMenuAberto(false)}
            className="flex items-center justify-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-paper transition hover:border-marquee/50 hover:bg-reel"
          >
            <span className="text-marquee">+</span> Nova investigação
          </Link>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2">
          <ConversationList conversaId={conversaId} onNavegar={() => setMenuAberto(false)} />
        </div>

        <StorageNotice />

        <footer className="border-t border-line px-4 py-3 text-[10px] leading-relaxed text-muted">
          <p>
            Dados de filmes e pôsteres:{" "}
            <a href="https://www.themoviedb.org/" target="_blank" rel="noreferrer" className="text-paper/80 hover:text-marquee">
              TMDB
            </a>
            . Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB.
          </p>
          <p className="mt-1">
            Sinopses da{" "}
            <a
              href="https://en.wikipedia.org/"
              target="_blank"
              rel="noreferrer"
              className="text-paper/80 hover:text-marquee"
            >
              Wikipedia
            </a>{" "}
            (CC BY-SA).
          </p>
        </footer>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line/60 px-3 sm:px-4">
          <button
            className="rounded-md p-1.5 text-paper hover:bg-reel md:hidden"
            onClick={() => setMenuAberto(true)}
            aria-label="Abrir conversas"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
            </svg>
          </button>
          <p className="min-w-0 flex-1 truncate text-sm text-paper/80">{titulo ?? "Nova investigação"}</p>
          {USANDO_MOCK && (
            <span
              className="shrink-0 rounded-full border border-marquee/40 px-2 py-0.5 text-[10px] uppercase tracking-wider text-marquee"
              title="Sem NEXT_PUBLIC_AGENT_URL: respostas vêm de lib/mock-agent.ts"
            >
              agente simulado
            </span>
          )}
        </header>

        <ChatWindow conversaId={conversaId} chat={chat} />
      </main>
    </div>
  );
}
