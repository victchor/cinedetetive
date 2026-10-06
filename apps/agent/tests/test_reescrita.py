"""Testa a validação e o plano B da reescrita SEM chamar o LLM de verdade (rápido e determinístico)."""

import json

import pytest

from cinedetetive.rag import reescrita


def responder_com(*respostas):
    """Substitui a chamada ao Ollama por respostas prontas, uma por tentativa."""
    fila = list(respostas)
    return lambda descricao: fila.pop(0)


def test_resposta_valida(monkeypatch):
    resposta = json.dumps({"consulta_en": "a man relives  the same day", "ano_min": 1990, "ano_max": 1999})
    monkeypatch.setattr(reescrita, "_chamar_llm", responder_com(resposta))
    r = reescrita.reescrever("cara que vive o mesmo dia, anos 90")
    assert r.consulta_en == "a man relives the same day"  # espaço duplo removido
    assert (r.ano_min, r.ano_max) == (1990, 1999)
    assert not r.fallback


def test_anos_invertidos_sao_corrigidos(monkeypatch):
    resposta = json.dumps({"consulta_en": "zombies on a train", "ano_min": 2019, "ano_max": 2010})
    monkeypatch.setattr(reescrita, "_chamar_llm", responder_com(resposta))
    r = reescrita.reescrever("zumbi no trem")
    assert (r.ano_min, r.ano_max) == (2010, 2019)


def test_ano_absurdo_vira_none(monkeypatch):
    resposta = json.dumps({"consulta_en": "a robot in space", "ano_min": 90, "ano_max": None})
    monkeypatch.setattr(reescrita, "_chamar_llm", responder_com(resposta))
    assert reescrita.reescrever("robô no espaço").ano_min is None


def test_tenta_de_novo_quando_vem_invalido(monkeypatch):
    valida = json.dumps({"consulta_en": "spinning top at the end"})
    monkeypatch.setattr(reescrita, "_chamar_llm", responder_com("isto não é json", valida))
    r = reescrita.reescrever("pião no final")
    assert r.consulta_en == "spinning top at the end"
    assert not r.fallback


@pytest.mark.parametrize("ruim", ["não é json", json.dumps({"consulta_en": ""}), json.dumps({})])
def test_plano_b_usa_a_descricao_original(monkeypatch, ruim):
    monkeypatch.setattr(reescrita, "_chamar_llm", responder_com(ruim, ruim))
    r = reescrita.reescrever("filme do pião")
    assert r.fallback
    assert r.consulta_en == "filme do pião"
