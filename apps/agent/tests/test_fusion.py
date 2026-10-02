import pytest

from cinedetetive.rag.fusion import rrf


def test_uma_lista_mantem_a_ordem():
    notas = rrf([["a", "b", "c"]])
    assert sorted(notas, key=notas.get, reverse=True) == ["a", "b", "c"]


def test_formula_com_k_60():
    notas = rrf([["a", "b"]])
    assert notas["a"] == pytest.approx(1 / 61)
    assert notas["b"] == pytest.approx(1 / 62)


def test_quem_aparece_nas_duas_listas_sobe():
    # "c" é só o 3º em cada lista, mas aparece nas duas: passa os que estão no topo de uma só
    vetor = ["a", "x", "c"]
    texto = ["b", "y", "c"]
    notas = rrf([vetor, texto])
    assert max(notas, key=notas.get) == "c"


def test_lista_vazia():
    assert rrf([[], []]) == {}
