"""Testa a busca pelo terminal.

Uso (dentro de apps/agent):
    uv run python scripts/buscar.py "a man relives the same day over and over"
    uv run python scripts/buscar.py "aliens and a soldier reliving a battle" --ano-min 2000 --excluir 137
    uv run python scripts/buscar.py "dreams inside dreams" --agregacao max -k 5
"""

import argparse
import time

from cinedetetive.db import conectar
from cinedetetive.rag.retriever import Filtros, buscar


def main() -> None:
    p = argparse.ArgumentParser(description="Busca híbrida de filmes por descrição")
    p.add_argument("consulta")
    p.add_argument("--ano-min", type=int)
    p.add_argument("--ano-max", type=int)
    p.add_argument("--genero", action="append", default=[], help="pode repetir: --genero comedy --genero drama")
    p.add_argument("--excluir", type=int, action="append", default=[], help="tmdb_id recusado; pode repetir")
    p.add_argument("--agregacao", choices=["soma", "max"], default="max")
    p.add_argument("-k", type=int, default=10)
    a = p.parse_args()

    with conectar() as conn:
        inicio = time.time()
        r = buscar(
            conn,
            a.consulta,
            Filtros(ano_min=a.ano_min, ano_max=a.ano_max, generos=a.genero),
            excluir_tmdb_ids=a.excluir,
            k=a.k,
            agregacao=a.agregacao,
        )
        ms = (time.time() - inicio) * 1000

    print(f'\n🔎 "{a.consulta}"  ({ms:.0f} ms)')
    print("   etapas:", r.etapas)
    print(f"\n   {'#':>2}  {'nota':>6}  {'vet':>3} {'txt':>3}  filme")
    for i, c in enumerate(r.candidatos, start=1):
        pv = c.posicao_vetor or "-"
        pt = c.posicao_texto or "-"
        print(f"   {i:>2}  {c.nota:.4f}  {pv:>3} {pt:>3}  {c.titulo} ({c.ano})  tmdb={c.tmdb_id}")
    if r.candidatos:
        trecho = r.candidatos[0].trecho.split("\n", 1)[-1]
        print(f"\n   trecho do 1º: {trecho[:220]}…")


if __name__ == "__main__":
    main()
