"""Busca híbrida: trechos por SENTIDO (vetor) + trechos por PALAVRAS (tsvector) → RRF → filmes.

    consulta ──► embedding ──► 40 trechos mais próximos (HNSW, distância de cosseno) ──┐
             └───────────────► 40 trechos que mais casam por palavras (GIN, ts_rank) ──┤
                                                                                       ▼
                                                  RRF: junta as duas listas pela posição
                                                                                       ▼
                        agrupa por filme, tira os recusados → os 10 filmes mais prováveis

Os números (40, 40, 10) são pontos de partida: o eval do passo 6 é que diz se devem mudar.
"""

from collections import defaultdict
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from cinedetetive.rag.embeddings import embed_consulta
from cinedetetive.rag.fusion import rrf

TRECHOS_POR_BUSCA = 40
EF_SEARCH = 100  # candidatos que o HNSW examina; o padrão (40) deixou o Groundhog Day de fora
TOTAL_TRECHOS_APROX = 116_518  # para o corte de palavras comuns (5% dos trechos)


class Filtros(BaseModel):
    """Restrições extraídas da fala do usuário ("anos 90", "ficção científica"...)."""

    ano_min: int | None = None
    ano_max: int | None = None
    generos: list[str] = Field(default_factory=list)


class Candidato(BaseModel):
    movie_id: int
    tmdb_id: int | None
    titulo: str
    ano: int
    nota: float                    # soma (ou máximo) das notas RRF dos trechos do filme
    trecho: str                    # o trecho que mais contribuiu: mostra POR QUE o filme veio
    posicao_vetor: int | None      # melhor posição de um trecho do filme na busca por sentido
    posicao_texto: int | None      # e na busca por palavras (None = não apareceu)


class Resultado(BaseModel):
    candidatos: list[Candidato]
    etapas: dict[str, int]         # quantos itens entraram/saíram de cada etapa (para depurar)


# Filtros comuns às duas buscas. %(x)s vira parâmetro do psycopg (nunca concatenar texto do usuário no SQL).
FILTROS_SQL = """
      (%(ano_min)s::int IS NULL OR c.year >= %(ano_min)s)
  AND (%(ano_max)s::int IS NULL OR c.year <= %(ano_max)s)
  AND (cardinality(%(generos)s::text[]) = 0 OR c.genres && %(generos)s::text[])
  AND NOT EXISTS (
        SELECT 1 FROM rag.movies m
        WHERE m.id = c.movie_id AND m.tmdb_id = ANY(%(excluir)s::int[]))
"""

# iterative_scan: com filtros, o HNSW continua procurando até achar 40 trechos que passem
# no WHERE (sem isso, ele examina ef_search candidatos, filtra, e pode sobrar menos de 40).
# relaxed_order deixa a ordem levemente fora; o ORDER BY de fora reordena.
SQL_VETOR = f"""
WITH proximos AS MATERIALIZED (
    SELECT c.id, c.movie_id, c.embedding <=> %(vetor)s AS distancia
    FROM rag.movie_chunks c
    WHERE {FILTROS_SQL}
    ORDER BY c.embedding <=> %(vetor)s
    LIMIT %(limite)s
)
SELECT id, movie_id FROM proximos ORDER BY distancia
"""

# Busca por palavras com peso de raridade (IDF), que o ts_rank do Postgres não tem.
#   1. a consulta vira lexemas ("relives" → "reliv") e cada um ganha seu IDF (tabela rag.lexemes)
#   2. palavras em mais de 5% dos trechos ("day", "man") saem: casam com tudo e só trazem ruído
#   3. o trecho casa se tiver QUALQUER palavra restante (OU); a nota é a soma do IDF das que casou
# Assim um trecho com "groundhog" (IDF 9,3) passa na frente de dez trechos com "day" (IDF 1,9).
MAX_FRACAO_TRECHOS = 0.05

SQL_TEXTO = f"""
WITH termos AS (
    SELECT l.word, l.idf
    FROM unnest(tsvector_to_array(to_tsvector('english', %(texto)s))) AS t(word)
    JOIN rag.lexemes l ON l.word = t.word
    WHERE l.ndoc <= %(max_ndoc)s
),
q AS (
    SELECT to_tsquery('simple', string_agg(quote_literal(word), ' | ')) AS consulta FROM termos
)
SELECT c.id, c.movie_id
FROM rag.movie_chunks c, q
WHERE c.tsv @@ q.consulta AND {FILTROS_SQL}
ORDER BY (
    SELECT sum(t.idf) FROM termos t WHERE c.tsv @@ to_tsquery('simple', quote_literal(t.word))
) DESC
LIMIT %(limite)s
"""

SQL_DETALHES = """
SELECT c.id, c.content, m.id, m.tmdb_id, m.title, m.year
FROM rag.movie_chunks c JOIN rag.movies m ON m.id = c.movie_id
WHERE c.id = ANY(%(ids)s)
"""


def buscar(
    conn: psycopg.Connection,
    consulta: str,
    filtros: Filtros | None = None,
    excluir_tmdb_ids: list[int] | None = None,
    k: int = 10,
    agregacao: Literal["soma", "max"] = "max",
) -> Resultado:
    """Devolve os k filmes mais prováveis para a descrição.

    `consulta` deveria estar em inglês (idioma das sinopses): o vetor funciona em português
    (bge-m3 é multilíngue), mas a busca por palavras não. A tradução entra no passo seguinte.
    """
    filtros = filtros or Filtros()
    params = {
        "vetor": embed_consulta(consulta),
        "texto": consulta,
        "ano_min": filtros.ano_min,
        "ano_max": filtros.ano_max,
        "generos": filtros.generos,
        "excluir": excluir_tmdb_ids or [],
        "limite": TRECHOS_POR_BUSCA,
        "max_ndoc": int(TOTAL_TRECHOS_APROX * MAX_FRACAO_TRECHOS),
    }

    conn.execute(f"SET hnsw.ef_search = {EF_SEARCH}")
    conn.execute("SET hnsw.iterative_scan = relaxed_order")
    por_vetor = conn.execute(SQL_VETOR, params).fetchall()
    por_texto = conn.execute(SQL_TEXTO, params).fetchall()

    ids_vetor = [chunk_id for chunk_id, _ in por_vetor]
    ids_texto = [chunk_id for chunk_id, _ in por_texto]
    nota_trecho = rrf([ids_vetor, ids_texto])

    detalhes = {
        linha[0]: linha
        for linha in conn.execute(SQL_DETALHES, {"ids": list(nota_trecho)}).fetchall()
    }
    pos_vetor = {chunk_id: i for i, chunk_id in enumerate(ids_vetor, start=1)}
    pos_texto = {chunk_id: i for i, chunk_id in enumerate(ids_texto, start=1)}

    # Agrupar por filme. "max" (padrão) usa o melhor trecho do filme. "soma" favorece filmes com
    # várias cenas parecidas — mas também filmes longos com muitos trechos fracos (o "Next Friday"
    # passou o "Groundhog Day" somando 10 trechos com a palavra "day"). O eval decide.
    trechos_do_filme: dict[int, list[int]] = defaultdict(list)
    for chunk_id in nota_trecho:
        trechos_do_filme[detalhes[chunk_id][2]].append(chunk_id)

    candidatos = []
    for movie_id, chunks in trechos_do_filme.items():
        notas = [nota_trecho[c] for c in chunks]
        melhor = max(chunks, key=nota_trecho.get)
        _, conteudo, _, tmdb_id, titulo, ano = detalhes[melhor]
        candidatos.append(
            Candidato(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                titulo=titulo,
                ano=ano,
                nota=sum(notas) if agregacao == "soma" else max(notas),
                trecho=conteudo,
                posicao_vetor=min((pos_vetor[c] for c in chunks if c in pos_vetor), default=None),
                posicao_texto=min((pos_texto[c] for c in chunks if c in pos_texto), default=None),
            )
        )
    candidatos.sort(key=lambda c: c.nota, reverse=True)

    return Resultado(
        candidatos=candidatos[:k],
        etapas={
            "trechos_vetor": len(ids_vetor),
            "trechos_texto": len(ids_texto),
            "trechos_nas_duas": len(set(ids_vetor) & set(ids_texto)),
            "filmes_distintos": len(candidatos),
            "filmes_devolvidos": min(k, len(candidatos)),
        },
    )
