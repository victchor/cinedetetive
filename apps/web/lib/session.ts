import { db } from "./db";
import type { Sessao } from "./types";

let emAndamento: Promise<Sessao> | null = null;

/**
 * Devolve a sessão anônima deste navegador, criando-a na primeira visita.
 * Também pede ao navegador para não apagar o IndexedDB (storage.persist).
 */
export function obterSessao(): Promise<Sessao> {
  emAndamento ??= (async () => {
    const existente = await db.sessao.toCollection().first();
    const persistente = await pedirPersistencia();

    if (existente) {
      if (existente.persistente !== persistente) {
        await db.sessao.update(existente.session_id, { persistente });
      }
      return { ...existente, persistente };
    }

    const nova: Sessao = {
      session_id: crypto.randomUUID(),
      criada_em: Date.now(),
      persistente,
    };
    await db.sessao.add(nova);
    return nova;
  })();
  return emAndamento;
}

async function pedirPersistencia(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.storage?.persist) return false;
  try {
    if (await navigator.storage.persisted()) return true;
    return await navigator.storage.persist();
  } catch {
    return false;
  }
}

/** Safari apaga dados de sites não visitados em ~7 dias. */
export function ehSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  return /Safari\//.test(ua) && !/Chrome\/|Chromium\/|CriOS\/|Edg\/|Android/.test(ua);
}
