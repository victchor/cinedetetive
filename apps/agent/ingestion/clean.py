"""Limpa o Wikipedia Movie Plots antes de ligar ao TMDB, quebrar em trechos e gerar embeddings.

Entrada:  data/raw/wiki_movie_plots_deduped.csv   (original do Kaggle, nunca é alterado)
Saída:    data/clean/movies.parquet

Uso (dentro de apps/agent):  uv run python ingestion/clean.py
"""

import json
import re

import pandas as pd

from cinedetetive.config import ROOT_DIR, settings

RAW = settings.data_dir / "raw" / "wiki_movie_plots_deduped.csv"
SAIDA = settings.data_dir / "clean" / "movies.parquet"
CASOS = ROOT_DIR / "apps" / "agent" / "evals" / "datasets" / "manual.jsonl"

MINIMO_SINOPSE = 300

# Marcações da Wikipedia: [1], [23], [citation needed], [clarification needed], [note 2]...
MARCACAO = re.compile(r"\[(?:\d+|citation needed|clarification needed|note \d+|[a-z])\]", re.IGNORECASE)

# Mesmo gênero escrito de jeitos diferentes → um nome só
SINONIMOS_GENERO = {
    "sci-fi": "science fiction",
    "scifi": "science fiction",
    "science-fiction": "science fiction",
    "animated": "animation",
    "comedy-drama": "comedy drama",
    "biopic": "biography",
    "biographical": "biography",
    "rom-com": "romantic comedy",
    "romcom": "romantic comedy",
    "noir": "film noir",
}
GENEROS_VAZIOS = {"", "unknown", "-", "n/a"}


def limpar_sinopse(texto: str) -> str:
    texto = MARCACAO.sub("", texto)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    # espaços repetidos dentro da linha, sem apagar as quebras de parágrafo
    texto = re.sub(r"[ \t ]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # espaço que sobrou antes de pontuação depois de tirar o [1]: "the town ." → "the town."
    texto = re.sub(r" +([.,;:!?])", r"\1", texto)
    return texto.strip()


def separar_generos(genero: str) -> list[str]:
    generos: list[str] = []
    for parte in re.split(r"[,/;|]", str(genero).lower()):
        parte = SINONIMOS_GENERO.get(parte.strip(), parte.strip())
        if parte not in GENEROS_VAZIOS and parte not in generos:
            generos.append(parte)
    return generos


def separar_elenco(elenco) -> list[str]:
    if pd.isna(elenco):
        return []
    sem_funcoes = re.sub(r"\([^)]*\)", "", str(elenco))  # "(director/screenplay)"
    nomes: list[str] = []
    for nome in re.split(r"[,;\n]", sem_funcoes):
        nome = nome.strip(" .")
        if nome and nome.lower() != "unknown" and nome not in nomes:
            nomes.append(nome)
    return nomes


def limpar_diretor(diretor) -> str | None:
    if pd.isna(diretor):
        return None
    diretor = str(diretor).strip()
    return None if diretor.lower() in {"", "unknown"} else diretor


def juntar_mesma_pagina(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas com a mesma página da Wikipedia viram uma só.

    Na maioria são coproduções (uma linha por país). Mas ~380 páginas têm ANOS diferentes:
    estreias em anos diferentes, vários filmes numa página só, ou linha errada no dataset
    (ex.: "Taxi Driver, 1944, Bollywood" com a sinopse do filme de 1976).
    Não dá para saber o ano certo só pelo CSV: os outros anos vão para `alt_years`
    e a ligação com o TMDB (link_tmdb.py) testa todos.
    """
    grupos = df.groupby("wiki_url")
    origens = grupos["origin"].agg(lambda s: ", ".join(sorted(set(s))))
    anos = grupos["year"].agg(lambda s: sorted(set(s)))

    # Desempate: sinopse mais longa; depois origem americana/britânica (a Wikipedia em
    # inglês é principalmente sobre esses filmes); depois o ano mais antigo.
    prioridade = df["origin"].map({"American": 0, "British": 1}).fillna(2)
    df = df.assign(_tam=-df["plot"].str.len(), _prio=prioridade)
    df = df.sort_values(["_tam", "_prio", "year"]).drop_duplicates("wiki_url").drop(columns=["_tam", "_prio"])

    df["origin"] = df["wiki_url"].map(origens)
    df["alt_years"] = [[a for a in anos[url] if a != ano] for url, ano in zip(df["wiki_url"], df["year"])]
    return df


def conferir_casos_de_teste(df: pd.DataFrame) -> None:
    casos = [json.loads(linha) for linha in CASOS.read_text(encoding="utf-8").splitlines() if linha.strip()]
    chave = set(zip(df["title"].str.lower(), df["year"]))
    faltando = [c for c in casos if (c["titulo"].lower(), c["ano"]) not in chave]
    print(f"Casos de teste encontrados: {len(casos) - len(faltando)}/{len(casos)}")
    for c in faltando:
        print("  ❌", c["id"], c["titulo"], c["ano"])


def main() -> None:
    bruto = pd.read_csv(RAW)
    print(f"Entrada: {len(bruto):,} filmes")

    df = pd.DataFrame(
        {
            "title": bruto["Title"].str.strip(),
            "year": bruto["Release Year"].astype("int16"),
            "origin": bruto["Origin/Ethnicity"].str.strip().str.replace("_", " "),
            "director": bruto["Director"].map(limpar_diretor),
            "cast_members": bruto["Cast"].map(separar_elenco),
            "genres": bruto["Genre"].map(separar_generos),
            "wiki_url": bruto["Wiki Page"].str.strip(),
            "plot": bruto["Plot"].map(limpar_sinopse),
        }
    )

    antes = len(df)
    df = juntar_mesma_pagina(df)
    print(f"  − {antes - len(df):,} linhas repetidas da mesma página (coproduções juntadas)")

    antes = len(df)
    df = df[df["plot"].str.len() >= MINIMO_SINOPSE]
    print(f"  − {antes - len(df):,} sinopses com menos de {MINIMO_SINOPSE} caracteres")

    df = df.sort_values(["year", "title"]).reset_index(drop=True)
    print(f"Saída: {len(df):,} filmes")

    print("\n=== Conferência ===")
    print("Títulos com espaço sobrando:", (df["title"] != df["title"].str.strip()).sum())
    print("Sinopses com marcação [n]:", df["plot"].str.contains(MARCACAO).sum())
    print("Filmes sem gênero:", (df["genres"].str.len() == 0).sum())
    print("Filmes sem elenco:", (df["cast_members"].str.len() == 0).sum())
    print("Mesmo título e ano, páginas diferentes (filmes distintos, mantidos):", df.duplicated(["title", "year"]).sum())
    print("Filmes com ano em conflito (alt_years, resolver no TMDB):", (df["alt_years"].str.len() > 0).sum())
    conferir_casos_de_teste(df)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SAIDA, index=False)
    print(f"\nGravado em {SAIDA} ({SAIDA.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
