import { mockChat, mockFeedback } from "./mock-agent";
import type { AgentEvent, AgentEventType, ChatRequest, FeedbackRequest } from "./types";

export const AGENT_URL = (process.env.NEXT_PUBLIC_AGENT_URL ?? "").replace(/\/$/, "");

/** Sem URL do agente, ou com NEXT_PUBLIC_USE_MOCK=true, o front usa o agente simulado. */
export const USANDO_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true" || AGENT_URL === "";

const TIPOS: AgentEventType[] = ["status", "token", "candidates", "clarification", "final", "error"];

export class AgentError extends Error {
  constructor(
    public codigo: string,
    mensagem: string,
  ) {
    super(mensagem);
  }
}

/**
 * Envia a mensagem ao agente e entrega cada evento SSE em ordem.
 * EventSource só faz GET, por isso o stream é lido manualmente a partir do fetch.
 */
export async function* streamChat(
  req: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
  if (USANDO_MOCK) {
    yield* mockChat(req, signal);
    return;
  }

  let resp: Response;
  try {
    resp = await fetch(`${AGENT_URL}/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new AgentError("agente_offline", "Não consegui falar com o agente. Ele está rodando?");
  }

  if (!resp.ok || !resp.body) {
    throw await erroHttp(resp);
  }

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;

    // Cada evento termina com uma linha em branco.
    const blocos = buffer.split(/\r?\n\r?\n/);
    buffer = blocos.pop() ?? "";
    for (const bloco of blocos) {
      const evento = parseBloco(bloco);
      if (evento) yield evento;
    }
  }

  const resto = parseBloco(buffer);
  if (resto) yield resto;
}

function parseBloco(bloco: string): AgentEvent | null {
  let tipo = "message";
  const dados: string[] = [];
  for (const linha of bloco.split(/\r?\n/)) {
    if (linha.startsWith(":")) continue; // comentário / keep-alive
    if (linha.startsWith("event:")) tipo = linha.slice(6).trim();
    else if (linha.startsWith("data:")) dados.push(linha.slice(5).replace(/^ /, ""));
  }
  if (dados.length === 0 || !TIPOS.includes(tipo as AgentEventType)) return null;
  try {
    return { type: tipo, data: JSON.parse(dados.join("\n")) } as AgentEvent;
  } catch {
    console.warn("Evento SSE com JSON inválido:", bloco);
    return null;
  }
}

async function erroHttp(resp: Response): Promise<AgentError> {
  if (resp.status === 429) {
    return new AgentError("limite", "Muitas mensagens em pouco tempo. Espere um minuto e tente de novo.");
  }
  if (resp.status === 422) {
    return new AgentError("invalido", "A mensagem ficou grande demais ou o histórico está inválido.");
  }
  return new AgentError(`http_${resp.status}`, "O agente respondeu com erro. Tente de novo.");
}

export async function enviarFeedback(body: FeedbackRequest): Promise<void> {
  if (USANDO_MOCK) return mockFeedback(body);
  const resp = await fetch(`${AGENT_URL}/v1/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await erroHttp(resp);
}
