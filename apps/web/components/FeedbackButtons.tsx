"use client";

import { useState } from "react";
import { enviarFeedback } from "@/lib/agent-client";
import { db, mensagensDa } from "@/lib/db";
import { obterSessao } from "@/lib/session";
import type { Mensagem } from "@/lib/types";

const NENHUM = "nenhum";

export default function FeedbackButtons({ mensagem }: { mensagem: Mensagem }) {
  const [aberto, setAberto] = useState(false);
  const [correto, setCorreto] = useState<string>(NENHUM);
  const [comentario, setComentario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(rating: 1 | -1) {
    setEnviando(true);
    setErro(null);
    try {
      const { session_id } = await obterSessao();
      // A descrição é o que o usuário escreveu até esta resposta; vira caso de teste nos evals.
      const descricao = (await mensagensDa(mensagem.conversa_id))
        .filter((m) => m.papel === "user" && m.criada_em <= mensagem.criada_em)
        .map((m) => m.conteudo)
        .join("\n");
      await enviarFeedback({
        session_id,
        trace_id: mensagem.trace_id,
        descricao,
        rating,
        correct_tmdb_id: rating === -1 && correto !== NENHUM ? Number(correto) : null,
        comment: comentario.trim() || null,
      });
      await db.mensagens.update(mensagem.id, { feedback: rating });
      setAberto(false);
    } catch {
      setErro("Não consegui enviar agora. Tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  if (mensagem.feedback != null) {
    return (
      <p className="text-[11px] text-muted">
        {mensagem.feedback === 1 ? "👍" : "👎"} Obrigado pelo retorno.
      </p>
    );
  }

  const botao =
    "rounded-md px-1.5 py-0.5 text-sm text-muted transition hover:bg-reel hover:text-paper disabled:opacity-40";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <span className="mr-1 text-[11px] text-muted">A resposta ajudou?</span>
        <button className={botao} onClick={() => enviar(1)} disabled={enviando} aria-label="Resposta boa">
          👍
        </button>
        <button
          className={`${botao} ${aberto ? "bg-reel text-paper" : ""}`}
          onClick={() => setAberto((a) => !a)}
          disabled={enviando}
          aria-label="Resposta ruim"
          aria-expanded={aberto}
        >
          👎
        </button>
      </div>

      {aberto && (
        <form
          className="animate-rise flex flex-col gap-2 rounded-lg border border-line bg-film p-3 text-xs"
          onSubmit={(e) => {
            e.preventDefault();
            enviar(-1);
          }}
        >
          {mensagem.candidatos.length > 0 && (
            <label className="flex flex-col gap-1">
              <span className="text-muted">Qual era o filme certo?</span>
              <select
                value={correto}
                onChange={(e) => setCorreto(e.target.value)}
                className="rounded-md border border-line bg-reel px-2 py-1.5 text-paper"
              >
                <option value={NENHUM}>Nenhum destes / não sei</option>
                {mensagem.candidatos.map((c) => (
                  <option key={c.tmdb_id} value={c.tmdb_id}>
                    {c.titulo} {c.ano ? `(${c.ano})` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-muted">O que deu errado? (opcional)</span>
            <textarea
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Ex.: o filme certo é Contato, de 1997"
              className="resize-none rounded-md border border-line bg-reel px-2 py-1.5 text-paper placeholder:text-muted/60"
            />
          </label>
          <p className="leading-relaxed text-muted">
            🔒 Sua descrição do filme será guardada <strong className="text-paper/80">de forma anônima</strong> para
            testar e melhorar o CineDetetive. Não guardamos nome, e-mail nem o resto do histórico.
          </p>
          {erro && <p className="text-nope">{erro}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setAberto(false)} className="rounded-md px-3 py-1.5 text-muted hover:text-paper">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={enviando}
              className="rounded-md bg-marquee px-3 py-1.5 font-medium text-ink hover:bg-marquee-deep disabled:opacity-50"
            >
              {enviando ? "Enviando…" : "Enviar"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
