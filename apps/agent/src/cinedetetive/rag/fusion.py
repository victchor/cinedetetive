"""Reciprocal Rank Fusion (RRF): junta listas ordenadas usando só a POSIÇÃO de cada item.

Por que não somar as notas? A busca vetorial dá similaridade de cosseno (0..1) e a textual dá
ts_rank (outra escala, sem teto). Não dá para comparar uma com a outra. A posição dá:
ser o 1º de uma lista vale o mesmo em qualquer lista.

    nota(item) = soma, em cada lista onde ele aparece, de 1 / (k + posição)

k = 60 é o valor do artigo original (Cormack et al., 2009). Ele suaviza a diferença entre
as primeiras posições: com k = 60, o 1º vale 1/61 e o 10º vale 1/70 — perto, mas ainda maior.
Um item que aparece nas DUAS listas soma as duas parcelas e sobe.
"""

from collections import defaultdict
from collections.abc import Hashable, Sequence

K_PADRAO = 60


def rrf(listas: Sequence[Sequence[Hashable]], k: int = K_PADRAO) -> dict[Hashable, float]:
    """Recebe listas de ids (cada uma já ordenada, melhor primeiro) e devolve id → nota RRF."""
    notas: dict[Hashable, float] = defaultdict(float)
    for lista in listas:
        for posicao, item in enumerate(lista, start=1):
            notas[item] += 1.0 / (k + posicao)
    return dict(notas)
