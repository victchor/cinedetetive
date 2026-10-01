"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { AgentError, streamChat } from "./agent-client";
import {
  adicionarMensagem,
  atualizarEstado,
  criarConversa,
  db,
  marcarResolvida,
  mensagensDa,
  reabrir,
} from "./db";
import { obterSessao } from "./session";
import type { Candidato, Confianca, Mensagem, MensagemHistorico } from "./types";

export const LIMITE_MENSAGEM = 1000;
const LIMITE_HISTORICO = 10;

/** O que está chegando do agente agora, antes de virar mensagem no IndexedDB. */
export interface Rascunho {
  conversaId: string;
  etapa: string | null;
  texto: string;
  candidatos: Candidato[];
  pergunta: string | null;
}

function paraHistorico(msgs: Mensagem[]): MensagemHistorico[] {
  return msgs
    .filter((m) => m.tipo !== "erro" && m.tipo !== "confirmacao")
    .slice(-LIMITE_HISTORICO)
    .map((m) => ({ papel: m.papel, conteudo: m.conteudo }));
}

export function useChat() {
  const router = useRouter();
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const executar = useCallback(
    async (texto: string, conversaIdAtual: string | null, opts: { excluir?: number[]; repetir?: boolean } = {}) => {
      const mensagem = texto.trim().slice(0, LIMITE_MENSAGEM);
      if (!mensagem || abortRef.current) return;

      const sessao = await obterSessao();

      let conversa = conversaIdAtual ? await db.conversas.get(conversaIdAtual) : undefined;
      if (!conversa) {
        conversa = await criarConversa(mensagem);
        router.replace(`/c/${conversa.id}`);
      } else if (conversa.status === "resolvida") {
        await reabrir(conversa.id);
      }
      const conversaId = conversa.id;

      const estado = structuredClone(conversa.estado);
      const novos = (opts.excluir ?? []).filter((id) => !estado.excluidos.includes(id));
      if (novos.length) {
        estado.excluidos.push(...novos);
        await atualizarEstado(conversaId, estado);
      }

      let anteriores = await mensagensDa(conversaId);
      if (opts.repetir) {
        // Remove as mensagens de erro e a última fala do usuário (ela é reenviada como "mensagem").
        const ultimaUser = anteriores.findLastIndex((m) => m.papel === "user");
        const erros = anteriores.slice(ultimaUser + 1).filter((m) => m.tipo === "erro");
        await db.mensagens.bulkDelete(erros.map((m) => m.id));
        anteriores = anteriores.slice(0, ultimaUser);
      } else {
        await adicionarMensagem({ conversa_id: conversaId, papel: "user", conteudo: mensagem, tipo: "texto" });
      }

      const controller = new AbortController();
      abortRef.current = controller;
      let atual: Rascunho = { conversaId, etapa: "Enviando", texto: "", candidatos: [], pergunta: null };
      setRascunho(atual);
      const atualizar = (parcial: Partial<Rascunho>) => {
        atual = { ...atual, ...parcial };
        setRascunho(atual);
      };

      let terminou = false;
      try {
        const eventos = streamChat(
          {
            session_id: sessao.session_id,
            conversa_id: conversaId,
            mensagem,
            historico: paraHistorico(anteriores),
            estado,
          },
          controller.signal,
        );

        for await (const ev of eventos) {
          switch (ev.type) {
            case "status":
              atualizar({ etapa: ev.data.etapa });
              break;
            case "token":
              atualizar({ etapa: null, texto: atual.texto + ev.data.texto });
              break;
            case "candidates":
              atualizar({ candidatos: ev.data.candidatos });
              break;
            case "clarification":
              atualizar({ pergunta: ev.data.pergunta });
              break;
            case "error":
              throw new AgentError(ev.data.codigo, ev.data.mensagem);
            case "final": {
              terminou = true;
              const { filme, confianca, estado: novoEstado, trace_id } = ev.data;
              const candidatos = atual.candidatos.length ? atual.candidatos : filme ? [filme] : [];
              await adicionarMensagem({
                conversa_id: conversaId,
                papel: "assistant",
                conteudo: atual.texto || atual.pergunta || "",
                tipo: atual.pergunta ? "pergunta" : "resposta",
                candidatos,
                filme,
                confianca: confianca as Confianca | null,
                trace_id,
              });
              await atualizarEstado(conversaId, novoEstado);
              break;
            }
          }
        }
        if (!terminou) throw new AgentError("stream_incompleto", "A resposta foi interrompida no meio. Tente de novo.");
      } catch (e) {
        if (controller.signal.aborted) {
          if (atual.texto) {
            await adicionarMensagem({
              conversa_id: conversaId,
              papel: "assistant",
              conteudo: `${atual.texto} …(interrompido)`,
              tipo: "resposta",
              candidatos: atual.candidatos,
            });
          }
        } else {
          const msg = e instanceof AgentError ? e.message : "Algo deu errado. Tente de novo.";
          console.error(e);
          await adicionarMensagem({ conversa_id: conversaId, papel: "assistant", conteudo: msg, tipo: "erro" });
        }
      } finally {
        abortRef.current = null;
        setRascunho(null);
      }
    },
    [router],
  );

  const enviar = useCallback((texto: string, conversaId: string | null) => executar(texto, conversaId), [executar]);

  const repetir = useCallback(
    async (conversaId: string) => {
      const msgs = await mensagensDa(conversaId);
      const ultima = msgs.findLast((m) => m.papel === "user");
      if (ultima) await executar(ultima.conteudo, conversaId, { repetir: true });
    },
    [executar],
  );

  /** "Não é esse" / "Nenhum desses": o front já marca os filmes como excluídos no estado. */
  const recusar = useCallback(
    (conversaId: string, filmes: Candidato[]) => {
      const texto =
        filmes.length === 1 ? `Não é esse (${filmes[0].titulo}).` : `Nenhum desses (${filmes.map((f) => f.titulo).join(", ")}).`;
      return executar(texto, conversaId, { excluir: filmes.map((f) => f.tmdb_id) });
    },
    [executar],
  );

  const confirmar = useCallback(async (conversaId: string, filme: Candidato) => {
    await marcarResolvida(conversaId, filme);
    await adicionarMensagem({
      conversa_id: conversaId,
      papel: "assistant",
      conteudo: `Caso encerrado: ${filme.titulo}${filme.ano ? ` (${filme.ano})` : ""}. 🎬`,
      tipo: "confirmacao",
      filme,
    });
  }, []);

  const parar = useCallback(() => abortRef.current?.abort(), []);

  return { rascunho, ocupado: rascunho !== null, enviar, repetir, recusar, confirmar, parar };
}
