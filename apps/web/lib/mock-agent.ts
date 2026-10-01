// Agente SIMULADO: existe só para o front funcionar antes do backend.
// Ele imita o contrato SSE real (status → candidates/clarification → token → final),
// mas a "busca" é uma contagem de palavras-chave num catálogo minúsculo.
// Quando apps/agent estiver de pé, defina NEXT_PUBLIC_AGENT_URL e este arquivo deixa de ser usado.

import type {
  AgentEvent,
  Candidato,
  ChatRequest,
  Confianca,
  EstadoBusca,
  FeedbackRequest,
  Filtros,
} from "./types";

interface FilmeMock extends Candidato {
  palavras: string[];
}

const CATALOGO: FilmeMock[] = [
  {
    tmdb_id: 137,
    titulo: "Feitiço do Tempo",
    titulo_original: "Groundhog Day",
    ano: 1993,
    diretor: "Harold Ramis",
    elenco: ["Bill Murray", "Andie MacDowell", "Chris Elliott"],
    generos: ["Comédia", "Romance", "Fantasia"],
    trecho: "A weatherman finds himself living the same day over and over again in Punxsutawney.",
    palavras: ["mesmo dia", "repete", "marmota", "acorda", "loop", "repórter", "previsão do tempo", "neve"],
  },
  {
    tmdb_id: 137113,
    titulo: "No Limite do Amanhã",
    titulo_original: "Edge of Tomorrow",
    ano: 2014,
    diretor: "Doug Liman",
    elenco: ["Tom Cruise", "Emily Blunt", "Bill Paxton"],
    generos: ["Ação", "Ficção científica"],
    trecho: "A soldier fighting aliens gets to relive the same day over and over again.",
    palavras: ["mesmo dia", "repete", "morre", "alienígena", "alien", "guerra", "soldado", "loop", "tom cruise"],
  },
  {
    tmdb_id: 27205,
    titulo: "A Origem",
    titulo_original: "Inception",
    ano: 2010,
    diretor: "Christopher Nolan",
    elenco: ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
    generos: ["Ação", "Ficção científica", "Suspense"],
    trecho: "A thief who steals secrets by entering dreams is given the task of planting an idea.",
    palavras: ["sonho", "pião", "invadir", "mente", "camadas", "ideia", "dicaprio", "nolan"],
  },
  {
    tmdb_id: 603,
    titulo: "Matrix",
    titulo_original: "The Matrix",
    ano: 1999,
    diretor: "Lana e Lilly Wachowski",
    elenco: ["Keanu Reeves", "Laurence Fishburne", "Carrie-Anne Moss"],
    generos: ["Ação", "Ficção científica"],
    trecho: "A hacker learns that the world is a simulation run by machines.",
    palavras: ["pílula", "simulação", "máquinas", "hacker", "realidade", "vermelha", "keanu", "bala"],
  },
  {
    tmdb_id: 157336,
    titulo: "Interestelar",
    titulo_original: "Interstellar",
    ano: 2014,
    diretor: "Christopher Nolan",
    elenco: ["Matthew McConaughey", "Anne Hathaway", "Jessica Chastain"],
    generos: ["Aventura", "Drama", "Ficção científica"],
    trecho: "Explorers travel through a wormhole in space to find a new home for humanity.",
    palavras: ["espaço", "buraco negro", "planeta", "filha", "astronauta", "poeira", "estante", "nolan"],
  },
  {
    tmdb_id: 862,
    titulo: "Toy Story",
    titulo_original: "Toy Story",
    ano: 1995,
    diretor: "John Lasseter",
    elenco: ["Tom Hanks", "Tim Allen", "Don Rickles"],
    generos: ["Animação", "Comédia", "Família"],
    trecho: "A cowboy doll feels threatened when a new spaceman toy arrives.",
    palavras: ["brinquedo", "boneco", "cowboy", "astronauta", "animação", "desenho", "pixar"],
  },
  {
    tmdb_id: 598,
    titulo: "Cidade de Deus",
    titulo_original: "Cidade de Deus",
    ano: 2002,
    diretor: "Fernando Meirelles",
    elenco: ["Alexandre Rodrigues", "Leandro Firmino", "Phellipe Haagensen"],
    generos: ["Drama", "Crime"],
    trecho: "Two boys grow up in a violent Rio favela; one becomes a photographer, the other a drug dealer.",
    palavras: ["favela", "rio", "fotógrafo", "tráfico", "brasileiro", "galinha", "gangue"],
  },
  {
    tmdb_id: 37165,
    titulo: "O Show de Truman",
    titulo_original: "The Truman Show",
    ano: 1998,
    diretor: "Peter Weir",
    elenco: ["Jim Carrey", "Laura Linney", "Ed Harris"],
    generos: ["Comédia", "Drama"],
    trecho: "A man discovers his whole life is a reality TV show watched by millions.",
    palavras: ["reality", "câmera", "programa", "cidade falsa", "barco", "filmada", "jim carrey"],
  },
  {
    tmdb_id: 329,
    titulo: "Jurassic Park: O Parque dos Dinossauros",
    titulo_original: "Jurassic Park",
    ano: 1993,
    diretor: "Steven Spielberg",
    elenco: ["Sam Neill", "Laura Dern", "Jeff Goldblum"],
    generos: ["Aventura", "Ficção científica"],
    trecho: "Cloned dinosaurs escape in a theme park on a remote island.",
    palavras: ["dinossauro", "parque", "ilha", "clone", "spielberg", "t-rex"],
  },
  {
    tmdb_id: 38,
    titulo: "Brilho Eterno de uma Mente sem Lembranças",
    titulo_original: "Eternal Sunshine of the Spotless Mind",
    ano: 2004,
    diretor: "Michel Gondry",
    elenco: ["Jim Carrey", "Kate Winslet", "Kirsten Dunst"],
    generos: ["Drama", "Romance", "Ficção científica"],
    trecho: "A couple undergo a procedure to erase each other from their memories.",
    palavras: ["memória", "apagar", "esquecer", "ex", "namorada", "lembranças", "jim carrey"],
  },
];

const FORA_DO_ESCOPO = /\b(receita|piada|futebol|presidente|programar|bolo|cotação|horóscopo)\b/i;

const PERGUNTAS = [
  "Você lembra mais ou menos a década? Anos 90, 2000, mais recente?",
  "Lembra de algum ator, diretor ou de uma cena bem marcante?",
  "Era animação, comédia, drama, ação ou ficção científica?",
];

function esperar(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Abortado", "AbortError"));
    });
  });
}

function extrairFiltros(texto: string, atuais: Filtros): Filtros {
  const f: Filtros = { ...atuais };
  const decada = texto.match(/anos\s+(\d0)\b/i);
  if (decada) {
    const d = Number(decada[1]);
    const inicio = d >= 30 ? 1900 + d : 2000 + d;
    f.ano_min = inicio;
    f.ano_max = inicio + 9;
  }
  if (/\b(recente|mais novo|novo)\b/i.test(texto)) {
    f.ano_min = Math.max(f.ano_min ?? 0, 2000);
    f.ano_max = null;
  }
  if (/\b(antigo|velho)\b/i.test(texto)) {
    f.ano_max = Math.min(f.ano_max ?? 9999, 1999);
  }
  return f;
}

function pontuar(texto: string, filme: FilmeMock) {
  const t = texto.toLowerCase();
  return filme.palavras.filter((p) => t.includes(p)).length;
}

async function* digitar(texto: string, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  const pedacos = texto.match(/\S+\s*/g) ?? [];
  for (const p of pedacos) {
    await esperar(28, signal);
    yield { type: "token", data: { texto: p } };
  }
}

function semPalavras(f: FilmeMock): Candidato {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { palavras, ...c } = f;
  return c;
}

export async function* mockChat(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  const traceId = `mock-${crypto.randomUUID().slice(0, 8)}`;

  yield { type: "status", data: { etapa: "Entendendo o pedido" } };
  await esperar(500, signal);

  if (FORA_DO_ESCOPO.test(req.mensagem)) {
    yield* digitar(
      "Eu só sei investigar filmes 🕵️ Me conta o que você lembra de um filme — uma cena, a época, um ator — que eu tento descobrir qual é.",
      signal,
    );
    yield { type: "final", data: { filme: null, confianca: null, estado: req.estado, trace_id: traceId } };
    return;
  }

  // O agente real usa o histórico inteiro para reescrever a consulta; aqui só juntamos as falas.
  const falas = [...req.historico.filter((m) => m.papel === "user").map((m) => m.conteudo), req.mensagem].join(" ");
  const filtros = extrairFiltros(req.mensagem, req.estado.filtros);
  const estado: EstadoBusca = { ...req.estado, filtros };

  yield { type: "status", data: { etapa: "Buscando sinopses" } };
  await esperar(700, signal);

  const ranking = CATALOGO.filter((f) => !estado.excluidos.includes(f.tmdb_id))
    .filter((f) => (filtros.ano_min ? (f.ano ?? 0) >= filtros.ano_min : true))
    .filter((f) => (filtros.ano_max ? (f.ano ?? 0) <= filtros.ano_max : true))
    .map((f) => ({ f, nota: pontuar(falas, f) }))
    .sort((a, b) => b.nota - a.nota);

  yield { type: "status", data: { etapa: "Reordenando candidatos" } };
  await esperar(500, signal);
  yield { type: "status", data: { etapa: "Consultando TMDB" } };
  await esperar(600, signal);
  yield { type: "status", data: { etapa: "Avaliando confiança" } };
  await esperar(400, signal);

  const [p1, p2] = ranking;
  const n1 = p1?.nota ?? 0;
  const n2 = p2?.nota ?? 0;

  let confianca: Confianca = n1 >= 3 && n1 - n2 >= 2 ? "alta" : n1 >= 1 ? "media" : "baixa";
  if (confianca === "baixa" && estado.perguntas_feitas >= 3) confianca = "media";

  const total = Math.max(1, ranking.slice(0, 3).reduce((s, r) => s + r.nota, 0));
  const comNota = (r: (typeof ranking)[number]): Candidato => ({
    ...semPalavras(r.f),
    confianca: Number((r.nota / total).toFixed(2)) || 0.05,
  });

  if (confianca === "baixa") {
    const pergunta = PERGUNTAS[estado.perguntas_feitas] ?? PERGUNTAS[0];
    const novoEstado = { ...estado, perguntas_feitas: estado.perguntas_feitas + 1 };
    yield { type: "clarification", data: { pergunta } };
    yield* digitar(`Ainda não tenho uma pista boa. ${pergunta}`, signal);
    yield { type: "final", data: { filme: null, confianca, estado: novoEstado, trace_id: traceId } };
    return;
  }

  if (ranking.length === 0) {
    yield* digitar("Não sobrou nenhum filme com esses filtros no meu catálogo de teste. Tente descrever de outro jeito.", signal);
    yield { type: "final", data: { filme: null, confianca: "baixa", estado, trace_id: traceId } };
    return;
  }

  if (confianca === "alta") {
    const filme = { ...comNota(p1), confianca: 0.9 };
    yield { type: "candidates", data: { candidatos: [filme] } };
    yield* digitar(
      `Acho que é **${filme.titulo}** (${filme.titulo_original}, ${filme.ano}), de ${filme.diretor}. A sinopse bate com o que você descreveu. É esse?`,
      signal,
    );
    yield { type: "final", data: { filme, confianca, estado, trace_id: traceId } };
    return;
  }

  const top3 = ranking.slice(0, 3).map(comNota);
  yield { type: "candidates", data: { candidatos: top3 } };
  yield* digitar(
    `Não tenho certeza, mas estes são os mais prováveis. O primeiro é **${top3[0].titulo}** (${top3[0].ano}). Algum deles é o seu?`,
    signal,
  );
  yield { type: "final", data: { filme: null, confianca, estado, trace_id: traceId } };
}

export async function mockFeedback(body: FeedbackRequest): Promise<void> {
  await esperar(300);
  console.info("[mock] feedback recebido", body);
}
