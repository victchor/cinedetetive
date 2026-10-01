"""Liga cada filme da base ao TMDB (tmdb_id), para ter pôster, título em português e um ID para os evals.

Três camadas, da mais confiável para a menos:
  1. Wikidata: página da Wikipedia → tmdb_id cadastrado (ligação exata, match_score = 1.0)
     1b. páginas renomeadas desde 2019: resolve o redirecionamento na Wikipedia e tenta de novo
  2. Busca no TMDB por título + ano, só para quem sobrou (match_score = semelhança, 0..1)
  3. Sem par seguro: tmdb_id fica vazio (o filme continua no índice, só fica sem pôster)

Entrada:  data/clean/movies.parquet
Saída:    data/clean/movies_linked.parquet
Cache:    data/cache/  (rodar de novo não repete as chamadas já feitas)

Uso (dentro de apps/agent):  uv run python ingestion/link_tmdb.py
"""

import json
import re
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

import httpx
import pandas as pd

from cinedetetive.config import ROOT_DIR, settings

ENTRADA = settings.data_dir / "clean" / "movies.parquet"
SAIDA = settings.data_dir / "clean" / "movies_linked.parquet"
CACHE = settings.data_dir / "cache"
CASOS = ROOT_DIR / "apps" / "agent" / "evals" / "datasets" / "manual.jsonl"

# A política de robôs da Wikimedia exige identificação com contato (https://w.wiki/4wJS)
USER_AGENT = "cinedetetive-study/0.1 (https://github.com/victchor/cinedetetive)"
WIKIDATA = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
TMDB = "https://api.themoviedb.org/3"

SIMILARIDADE_MINIMA = 0.9  # título do TMDB precisa ser quase igual ao da Wikipedia
DIFERENCA_MAXIMA_ANO = 1   # estreias em países diferentes costumam variar 1 ano


# ---------- cache simples em JSON ----------

def ler_cache(nome: str) -> dict:
    arquivo = CACHE / nome
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}


def gravar_cache(nome: str, dados: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def titulo_da_pagina(wiki_url: str) -> str:
    """https://en.wikipedia.org/wiki/Groundhog_Day_(film) → 'Groundhog Day (film)'

    Também aceita "link vermelho" (página que não existe): .../w/index.php?title=X&action=edit&redlink=1
    """
    if "/wiki/" in wiki_url:
        caminho = urllib.parse.unquote(wiki_url.split("/wiki/", 1)[1])
    else:
        caminho = urllib.parse.parse_qs(urllib.parse.urlparse(wiki_url).query).get("title", [""])[0]
    return caminho.split("#")[0].replace("_", " ")


def em_lotes(itens: list, tamanho: int):
    for i in range(0, len(itens), tamanho):
        yield itens[i : i + tamanho]


# ---------- camada 1: Wikidata ----------

def consultar_wikidata(cliente: httpx.Client, paginas: list[str]) -> dict[str, int]:
    """Nome da página da Wikipedia → tmdb_id, para as que o Wikidata conhece."""
    literais = " ".join('"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"@en' for p in paginas)
    consulta = f"""
    SELECT ?nome ?tmdb WHERE {{
      VALUES ?nome {{ {literais} }}
      ?artigo schema:name ?nome ;
              schema:isPartOf <https://en.wikipedia.org/> ;
              schema:about ?item .
      ?item wdt:P4947 ?tmdb .
    }}"""
    for tentativa in range(4):
        resp = cliente.post(WIKIDATA, data={"query": consulta}, headers={"Accept": "application/sparql-results+json"})
        if resp.status_code == 200:
            break
        time.sleep(5 * (tentativa + 1))  # o Wikidata limita consultas pesadas; espera e tenta de novo
    resp.raise_for_status()

    resultado: dict[str, int] = {}
    for linha in resp.json()["results"]["bindings"]:
        valor = linha["tmdb"]["value"]
        if valor.isdigit():
            resultado.setdefault(linha["nome"]["value"], int(valor))
    return resultado


def camada_wikidata(cliente: httpx.Client, paginas: list[str]) -> dict[str, int | None]:
    cache = ler_cache("wikidata.json")
    faltando = [p for p in dict.fromkeys(paginas) if p not in cache]
    for i, lote in enumerate(em_lotes(faltando, 200), start=1):
        achados = consultar_wikidata(cliente, lote)
        cache.update({p: achados.get(p) for p in lote})
        if i % 10 == 0:
            gravar_cache("wikidata.json", cache)
            print(f"    Wikidata: {i * 200:,}/{len(faltando):,} páginas consultadas")
        time.sleep(0.5)
    gravar_cache("wikidata.json", cache)
    return cache


def resolver_redirecionamentos(cliente: httpx.Client, paginas: list[str]) -> dict[str, str]:
    """Páginas renomeadas depois de 2019: 'Tabu (1931 film)' → 'Tabu: A Story of the South Seas'."""
    cache = ler_cache("redirecionamentos.json")
    faltando = [p for p in dict.fromkeys(paginas) if p not in cache]
    for lote in em_lotes(faltando, 50):  # limite da API da Wikipedia
        resp = cliente.get(
            WIKIPEDIA_API,
            params={"action": "query", "titles": "|".join(lote), "redirects": 1, "format": "json", "formatversion": 2},
        )
        resp.raise_for_status()
        dados = resp.json().get("query", {})
        mapa = {p: p for p in lote}
        for etapa in ("normalized", "redirects"):
            de_para = {item["from"]: item["to"] for item in dados.get(etapa, [])}
            mapa = {orig: de_para.get(atual, atual) for orig, atual in mapa.items()}
        cache.update(mapa)
        time.sleep(0.2)
    gravar_cache("redirecionamentos.json", cache)
    return cache


# ---------- camada 2: busca no TMDB ----------

def normalizar_titulo(titulo: str) -> str:
    titulo = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    titulo = re.sub(r"[^a-z0-9 ]", " ", titulo.lower())
    titulo = re.sub(r"^(the|a|an) ", "", titulo.strip())
    return re.sub(r"\s+", " ", titulo).strip()


def melhor_candidato(titulo: str, anos: list[int], resultados: list[dict]) -> tuple[int | None, float]:
    """Escolhe o resultado do TMDB mais parecido com (título, ano). Devolve (tmdb_id, nota)."""
    alvo = normalizar_titulo(titulo)
    melhor: tuple[int | None, float] = (None, 0.0)
    for r in resultados:
        data = r.get("release_date") or ""
        if len(data) < 4:
            continue
        diferenca = min(abs(int(data[:4]) - a) for a in anos)
        if diferenca > DIFERENCA_MAXIMA_ANO:
            continue
        semelhanca = max(
            SequenceMatcher(None, alvo, normalizar_titulo(r.get("title") or "")).ratio(),
            SequenceMatcher(None, alvo, normalizar_titulo(r.get("original_title") or "")).ratio(),
        )
        if semelhanca < SIMILARIDADE_MINIMA:
            continue
        nota = round(0.7 * semelhanca + 0.3 * (1.0 if diferenca == 0 else 0.6), 3)
        if nota > melhor[1]:
            melhor = (r["id"], nota)
    return melhor


def buscar_no_tmdb(cliente: httpx.Client, titulo: str) -> list[dict]:
    for tentativa in range(4):
        resp = cliente.get(f"{TMDB}/search/movie", params={"query": titulo, "include_adult": "false"})
        if resp.status_code == 429:  # limite de requisições: espera o que o TMDB pedir
            time.sleep(float(resp.headers.get("Retry-After", 2)))
            continue
        if resp.status_code >= 500:
            time.sleep(2 * (tentativa + 1))
            continue
        resp.raise_for_status()
        return resp.json().get("results", [])
    return []


def camada_tmdb(cliente: httpx.Client, filmes: pd.DataFrame, nome_cache: str = "tmdb_busca.json") -> dict[str, list]:
    """wiki_url → [tmdb_id, nota]. Busca só pelo título e escolhe pelo ano depois (mais tolerante)."""
    cache = ler_cache(nome_cache)
    faltando = filmes[~filmes["wiki_url"].isin(cache.keys())]

    def processar(linha) -> tuple[str, list]:
        anos = [int(linha.year), *[int(a) for a in linha.alt_years]]
        return linha.wiki_url, list(melhor_candidato(linha.title, anos, buscar_no_tmdb(cliente, linha.title)))

    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, (url, resultado) in enumerate(pool.map(processar, faltando.itertuples()), start=1):
            cache[url] = resultado
            if i % 500 == 0:
                gravar_cache(nome_cache, cache)
                print(f"    TMDB: {i:,}/{len(faltando):,} buscas")
    gravar_cache(nome_cache, cache)
    return cache


# ---------- camada 3: conflitos (o mesmo tmdb_id em mais de um filme) ----------

def ano_no_tmdb(cliente: httpx.Client, tmdb_ids: list[int]) -> dict[str, int | None]:
    cache = ler_cache("tmdb_anos.json")
    faltando = [i for i in dict.fromkeys(tmdb_ids) if str(i) not in cache]

    def consultar(tmdb_id: int) -> tuple[str, int | None]:
        resp = cliente.get(f"{TMDB}/movie/{tmdb_id}")
        data = (resp.json().get("release_date") or "") if resp.status_code == 200 else ""
        return str(tmdb_id), int(data[:4]) if len(data) >= 4 else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        cache.update(dict(pool.map(consultar, faltando)))
    gravar_cache("tmdb_anos.json", cache)
    return cache


def resolver_conflitos(cliente: httpx.Client, df: pd.DataFrame) -> pd.DataFrame:
    """Quando dois filmes da base apontam para o mesmo tmdb_id:
    - ano não bate com o TMDB (±1)  → pareamento errado: tira o tmdb_id
      (ex.: 'To Catch a Thief' de Hong Kong, 1991, ligado ao do Hitchcock, 1955)
    - ano bate e sobra mais de um  → é o MESMO filme em duas páginas da Wikipedia:
      fica só a linha com a sinopse mais longa (senão ocupa 2 vagas no top 20 da busca)
    """
    repetido = df["tmdb_id"].notna() & df.duplicated("tmdb_id", keep=False)
    anos = ano_no_tmdb(cliente, df.loc[repetido, "tmdb_id"].astype(int).tolist())

    def ano_bate(linha) -> bool:
        ano = anos.get(str(int(linha.tmdb_id)))
        return ano is not None and abs(ano - linha.year) <= DIFERENCA_MAXIMA_ANO

    errados = [i for i, linha in df[repetido].iterrows() if not ano_bate(linha)]
    df.loc[errados, ["tmdb_id", "match_score"]] = None
    df.loc[errados, "match_source"] = "conflito"
    print(f"  pareamentos errados desfeitos: {len(errados):,}")

    ainda_repetido = df["tmdb_id"].notna() & df.duplicated("tmdb_id", keep=False)
    tamanho = df["plot"].str.len()
    manter = tamanho[ainda_repetido].groupby(df.loc[ainda_repetido, "tmdb_id"]).idxmax()
    remover = df.index[ainda_repetido].difference(manter.values)
    print(f"  mesmo filme em duas páginas, linhas removidas: {len(remover):,}")
    return df.drop(index=remover)


# ---------- verificações ----------

def conferir_casos_de_teste(df: pd.DataFrame) -> None:
    casos = [json.loads(linha) for linha in CASOS.read_text(encoding="utf-8").splitlines() if linha.strip()]
    por_titulo = {(t.lower(), a): (i, s) for t, a, i, s in zip(df["title"], df["year"], df["tmdb_id"], df["match_source"])}
    certos = 0
    for c in casos:
        tmdb_id, fonte = por_titulo.get((c["titulo"].lower(), c["ano"]), (None, None))
        ok = tmdb_id == c["tmdb_id"]
        certos += ok
        if not ok:
            print(f"  ❌ {c['id']} {c['titulo']}: esperado {c['tmdb_id']}, ligado a {tmdb_id} ({fonte})")
    print(f"  Casos de teste com o tmdb_id certo: {certos}/{len(casos)}")


def medir_precisao_da_busca(cliente: httpx.Client, df: pd.DataFrame, n: int = 300) -> None:
    """Roda a camada 2 em filmes que o Wikidata já resolveu e compara: a busca por nome acerta quanto?"""
    amostra = df[df["match_source"] == "wikidata"].sample(n, random_state=7)
    resultado = camada_tmdb(cliente, amostra, nome_cache="tmdb_busca_validacao.json")
    aceitos = [(resultado[u][0], esperado) for u, esperado in zip(amostra["wiki_url"], amostra["tmdb_id"]) if resultado[u][0]]
    corretos = sum(achado == esperado for achado, esperado in aceitos)
    print(f"  Busca por nome em {n} filmes já ligados pelo Wikidata:")
    print(f"    aceitou um candidato: {len(aceitos)}/{n} ({len(aceitos) / n:.0%})")
    print(f"    candidato correto:    {corretos}/{len(aceitos)} ({corretos / max(1, len(aceitos)):.1%})")


# ---------- principal ----------

def main() -> None:
    if not settings.tmdb_read_token:
        raise SystemExit("TMDB_READ_TOKEN vazio no .env")

    df = pd.read_parquet(ENTRADA)
    df["pagina"] = df["wiki_url"].map(titulo_da_pagina)
    print(f"Entrada: {len(df):,} filmes")

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as wiki:
        print("Camada 1: Wikidata")
        ids = camada_wikidata(wiki, df["pagina"].tolist())
        df["tmdb_id"] = df["pagina"].map(ids)

        sem_id = df.loc[df["tmdb_id"].isna(), "pagina"].tolist()
        print(f"Camada 1b: redirecionamentos ({len(sem_id):,} páginas sem par)")
        destino = resolver_redirecionamentos(wiki, sem_id)
        renomeadas = sorted({destino[p] for p in sem_id if destino.get(p, p) != p})
        ids_renomeadas = camada_wikidata(wiki, renomeadas) if renomeadas else {}
        faltava = df["tmdb_id"].isna()
        df.loc[faltava, "tmdb_id"] = df.loc[faltava, "pagina"].map(lambda p: ids_renomeadas.get(destino.get(p, p)))

    df["match_source"] = df["tmdb_id"].notna().map({True: "wikidata", False: None})
    df["match_score"] = df["tmdb_id"].notna().map({True: 1.0, False: None})
    print(f"  ligados pelo Wikidata: {df['tmdb_id'].notna().sum():,}")

    tmdb_headers = {"Authorization": f"Bearer {settings.tmdb_read_token}", "User-Agent": USER_AGENT}
    with httpx.Client(headers=tmdb_headers, timeout=10) as tmdb:
        restantes = df[df["tmdb_id"].isna()]
        print(f"Camada 2: busca no TMDB ({len(restantes):,} filmes)")
        achados = camada_tmdb(tmdb, restantes)
        aceitos = {url: r for url, r in achados.items() if r[0]}
        linhas = df["tmdb_id"].isna() & df["wiki_url"].isin(aceitos.keys())
        df.loc[linhas, "tmdb_id"] = df.loc[linhas, "wiki_url"].map(lambda u: aceitos[u][0])
        df.loc[linhas, "match_score"] = df.loc[linhas, "wiki_url"].map(lambda u: aceitos[u][1])
        df.loc[linhas, "match_source"] = "tmdb_search"
        print(f"  ligados pela busca: {linhas.sum():,}")

        print("Camada 3: conflitos (o mesmo tmdb_id em mais de um filme)")
        df = resolver_conflitos(tmdb, df)

        print("\n=== Validação ===")
        medir_precisao_da_busca(tmdb, df)

    df["tmdb_id"] = df["tmdb_id"].astype("Int64")
    df["match_score"] = df["match_score"].astype("float32")

    repetidos = df["tmdb_id"].notna() & df.duplicated("tmdb_id", keep=False)
    print(f"  tmdb_id usado por mais de um filme (deve ser 0): {repetidos.sum():,} linhas")
    conferir_casos_de_teste(df)

    print("\n=== Resultado ===")
    print(df["match_source"].fillna("sem par").value_counts().to_string())
    print(f"Cobertura: {df['tmdb_id'].notna().mean():.1%}")

    df.drop(columns="pagina").to_parquet(SAIDA, index=False)
    print(f"Gravado em {SAIDA}")


if __name__ == "__main__":
    main()
