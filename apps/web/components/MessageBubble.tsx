"use client";

import type { Candidato, Mensagem } from "@/lib/types";
import FeedbackButtons from "./FeedbackButtons";
import MovieCard from "./MovieCard";
import RichText from "./RichText";

interface Props {
  mensagem: Mensagem;
  /** Última mensagem do agente numa conversa aberta: mostra os botões de decisão. */
  ativa: boolean;
  onConfirmar: (filme: Candidato) => void;
  onRecusar: (filmes: Candidato[]) => void;
  onRepetir: () => void;
}

export function Avatar() {
  return (
    <div
      aria-hidden
      className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-marquee/40 bg-film text-sm"
    >
      🕵️
    </div>
  );
}

const btnSim =
  "rounded-md bg-marquee px-3 py-1.5 text-xs font-semibold text-ink transition hover:bg-marquee-deep";
const btnNao =
  "rounded-md border border-line px-3 py-1.5 text-xs text-paper/80 transition hover:border-nope/60 hover:text-nope";

export default function MessageBubble({ mensagem: m, ativa, onConfirmar, onRecusar, onRepetir }: Props) {
  if (m.papel === "user") {
    return (
      <div className="animate-rise flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-reel px-4 py-2.5 text-[15px] leading-relaxed text-paper sm:max-w-[75%]">
          {m.conteudo}
        </div>
      </div>
    );
  }

  if (m.tipo === "confirmacao") {
    return (
      <div className="animate-rise mx-auto flex items-center gap-2 rounded-full border border-ok/30 bg-ok/10 px-4 py-1.5 text-xs text-ok">
        <span aria-hidden>✔</span>
        {m.conteudo}
      </div>
    );
  }

  if (m.tipo === "erro") {
    return (
      <div className="animate-rise flex gap-3">
        <Avatar />
        <div className="flex flex-col items-start gap-2 rounded-2xl rounded-tl-sm border border-nope/30 bg-nope/10 px-4 py-2.5 text-sm text-nope">
          {m.conteudo}
          {ativa && (
            <button onClick={onRepetir} className="rounded-md border border-nope/40 px-2.5 py-1 text-xs hover:bg-nope/15">
              ↻ Tentar de novo
            </button>
          )}
        </div>
      </div>
    );
  }

  const varios = m.candidatos.length > 1;

  return (
    <div className="animate-rise flex gap-3">
      <Avatar />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div
          className={`text-[15px] leading-relaxed ${
            m.tipo === "pergunta"
              ? "rounded-2xl rounded-tl-sm border border-marquee/40 bg-marquee/10 px-4 py-2.5"
              : "pt-1"
          }`}
        >
          {m.tipo === "pergunta" && (
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-marquee">
              Pergunta do detetive
            </span>
          )}
          <RichText texto={m.conteudo} />
        </div>

        {m.candidatos.length > 0 && (
          <div className={`grid gap-2 ${varios ? "sm:grid-cols-1" : ""}`}>
            {m.candidatos.map((c, i) => (
              <MovieCard
                key={c.tmdb_id}
                filme={c}
                destaque={i === 0}
                acoes={
                  ativa && (
                    <>
                      <button className={btnSim} onClick={() => onConfirmar(c)}>
                        É esse!
                      </button>
                      {!varios && (
                        <button className={btnNao} onClick={() => onRecusar([c])}>
                          Não é esse
                        </button>
                      )}
                    </>
                  )
                }
              />
            ))}
            {ativa && varios && (
              <button className={`${btnNao} self-start`} onClick={() => onRecusar(m.candidatos)}>
                Nenhum desses
              </button>
            )}
          </div>
        )}

        <FeedbackButtons mensagem={m} />
      </div>
    </div>
  );
}
