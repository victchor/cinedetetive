"""Quebra as sinopses em trechos e grava filmes e trechos no Postgres (ainda sem embedding).

Por que trechos: o embedding de uma sinopse inteira vira a "média" do filme e dilui a cena
que o usuário lembra. Trechos de ~800 caracteres mantêm cada cena nítida.

Entrada:  data/clean/movies_linked.parquet
Saída:    rag.movies e rag.movie_chunks no Postgres
          data/colab/chunks_parte1..8.parquet  (id + texto, para o Colab gerar os embeddings)

Uso (dentro de apps/agent):  uv run python ingestion/chunk_load.py
Pode rodar de novo: apaga e recarrega as tabelas.
"""

import re

import pandas as pd
import psycopg

from cinedetetive.config import settings

ENTRADA = settings.data_dir / "clean" / "movies_linked.parquet"
PASTA_COLAB = settings.data_dir / "colab"
PARTES_COLAB = 8  # partes pequenas (~4 MB) para subir no Drive sem limite de tamanho

TAMANHO_TRECHO = 800   # caracteres de sinopse por trecho (sem contar o cabeçalho)
SOBREPOSICAO = 0.15    # ~120 caracteres repetidos entre trechos vizinhos

# Fim de frase seguido de espaço, ou quebra de parágrafo
FIM_DE_FRASE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"')\]])\s+|\n+")


def cabecalho(titulo: str, ano: int, generos: list[str]) -> str:
    """Contexto curto no início de todo trecho: o trecho 5 de uma sinopse sozinho não diz de qual filme é."""
    genero = f" — {', '.join(generos[:3])}" if len(generos) else ""
    return f"{titulo} ({ano}){genero}"


def dividir_frases(texto: str) -> list[str]:
    frases = [f.strip() for f in FIM_DE_FRASE.split(texto) if f and f.strip()]
    # frase gigante (raro): corta por palavras para nenhum pedaço passar do tamanho do trecho
    resultado = []
    for frase in frases:
        while len(frase) > TAMANHO_TRECHO:
            corte = frase.rfind(" ", 0, TAMANHO_TRECHO)
            corte = corte if corte > 0 else TAMANHO_TRECHO
            resultado.append(frase[:corte].strip())
            frase = frase[corte:].strip()
        resultado.append(frase)
    return resultado


def quebrar_em_trechos(texto: str) -> list[str]:
    """Junta frases inteiras até ~800 caracteres. O trecho seguinte começa repetindo as
    últimas frases do anterior (~15%), para uma cena cortada ao meio aparecer inteira em um dos dois."""
    frases = dividir_frases(texto)
    trechos: list[str] = []
    atual: list[str] = []

    for frase in frases:
        if atual and len(" ".join([*atual, frase])) > TAMANHO_TRECHO:
            trechos.append(" ".join(atual))
            # sobreposição: leva as últimas frases que couberem em ~15% do tamanho
            sobra: list[str] = []
            for anterior in reversed(atual):
                if len(" ".join([anterior, *sobra])) > TAMANHO_TRECHO * SOBREPOSICAO:
                    break
                sobra.insert(0, anterior)
            atual = sobra
        atual.append(frase)

    if atual:
        trechos.append(" ".join(atual))
    return trechos


def montar_trechos(filmes: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for filme in filmes.itertuples():
        topo = cabecalho(filme.title, filme.year, list(filme.genres))
        for indice, trecho in enumerate(quebrar_em_trechos(filme.plot)):
            linhas.append(
                {
                    "movie_id": filme.id,
                    "chunk_index": indice,
                    "content": f"{topo}\n{trecho}",
                    "year": filme.year,
                    "genres": list(filme.genres),
                }
            )
    trechos = pd.DataFrame(linhas)
    trechos.insert(0, "id", range(1, len(trechos) + 1))
    return trechos


def gravar_no_banco(filmes: pd.DataFrame, trechos: pd.DataFrame) -> None:
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE rag.movies, rag.movie_chunks RESTART IDENTITY")

        # COPY é a forma mais rápida de inserir muitas linhas no Postgres (bem mais que INSERT um a um)
        colunas = ["id", "title", "year", "origin", "director", "cast_members", "genres",
                   "wiki_url", "tmdb_id", "match_score", "match_source"]
        with cur.copy(f"COPY rag.movies ({', '.join(colunas)}) FROM STDIN") as copy:
            for f in filmes.itertuples():
                copy.write_row([
                    f.id, f.title, f.year, f.origin, f.director, list(f.cast_members), list(f.genres),
                    f.wiki_url,
                    None if pd.isna(f.tmdb_id) else int(f.tmdb_id),
                    None if pd.isna(f.match_score) else float(f.match_score),
                    f.match_source if f.match_source in ("wikidata", "tmdb_search") else None,
                ])

        with cur.copy("COPY rag.movie_chunks (id, movie_id, chunk_index, content, year, genres) FROM STDIN") as copy:
            for t in trechos.itertuples():
                copy.write_row([t.id, t.movie_id, t.chunk_index, t.content, t.year, t.genres])

        # como os ids vieram de fora, o contador automático precisa ser avançado
        cur.execute("SELECT setval(pg_get_serial_sequence('rag.movies', 'id'), (SELECT max(id) FROM rag.movies))")
        cur.execute("SELECT setval(pg_get_serial_sequence('rag.movie_chunks', 'id'), (SELECT max(id) FROM rag.movie_chunks))")


def main() -> None:
    filmes = pd.read_parquet(ENTRADA).reset_index(drop=True)
    filmes.insert(0, "id", range(1, len(filmes) + 1))
    print(f"Filmes: {len(filmes):,}")

    trechos = montar_trechos(filmes)
    tamanho = trechos["content"].str.len()
    por_filme = trechos.groupby("movie_id").size()
    print(f"Trechos: {len(trechos):,}  (média de {por_filme.mean():.1f} por filme, máximo {por_filme.max()})")
    print(f"Tamanho do trecho (com cabeçalho): mediana {tamanho.median():.0f}, máximo {tamanho.max()} caracteres")

    print("\nExemplo — Groundhog Day, trechos 0 e 1:")
    gd = filmes.loc[filmes["title"] == "Groundhog Day", "id"].iloc[0]
    for conteudo in trechos.loc[trechos["movie_id"] == gd, "content"].head(2):
        print("  ┌", conteudo[:400].replace("\n", "\n  │ "), "…\n")

    print("Gravando no Postgres...")
    gravar_no_banco(filmes, trechos)

    PASTA_COLAB.mkdir(parents=True, exist_ok=True)
    for antiga in PASTA_COLAB.glob("chunks_parte*.parquet"):
        antiga.unlink()
    por_parte = -(-len(trechos) // PARTES_COLAB)  # divisão arredondando para cima
    for i in range(PARTES_COLAB):
        parte = trechos.iloc[i * por_parte : (i + 1) * por_parte][["id", "content"]]
        parte.to_parquet(PASTA_COLAB / f"chunks_parte{i + 1}.parquet", index=False, compression="zstd")
    print(f"Exportado para o Colab: {PASTA_COLAB}/chunks_parte1..{PARTES_COLAB}.parquet")


if __name__ == "__main__":
    main()
