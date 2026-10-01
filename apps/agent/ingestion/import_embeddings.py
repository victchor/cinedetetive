"""Grava no Postgres os embeddings gerados no Colab e confere se batem com o Ollama.

Entrada:  data/colab/embeddings_bge-m3.npz   (baixado do Google Drive)
Saída:    rag.movie_chunks.embedding preenchido + índice HNSW recriado

Depois de gravar, faz duas verificações:
  1. Compatibilidade: os mesmos trechos passados pelo Ollama (que vai gerar os vetores das
     PERGUNTAS) precisam dar vetores quase idênticos aos do Colab. Senão a busca compara
     "mapas" diferentes e erra sem avisar.
  2. Primeira busca vetorial de verdade, para ver o RAG achando filmes.

Uso (dentro de apps/agent):  uv run python ingestion/import_embeddings.py
"""

import time

import httpx
import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from cinedetetive.config import settings

ENTRADA = settings.data_dir / "colab" / "embeddings_bge-m3.npz"
COMPATIBILIDADE_MINIMA = 0.99


def embed_ollama(textos: list[str]) -> np.ndarray:
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/embed",
        json={"model": settings.embedding_model, "input": textos},
        timeout=300,
    )
    resp.raise_for_status()
    return np.array(resp.json()["embeddings"], dtype="float32")


def carregar() -> tuple[np.ndarray, np.ndarray, str]:
    dados = np.load(ENTRADA)
    ids, vetores, modelo = dados["ids"], dados["vetores"].astype("float32"), str(dados["modelo"])
    print(f"Arquivo: {len(ids):,} vetores de {vetores.shape[1]} dimensões, modelo {modelo}")
    if vetores.shape[1] != settings.embedding_dim:
        raise SystemExit(f"Dimensão {vetores.shape[1]} ≠ EMBEDDING_DIM {settings.embedding_dim}")
    if np.isnan(vetores).any():
        raise SystemExit("Há NaN nos vetores")
    return ids, vetores, modelo


def gravar(conn: psycopg.Connection, ids: np.ndarray, vetores: np.ndarray, modelo: str) -> None:
    with conn.cursor() as cur:
        no_banco = cur.execute("SELECT count(*) FROM rag.movie_chunks").fetchone()[0]
        if no_banco != len(ids):
            raise SystemExit(f"O banco tem {no_banco:,} trechos e o arquivo {len(ids):,}. Rode chunk_load.py e o Colab de novo.")

        # Atualizar 116 mil linhas com o índice HNSW existindo é lento (o grafo é refeito a cada linha).
        # Mais rápido: apagar o índice, gravar tudo e construir o índice uma vez só no final.
        cur.execute("DROP INDEX IF EXISTS rag.movie_chunks_embedding_hnsw")

        inicio = time.time()
        cur.execute("CREATE TEMP TABLE novos (id BIGINT, embedding vector(1024)) ON COMMIT DROP")
        with cur.copy("COPY novos (id, embedding) FROM STDIN WITH (FORMAT BINARY)") as copy:
            copy.set_types(["int8", "vector"])
            for chunk_id, vetor in zip(ids, vetores):
                copy.write_row([int(chunk_id), vetor])
        cur.execute(
            """UPDATE rag.movie_chunks c
               SET embedding = n.embedding, embedding_model = %s
               FROM novos n WHERE c.id = n.id""",
            (modelo,),
        )
        print(f"Vetores gravados: {cur.rowcount:,} em {time.time() - inicio:.0f} s")

        inicio = time.time()
        cur.execute("SET maintenance_work_mem = '1GB'")
        cur.execute(
            """CREATE INDEX movie_chunks_embedding_hnsw
               ON rag.movie_chunks USING hnsw (embedding vector_cosine_ops)
               WITH (m = 16, ef_construction = 64)"""
        )
        print(f"Índice HNSW construído em {time.time() - inicio:.0f} s")
    conn.commit()


def conferir_compatibilidade(conn: psycopg.Connection, n: int = 20) -> None:
    linhas = conn.execute(
        "SELECT content, embedding FROM rag.movie_chunks ORDER BY random() LIMIT %s", (n,)
    ).fetchall()
    colab = np.array([e for _, e in linhas], dtype="float32")
    ollama = embed_ollama([c for c, _ in linhas])
    similaridade = (colab * ollama).sum(axis=1) / (np.linalg.norm(colab, axis=1) * np.linalg.norm(ollama, axis=1))
    ok = similaridade.min() >= COMPATIBILIDADE_MINIMA
    print(f"Colab × Ollama em {n} trechos: média {similaridade.mean():.4f}, mínima {similaridade.min():.4f}  "
          f"{'✅ compatíveis' if ok else '❌ INCOMPATÍVEIS — a busca vai errar'}")


def primeira_busca(conn: psycopg.Connection, pergunta: str) -> None:
    vetor = embed_ollama([pergunta])[0]
    filmes = conn.execute(
        """SELECT m.title, m.year, round((1 - (c.embedding <=> %s))::numeric, 3) AS similaridade
           FROM rag.movie_chunks c JOIN rag.movies m ON m.id = c.movie_id
           ORDER BY c.embedding <=> %s
           LIMIT 5""",
        (vetor, vetor),
    ).fetchall()
    print(f'\n🔎 "{pergunta}"')
    for titulo, ano, sim in filmes:
        print(f"   {sim}  {titulo} ({ano})")


def main() -> None:
    ids, vetores, modelo = carregar()
    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        gravar(conn, ids, vetores, modelo)

        sem = conn.execute("SELECT count(*) FROM rag.movie_chunks WHERE embedding IS NULL").fetchone()[0]
        print(f"Trechos sem embedding: {sem:,}")

        print("\n=== Compatibilidade ===")
        conferir_compatibilidade(conn)

        print("\n=== Primeira busca vetorial ===")
        primeira_busca(conn, "a man relives the same day over and over")
        primeira_busca(conn, "homem que acorda sempre no mesmo dia, tinha uma marmota")
        primeira_busca(conn, "filme coreano de zumbi num trem")


if __name__ == "__main__":
    main()
