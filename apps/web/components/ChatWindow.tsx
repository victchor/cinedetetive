"use client";

import { useLiveQuery } from "dexie-react-hooks";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { db, mensagensDa } from "@/lib/db";
import type { Rascunho, useChat } from "@/lib/use-chat";
import Composer from "./Composer";
import MessageBubble, { Avatar } from "./MessageBubble";
import MovieCard from "./MovieCard";
import RichText from "./RichText";

const EXEMPLOS = [
  "Um filme dos anos 90 em que o cara acorda todo dia no mesmo dia, acho que tinha uma marmota",
  "Um cara descobre que a vida dele inteira é um programa de TV",
  "Ficção científica com astronautas, um buraco negro e um pai que deixa a filha",
  "Um ladrão que invade sonhos das pessoas, tinha um pião no final",
];

interface Props {
  conversaId: string | null;
  chat: ReturnType<typeof useChat>;
}

export default function ChatWindow({ conversaId, chat }: Props) {
  const conversa = useLiveQuery(
    async () => (conversaId ? ((await db.conversas.get(conversaId)) ?? null) : null),
    [conversaId],
  );
  const mensagens = useLiveQuery(async () => (conversaId ? mensagensDa(conversaId) : []), [conversaId]) ?? [];
  const rascunho = chat.rascunho?.conversaId === conversaId ? chat.rascunho : null;

  const fimRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensagens.length, rascunho?.texto, rascunho?.etapa, rascunho?.candidatos.length]);

  const naoEncontrada = conversaId && conversa === null && !rascunho;
  const vazia = !conversaId || (mensagens.length === 0 && !rascunho);
  const aberta = conversa?.status !== "resolvida";
  const idUltimaDoAgente = mensagens.findLast((m) => m.papel === "assistant" && m.tipo !== "confirmacao")?.id;
  const ultimaEhDoAgente = mensagens.at(-1)?.papel === "assistant";

  if (naoEncontrada) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="font-display text-2xl">Conversa não encontrada</p>
        <p className="max-w-sm text-sm text-muted">
          O histórico fica só neste navegador. Ela pode ter sido apagada ou foi aberta em outro navegador.
        </p>
        <Link href="/" className="rounded-md bg-marquee px-4 py-2 text-sm font-semibold text-ink">
          Começar uma investigação
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {vazia ? (
          <EmptyState onExemplo={(t) => chat.enviar(t, conversaId)} />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
            {mensagens.map((m) => (
              <MessageBubble
                key={m.id}
                mensagem={m}
                ativa={aberta && !chat.ocupado && m.id === idUltimaDoAgente && ultimaEhDoAgente}
                onConfirmar={(f) => chat.confirmar(m.conversa_id, f)}
                onRecusar={(fs) => chat.recusar(m.conversa_id, fs)}
                onRepetir={() => chat.repetir(m.conversa_id)}
              />
            ))}
            {rascunho && <StreamingBubble rascunho={rascunho} />}
            <div ref={fimRef} />
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-3xl px-4 pb-4 pt-2 sm:px-6">
        {conversa?.status === "resolvida" && !chat.ocupado && (
          <p className="mb-2 text-center text-xs text-muted">
            Caso encerrado. Escreva de novo se quiser reabrir a investigação, ou{" "}
            <Link href="/" className="text-marquee underline-offset-2 hover:underline">
              comece outra
            </Link>
            .
          </p>
        )}
        <Composer
          ocupado={chat.ocupado}
          placeholder={vazia ? "Descreva o filme do jeito que você lembra…" : "Responda ou dê mais uma pista…"}
          onEnviar={(t) => chat.enviar(t, conversaId)}
          onParar={chat.parar}
        />
      </div>
    </div>
  );
}

function StreamingBubble({ rascunho }: { rascunho: Rascunho }) {
  return (
    <div className="flex gap-3" aria-live="polite">
      <Avatar />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {rascunho.etapa && !rascunho.texto && (
          <div className="flex items-center gap-2 pt-1.5 text-sm text-muted">
            <svg viewBox="0 0 24 24" className="animate-reel h-4 w-4 text-marquee" fill="none" stroke="currentColor" strokeWidth={1.6}>
              <circle cx="12" cy="12" r="9" />
              <circle cx="12" cy="7" r="1.6" fill="currentColor" />
              <circle cx="12" cy="17" r="1.6" fill="currentColor" />
              <circle cx="7" cy="12" r="1.6" fill="currentColor" />
              <circle cx="17" cy="12" r="1.6" fill="currentColor" />
            </svg>
            <span>{rascunho.etapa}…</span>
          </div>
        )}
        {rascunho.texto && (
          <div
            className={`cursor-blink text-[15px] leading-relaxed ${
              rascunho.pergunta ? "rounded-2xl rounded-tl-sm border border-marquee/40 bg-marquee/10 px-4 py-2.5" : "pt-1"
            }`}
          >
            <RichText texto={rascunho.texto} />
          </div>
        )}
        {rascunho.candidatos.length > 0 && (
          <div className="grid gap-2">
            {rascunho.candidatos.map((c, i) => (
              <MovieCard key={c.tmdb_id} filme={c} destaque={i === 0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ onExemplo }: { onExemplo: (t: string) => void }) {
  return (
    <div className="spotlight flex min-h-full flex-col items-center justify-center px-4 py-12 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-marquee/40 bg-film text-3xl">
        🕵️
      </div>
      <h1 className="font-display text-4xl tracking-tight sm:text-5xl">
        Cine<span className="text-marquee">Detetive</span>
      </h1>
      <p className="mt-3 max-w-md text-balance text-muted">
        Esqueceu o nome de um filme? Conte o que você lembra — uma cena, a época, um ator. Se eu não tiver certeza,
        eu pergunto.
      </p>
      <div className="mt-8 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
        {EXEMPLOS.map((e) => (
          <button
            key={e}
            onClick={() => onExemplo(e)}
            className="rounded-xl border border-line bg-film/70 px-4 py-3 text-left text-sm text-paper/80 transition hover:border-marquee/50 hover:text-paper"
          >
            “{e}”
          </button>
        ))}
      </div>
    </div>
  );
}
