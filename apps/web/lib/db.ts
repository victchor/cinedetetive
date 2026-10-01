import Dexie, { type EntityTable } from "dexie";
import {
  ESTADO_INICIAL,
  type Candidato,
  type Conversa,
  type EstadoBusca,
  type Mensagem,
  type Sessao,
} from "./types";

// Banco "cinedetetive" no IndexedDB do navegador. O servidor não guarda conversas.
export const db = new Dexie("cinedetetive") as Dexie & {
  sessao: EntityTable<Sessao, "session_id">;
  conversas: EntityTable<Conversa, "id">;
  mensagens: EntityTable<Mensagem, "id">;
};

db.version(1).stores({
  sessao: "&session_id",
  conversas: "&id, atualizada_em",
  mensagens: "&id, conversa_id, [conversa_id+criada_em]",
});

export function tituloDe(texto: string): string {
  const limpo = texto.trim().replace(/\s+/g, " ");
  return limpo.length > 48 ? `${limpo.slice(0, 47)}…` : limpo;
}

export async function criarConversa(primeiraMensagem: string): Promise<Conversa> {
  const agora = Date.now();
  const conversa: Conversa = {
    id: crypto.randomUUID(),
    titulo: tituloDe(primeiraMensagem),
    status: "aberta",
    filme_resolvido: null,
    estado: structuredClone(ESTADO_INICIAL),
    criada_em: agora,
    atualizada_em: agora,
  };
  await db.conversas.add(conversa);
  return conversa;
}

export async function adicionarMensagem(
  m: Omit<Mensagem, "id" | "criada_em" | "candidatos" | "filme" | "confianca" | "trace_id" | "feedback"> &
    Partial<Mensagem>,
): Promise<Mensagem> {
  const msg: Mensagem = {
    id: crypto.randomUUID(),
    criada_em: Date.now(),
    candidatos: [],
    filme: null,
    confianca: null,
    trace_id: null,
    feedback: null,
    ...m,
  };
  await db.transaction("rw", db.mensagens, db.conversas, async () => {
    await db.mensagens.add(msg);
    await db.conversas.update(m.conversa_id, { atualizada_em: msg.criada_em });
  });
  return msg;
}

export function mensagensDa(conversaId: string) {
  return db.mensagens
    .where("[conversa_id+criada_em]")
    .between([conversaId, Dexie.minKey], [conversaId, Dexie.maxKey])
    .toArray();
}

export async function atualizarEstado(conversaId: string, estado: EstadoBusca) {
  await db.conversas.update(conversaId, { estado, atualizada_em: Date.now() });
}

export async function marcarResolvida(conversaId: string, filme: Candidato) {
  await db.conversas.update(conversaId, {
    status: "resolvida",
    filme_resolvido: filme,
    atualizada_em: Date.now(),
  });
}

export async function reabrir(conversaId: string) {
  await db.conversas.update(conversaId, { status: "aberta", filme_resolvido: null });
}

export async function apagarConversa(conversaId: string) {
  await db.transaction("rw", db.mensagens, db.conversas, async () => {
    await db.mensagens.where("conversa_id").equals(conversaId).delete();
    await db.conversas.delete(conversaId);
  });
}
