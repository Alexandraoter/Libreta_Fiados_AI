import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


def get_conn():
    """Abre una conexión a PostgreSQL. Cada fila llega como diccionario."""
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)