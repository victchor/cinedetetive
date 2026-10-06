"""Eval de recuperação (nível 1): só a busca, sem LLM gerando a resposta final.

Para cada caso de teste, roda a busca com a descrição e vê em que posição veio o filme certo
(comparando tmdb_id). Roda várias VARIAÇÕES da busca para compará-las nos mesmos casos.

Desde o passo 5.2, a descrição (português) também passa pela REESCRITA do Llama (inglês +
filtros). As reescritas ficam em cache por modelo + versão do prompt: mudar um dos dois
gera reescritas novas; rodar de novo sem mudar nada não chama o LLM.

Uso (dentro de apps/agent):
    uv run python evals/run_retrieval.py --versao v2-reescrita
    uv run python evals/run_retrieval.py --variacao vetor --variacao hibrida_en   (só algumas)

Resultado: tabela no terminal + evals/resultados/<data>_<versao>.json (vai para o Git).
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cinedetetive.config import settings
from cinedetetive.db import conectar
from cinedetetive.llm.prompts import REESCRITA_VERSAO
from cinedetetive.metricas import mrr, posicao, taxa_no_top
from cinedetetive.rag.embeddings import embed_consulta
from cinedetetive.rag.reescrita import ConsultaReescrita, reescrever
from cinedetetive.rag.retriever import Filtros, buscar

PASTA = Path(__file__).parent
CASOS = PASTA / "datasets" / "manual.jsonl"
RESULTADOS = PASTA / "resultados"
CACHE_REESCRITAS = settings.data_dir / "cache" / "reescritas.json"
K = 20          # quantos filmes a busca devolve; Recall@20 é a métrica principal do nível 1
FOLGA_ANOS = 5  # "anos 90" vira 1985–2004: a memória das pessoas erra a década com frequência

# nome → como buscar.
#   vetor / texto: qual versão da pergunta usar em cada metade ("pt" original, "en" reescrita)
#   filtros: None (sem filtro), "llm" (os anos que o Llama extraiu) ou "llm_folga" (com folga)
VARIACOES = {
    "vetor":                {"modo": "vetor",   "vetor": "pt"},
    "vetor_en":             {"modo": "vetor",   "vetor": "en"},
    "texto_en":             {"modo": "texto",   "texto": "en"},
    "hibrida":              {"modo": "hibrida", "vetor": "pt", "texto": "pt"},
    "hibrida_en":           {"modo": "hibrida", "vetor": "en", "texto": "en"},
    "hibrida_mista":        {"modo": "hibrida", "vetor": "pt", "texto": "en"},
    "hibrida_en_filtros":   {"modo": "hibrida", "vetor": "en", "texto": "en", "filtros": "llm"},
    "hibrida_en_folga":     {"modo": "hibrida", "vetor": "en", "texto": "en", "filtros": "llm_folga"},
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


def reescrever_casos(casos: list[dict]) -> dict[str, ConsultaReescrita]:
    """Reescreve cada descrição com o Llama, reaproveitando o cache quando possível."""
    cache = json.loads(CACHE_REESCRITAS.read_text(encoding="utf-8")) if CACHE_REESCRITAS.exists() else {}
    resultado = {}
    for caso in casos:
        chave = f"{settings.llm_model}|{REESCRITA_VERSAO}|{caso['descricao']}"
        if chave not in cache:
            inicio = time.time()
            cache[chave] = reescrever(caso["descricao"]).model_dump()
            print(f"  {caso['id']} {time.time() - inicio:4.1f}s → {cache[chave]['consulta_en'][:90]}")
            CACHE_REESCRITAS.parent.mkdir(parents=True, exist_ok=True)
            CACHE_REESCRITAS.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        resultado[caso["id"]] = ConsultaReescrita(**cache[chave])
    return resultado


def filtros_de(r: ConsultaReescrita, tipo: str | None) -> Filtros | None:
    if tipo is None:
        return None
    folga = FOLGA_ANOS if tipo == "llm_folga" else 0
    return Filtros(
        ano_min=r.ano_min - folga if r.ano_min else None,
        ano_max=r.ano_max + folga if r.ano_max else None,
    )


def rodar_variacao(conn, casos, reescritas, vetores, cfg: dict) -> list[dict]:
    resultados = []
    for caso in casos:
        r = reescritas[caso["id"]]
        texto = {"pt": caso["descricao"], "en": r.consulta_en}
        lado_vetor = cfg.get("vetor", "pt")
        inicio = time.time()
        res = buscar(
            conn,
            texto[lado_vetor],
            filtros=filtros_de(r, cfg.get("filtros")),
            k=K,
            modo=cfg["modo"],
            vetor=vetores[(caso["id"], lado_vetor)] if cfg["modo"] != "texto" else None,
            consulta_texto=texto[cfg.get("texto", "pt")],
        )
        pos = posicao(caso["tmdb_id"], [c.tmdb_id for c in res.candidatos])
        resultados.append(
            {
                "id": caso["id"],
                "titulo": caso["titulo"],
                "categoria": caso["categoria"],
                "posicao": pos,
                "primeiro": f"{res.candidatos[0].titulo} ({res.candidatos[0].ano})" if res.candidatos else None,
                "ms": round((time.time() - inicio) * 1000),
            }
        )
    return resultados


def titulos_vazados(casos, reescritas) -> list[str]:
    """O Llama não deveria escrever títulos na consulta. Conferimos o título esperado."""
    vazados = []
    for c in casos:
        consulta = reescritas[c["id"]].consulta_en.lower()
        if len(c["titulo"]) > 3 and c["titulo"].lower() in consulta:
            vazados.append(f"{c['id']} {c['titulo']}")
    return vazados


def imprimir_tabela(por_variacao: dict[str, list[dict]]) -> None:
    print(f"\n{'variação':<20} {'Recall@20':>9} {'Hit@1':>6} {'Hit@3':>6} {'Hit@10':>7} {'MRR':>6} {'ms/busca':>9}")
    for nome, res in por_variacao.items():
        m = metricas([r["posicao"] for r in res])
        ms = sum(r["ms"] for r in res) / len(res)
        print(
            f"{nome:<20} {m['recall@20']:>8.0%} {m['hit@1']:>6.0%} {m['hit@3']:>6.0%} "
            f"{m['hit@10']:>7.0%} {m['mrr']:>6.2f} {ms:>9.0f}"
        )


def imprimir_por_categoria(por_variacao: dict[str, list[dict]]) -> None:
    categorias = list(dict.fromkeys(r["categoria"] for r in next(iter(por_variacao.values()))))
    abrev = {"memoria_errada": "mem_errada", "termo_traduzido": "traduzido", "nao_americano": "nao_amer"}
    print(f"\nRecall@20 por categoria\n{'variação':<20}" + "".join(f"{abrev.get(c, c):>11}" for c in categorias))
    for nome, res in por_variacao.items():
        por_cat = defaultdict(list)
        for r in res:
            por_cat[r["categoria"]].append(r["posicao"])
        celulas = [f"{sum(1 for x in por_cat[c] if x and x <= K)}/{len(por_cat[c])}" for c in categorias]
        print(f"{nome:<20}" + "".join(f"{x:>11}" for x in celulas))


def imprimir_casos(por_variacao: dict[str, list[dict]]) -> None:
    nomes = list(por_variacao)
    print(f"\nPosição do filme certo em cada caso ('-' = não veio entre os {K})")
    print(f"{'caso':<5} {'filme':<26}" + "".join(f"{n[-10:]:>11}" for n in nomes))
    for i, caso in enumerate(por_variacao[nomes[0]]):
        celulas = "".join(f"{(por_variacao[n][i]['posicao'] or '-'):>11}" for n in nomes)
        print(f"{caso['id']:<5} {caso['titulo'][:25]:<26}{celulas}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--versao", default="sem-nome", help="rótulo da rodada (vai no nome do arquivo)")
    p.add_argument("--variacao", choices=list(VARIACOES), action="append", help="rodar só algumas")
    a = p.parse_args()

    casos = carregar_casos()
    escolhidas = {n: VARIACOES[n] for n in (a.variacao or VARIACOES)}
    print(f"{len(casos)} casos · LLM {settings.llm_model} · prompt {REESCRITA_VERSAO}")

    print("Reescrevendo as descrições (cache em data/cache/reescritas.json)...")
    reescritas = reescrever_casos(casos)
    falhas = [cid for cid, r in reescritas.items() if r.fallback]
    if falhas:
        print(f"  ⚠️ reescrita falhou (usou a original) em: {', '.join(falhas)}")

    print("Gerando os vetores (português e inglês)...")
    inicio = time.time()
    lados = {cfg.get("vetor", "pt") for cfg in escolhidas.values() if cfg["modo"] != "texto"}
    vetores = {}
    for caso in casos:
        texto = {"pt": caso["descricao"], "en": reescritas[caso["id"]].consulta_en}
        for lado in lados:
            vetores[(caso["id"], lado)] = embed_consulta(texto[lado])
    print(f"  {time.time() - inicio:.0f} s")

    por_variacao = {}
    with conectar() as conn:
        for nome, cfg in escolhidas.items():
            por_variacao[nome] = rodar_variacao(conn, casos, reescritas, vetores, cfg)

    imprimir_tabela(por_variacao)
    imprimir_por_categoria(por_variacao)
    imprimir_casos(por_variacao)
    vazados = titulos_vazados(casos, reescritas)
    print(f"\nTítulos escritos pelo Llama na consulta: {', '.join(vazados) if vazados else 'nenhum ✅'}")

    RESULTADOS.mkdir(exist_ok=True)
    arquivo = RESULTADOS / f"{datetime.now():%Y-%m-%d_%H%M}_{a.versao}.json"
    arquivo.write_text(
        json.dumps(
            {
                "versao": a.versao,
                "data": datetime.now().isoformat(timespec="seconds"),
                "dataset": CASOS.name,
                "k": K,
                "llm": settings.llm_model,
                "prompt_reescrita": REESCRITA_VERSAO,
                "reescritas": {cid: r.model_dump() for cid, r in reescritas.items()},
                "titulos_vazados": vazados,
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
