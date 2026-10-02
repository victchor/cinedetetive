import httpx
import numpy as np

from cinedetetive.config import settings


def embed_consulta(texto: str) -> np.ndarray:
    """Vetor da pergunta, pelo MESMO modelo que gerou os vetores dos trechos (bge-m3).

    Os trechos foram gerados no Colab e a pergunta é gerada aqui pelo Ollama; a
    ingestão (import_embeddings.py) conferiu que os dois dão vetores iguais.
    """
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/embed",
        json={"model": settings.embedding_model, "input": [texto]},
        timeout=60,
    )
    resp.raise_for_status()
    return np.array(resp.json()["embeddings"][0], dtype="float32")
