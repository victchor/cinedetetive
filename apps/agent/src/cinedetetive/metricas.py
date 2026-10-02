"""Métricas de avaliação: o filme certo apareceu? Em que posição?

Todas partem da POSIÇÃO do filme certo na lista devolvida (1 = primeiro; None = não veio).

    Recall@k / Hit@k   fração dos casos com o filme certo entre os k primeiros.
                       (Com UM filme certo por pergunta, Recall@k e Hit@k são a mesma conta;
                       o nome muda pelo uso: Recall@20 mede a busca, Hit@1 mede a resposta final.)
    MRR                média de 1/posição. 1º = 1,0 · 2º = 0,5 · 10º = 0,1 · não veio = 0.
                       Distingue "achou em 1º" de "achou em 18º", que o Recall@20 trata igual.
"""

from collections.abc import Sequence


def posicao(esperado: int, devolvidos: Sequence[int | None]) -> int | None:
    """Posição (começando em 1) do tmdb_id esperado na lista; None se não estiver."""
    for i, tmdb_id in enumerate(devolvidos, start=1):
        if tmdb_id == esperado:
            return i
    return None


def taxa_no_top(posicoes: Sequence[int | None], k: int) -> float:
    """Recall@k / Hit@k: fração dos casos com o filme certo entre os k primeiros."""
    if not posicoes:
        return 0.0
    return sum(1 for p in posicoes if p is not None and p <= k) / len(posicoes)


def mrr(posicoes: Sequence[int | None]) -> float:
    """Mean Reciprocal Rank: média de 1/posição (0 quando o filme não veio)."""
    if not posicoes:
        return 0.0
    return sum(1 / p for p in posicoes if p is not None) / len(posicoes)
