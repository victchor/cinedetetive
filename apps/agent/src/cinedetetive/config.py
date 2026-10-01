from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py → cinedetetive → src → agent → apps → raiz do projeto
ROOT_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Única porta de entrada das configurações. Lê o .env da raiz do projeto."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    tmdb_read_token: str = ""

    data_dir: Path = ROOT_DIR / "data"


settings = Settings()
