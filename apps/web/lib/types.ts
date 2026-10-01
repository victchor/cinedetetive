// Contrato entre o front e o agente (apps/agent).
// Estes tipos espelham os schemas Pydantic que o FastAPI vai validar.

export type Papel = "user" | "assistant";
export type Confianca = "alta" | "media" | "baixa";

export interface Filtros {
  ano_min?: number | null;
  ano_max?: number | null;
  generos?: string[];
  pessoas?: string[];
}

/** Estado da busca: vai e volta entre navegador e agente a cada mensagem. */
export interface EstadoBusca {
  filtros: Filtros;
  excluidos: number[]; // tmdb_id dos filmes recusados
  perguntas_feitas: number;
}

export const ESTADO_INICIAL: EstadoBusca = {
  filtros: {},
  excluidos: [],
  perguntas_feitas: 0,
};

export interface Candidato {
  tmdb_id: number;
  titulo: string; // título em português
  titulo_original?: string;
  ano?: number | null;
  poster_url?: string | null;
  diretor?: string | null;
  elenco?: string[];
  generos?: string[];
  confianca?: number; // 0..1
  trecho?: string | null; // trecho da sinopse que casou
}

// ---------- POST /v1/chat ----------

export interface MensagemHistorico {
  papel: Papel;
  conteudo: string;
}

export interface ChatRequest {
  session_id: string;
  conversa_id: string;
  mensagem: string;
  historico: MensagemHistorico[];
  estado: EstadoBusca;
}

// ---------- Eventos SSE ----------
// No fio: "event: <tipo>\ndata: <json>\n\n"

export interface EventPayloads {
  status: { etapa: string };
  token: { texto: string };
  candidates: { candidatos: Candidato[] };
  clarification: { pergunta: string };
  final: {
    filme: Candidato | null;
    confianca: Confianca | null;
    estado: EstadoBusca;
    trace_id: string | null;
  };
  error: { codigo: string; mensagem: string };
}

export type AgentEventType = keyof EventPayloads;

export type AgentEvent = {
  [K in AgentEventType]: { type: K; data: EventPayloads[K] };
}[AgentEventType];

// ---------- POST /v1/feedback ----------

export interface FeedbackRequest {
  session_id: string;
  trace_id: string | null;
  descricao: string;
  rating: 1 | -1;
  correct_tmdb_id: number | null;
  comment: string | null;
}

// ---------- IndexedDB ----------

export interface Sessao {
  session_id: string;
  criada_em: number;
  persistente: boolean;
}

export interface Conversa {
  id: string;
  titulo: string;
  status: "aberta" | "resolvida";
  filme_resolvido: Candidato | null;
  estado: EstadoBusca;
  criada_em: number;
  atualizada_em: number;
}

export type TipoMensagem = "texto" | "resposta" | "pergunta" | "erro" | "confirmacao";

export interface Mensagem {
  id: string;
  conversa_id: string;
  papel: Papel;
  conteudo: string;
  tipo: TipoMensagem;
  candidatos: Candidato[];
  filme: Candidato | null;
  confianca: Confianca | null;
  trace_id: string | null;
  feedback: 1 | -1 | null;
  criada_em: number;
}
