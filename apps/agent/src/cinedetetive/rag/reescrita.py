"""Reescrita da pergunta: descrição em português → consulta em inglês + filtros.

Por quê: as sinopses estão em inglês. A busca por sentido até entende português (bge-m3 é
multilíngue), mas a busca por palavras não ("marmota" nunca casa com "groundhog"). No eval
do passo 6, com as descrições em português, a busca por palavras acertou 0 de 30 casos.

Como: o Llama responde com SAÍDA ESTRUTURADA — o Ollama recebe o JSON Schema do Pydantic e
obriga a resposta a seguir esse formato. Mesmo assim validamos; se vier inválido, tenta de
novo uma vez; se falhar de novo, usa a descrição original (a busca por sentido ainda funciona).
"""

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from cinedetetive.config import settings
from cinedetetive.llm.prompts import REESCRITA_SISTEMA

TENTATIVAS = 2


class SaidaLLM(BaseModel):
    """O formato que o Llama é obrigado a devolver (vira JSON Schema para o Ollama)."""

    consulta_en: str = Field(min_length=3)
    ano_min: int | None = None
    ano_max: int | None = None
    generos: list[str] = Field(default_factory=list)
    pessoas: list[str] = Field(default_factory=list)

    @field_validator("consulta_en")
    @classmethod
    def sem_espacos_sobrando(cls, v: str) -> str:
        return " ".join(v.split())

    @model_validator(mode="after")
    def anos_coerentes(self) -> "SaidaLLM":
        # modelo pequeno às vezes inverte os anos ou inventa um ano absurdo
        for campo in ("ano_min", "ano_max"):
            ano = getattr(self, campo)
            if ano is not None and not 1890 <= ano <= 2030:
                setattr(self, campo, None)
        if self.ano_min and self.ano_max and self.ano_min > self.ano_max:
            self.ano_min, self.ano_max = self.ano_max, self.ano_min
        return self


class ConsultaReescrita(SaidaLLM):
    fallback: bool = False  # True = o LLM falhou e consulta_en é a descrição original


def _chamar_llm(descricao: str) -> str:
    """Uma chamada ao Ollama. Separada para os testes poderem substituí-la."""
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": REESCRITA_SISTEMA},
                {"role": "user", "content": descricao},
            ],
            "format": SaidaLLM.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0},  # mesma pergunta → mesma resposta (bom para evals)
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def reescrever(descricao: str) -> ConsultaReescrita:
    for _ in range(TENTATIVAS):
        try:
            saida = SaidaLLM.model_validate_json(_chamar_llm(descricao))
            return ConsultaReescrita(**saida.model_dump())
        except (ValidationError, httpx.HTTPError, KeyError):
            continue
    return ConsultaReescrita(consulta_en=descricao, fallback=True)
