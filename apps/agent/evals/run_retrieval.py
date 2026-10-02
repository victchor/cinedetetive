"""Eval de recuperação (nível 1): só a busca, sem LLM gerando resposta.

Para cada caso de teste, roda a busca com a descrição e vê em que posição veio o filme certo
(comparando tmdb_id). Roda várias VARIAÇÕES da busca para compará-las nos mesmos casos.

Uso (dentro de apps/agent):
    uv run python evals/run_retrieval.py
    uv run python evals/run_retrieval.py --versao v1-hibrida-idf
    uv run python evals/run_retrieval.py --variacao hibrida      (só uma variação)

Resultado: tabela no terminal + evals/resultados/<data>_<versao>.json (vai para o Git).
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cinedetetive.db import conectar
from cinedetetive.metricas import mrr, posicao, taxa_no_top
from cinedetetive.rag.embeddings import embed_consulta
from cinedetetive.rag.retriever import buscar

PASTA = Path(__file__).parent
CASOS = PASTA / "datasets" / "manual.jsonl"
RESULTADOS = PASTA / "resultados"
K = 20  # quantos filmes a busca devolve; Recall@20 é a métrica principal do nível 1

# nome → parâmetros de buscar(). Para testar uma ideia nova, acrescente uma linha aqui.
VARIACOES = {
    "vetor": {"modo": "vetor", "agregacao": "max"},
    "texto": {"modo": "texto", "agregacao": "max"},
    "hibrida": {"modo": "hibrida", "agregacao": "max"},
    "hibrida_soma": {"modo": "hibrida", "agregacao": "soma"},
}


def carregar_casos() -> list[dict]:
    return [json.loads(linha) for linha in CASOS.read_text(encoding="utf-8").splitlines() if linha.strip()]


def metricas(posicoes: list[int | None]) -> dict[str, float]:
    return {
        "recall@20": taxa_no_top(posicoes, 20),
        "hit@1": taxa_no_top(posicoes, 1),
        "hit@3": taxa_no_top(posicoes, 3),
        "hit@10": taxa_no_top(posicoes, 10),
        "mrr": mrr(posicoes),
    }


def rodar_variacao(conn, casos: list[dict], vetores: dict[str, object], params: dict) -> list[dict]:
    resultados = []
    for caso in casos:
        inicio = time.time()
        r = buscar(conn, caso["descricao"], k=K, vetor=vetores[caso["id"]], **params)
        devolvidos = [c.tmdb_id for c in r.candidatos]
        pos = posicao(caso["tmdb_id"], devolvidos)
        resultados.append(
            {
                "id": caso["id"],
                "titulo": caso["titulo"],
                "categoria": caso["categoria"],
                "posicao": pos,
                "primeiro": f"{r.candidatos[0].titulo} ({r.candidatos[0].ano})" if r.candidatos else None,
                "ms": round((time.time() - inicio) * 1000),
            }
        )
    return resultados


def imprimir_tabela(por_variacao: dict[str, list[dict]]) -> None:
    print(f"\n{'variação':<14} {'Recall@20':>9} {'Hit@1':>6} {'Hit@3':>6} {'Hit@10':>7} {'MRR':>6} {'ms/busca':>9}")
    for nome, res in por_variacao.items():
        m = metricas([r["posicao"] for r in res])
        ms = sum(r["ms"] for r in res) / len(res)
        print(
            f"{nome:<14} {m['recall@20']:>8.0%} {m['hit@1']:>6.0%} {m['hit@3']:>6.0%} "
            f"{m['hit@10']:>7.0%} {m['mrr']:>6.2f} {ms:>9.0f}"
        )


def imprimir_por_categoria(por_variacao: dict[str, list[dict]]) -> None:
    categorias = list(dict.fromkeys(r["categoria"] for r in next(iter(por_variacao.values()))))
    print(f"\nRecall@20 por categoria\n{'variação':<14}" + "".join(f"{c[:14]:>16}" for c in categorias))
    for nome, res in por_variacao.items():
        por_cat = defaultdict(list)
        for r in res:
            por_cat[r["categoria"]].append(r["posicao"])
        celulas = []
        for c in categorias:
            p = por_cat[c]
            acertos = sum(1 for x in p if x is not None and x <= K)
            celulas.append(f"{acertos}/{len(p)}")
        print(f"{nome:<14}" + "".join(f"{x:>16}" for x in celulas))


def imprimir_casos(por_variacao: dict[str, list[dict]]) -> None:
    nomes = list(por_variacao)
    print(f"\nPosição do filme certo em cada caso ('-' = não veio entre os {K})")
    print(f"{'caso':<5} {'filme':<34}" + "".join(f"{n[:12]:>13}" for n in nomes))
    for i, caso in enumerate(por_variacao[nomes[0]]):
        posicoes = [por_variacao[n][i]["posicao"] for n in nomes]
        celulas = "".join(f"{(p if p else '-'):>13}" for p in posicoes)
        print(f"{caso['id']:<5} {caso['titulo'][:33]:<34}{celulas}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--versao", default="sem-nome", help="rótulo da rodada (vai no nome do arquivo)")
    p.add_argument("--variacao", choices=list(VARIACOES), action="append", help="rodar só algumas")
    a = p.parse_args()

    casos = carregar_casos()
    escolhidas = {n: VARIACOES[n] for n in (a.variacao or VARIACOES)}

    print(f"{len(casos)} casos · variações: {', '.join(escolhidas)}")
    print("Gerando o vetor de cada descrição (uma vez só)...")
    inicio = time.time()
    vetores = {c["id"]: embed_consulta(c["descricao"]) for c in casos}
    print(f"  {time.time() - inicio:.0f} s")

    por_variacao = {}
    with conectar() as conn:
        for nome, params in escolhidas.items():
            por_variacao[nome] = rodar_variacao(conn, casos, vetores, params)

    imprimir_tabela(por_variacao)
    imprimir_por_categoria(por_variacao)
    imprimir_casos(por_variacao)

    RESULTADOS.mkdir(exist_ok=True)
    arquivo = RESULTADOS / f"{datetime.now():%Y-%m-%d_%H%M}_{a.versao}.json"
    arquivo.write_text(
        json.dumps(
            {
                "versao": a.versao,
                "data": datetime.now().isoformat(timespec="seconds"),
                "dataset": CASOS.name,
                "k": K,
                "variacoes": {
                    nome: {
                        "parametros": escolhidas[nome],
                        "metricas": {m: round(v, 4) for m, v in metricas([r["posicao"] for r in res]).items()},
                        "casos": res,
                    }
                    for nome, res in por_variacao.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nGravado em {arquivo.relative_to(PASTA.parent)}")


if __name__ == "__main__":
    main()
