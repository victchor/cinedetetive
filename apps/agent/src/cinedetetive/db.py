import psycopg
from pgvector.psycopg import register_vector

from cinedetetive.config import settings


def conectar() -> psycopg.Connection:
    """Conexão com o Postgres já sabendo enviar e receber o tipo vector."""
    conn = psycopg.connect(settings.database_url, autocommit=True)
    register_vector(conn)
    return conn
