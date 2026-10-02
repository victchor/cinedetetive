import pytest

from cinedetetive.metricas import mrr, posicao, taxa_no_top


def test_posicao_comeca_em_1():
    assert posicao(137, [27205, 137, 603]) == 2


def test_posicao_quando_nao_veio():
    assert posicao(137, [27205, 603]) is None


def test_posicao_ignora_filmes_sem_tmdb_id():
    assert posicao(137, [None, None, 137]) == 3


def test_exemplo_do_guia():
    # 3 casos: filme certo em 1º, em 4º e ausente
    posicoes = [1, 4, None]
    assert taxa_no_top(posicoes, 20) == pytest.approx(2 / 3)
    assert taxa_no_top(posicoes, 1) == pytest.approx(1 / 3)
    assert taxa_no_top(posicoes, 3) == pytest.approx(1 / 3)
    assert mrr(posicoes) == pytest.approx((1 + 0.25 + 0) / 3)


def test_listas_vazias():
    assert taxa_no_top([], 20) == 0.0
    assert mrr([]) == 0.0
