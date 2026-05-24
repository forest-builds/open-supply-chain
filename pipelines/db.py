from collections.abc import Iterator
from contextlib import contextmanager
import os

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

load_dotenv()


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required. Copy .env.example to .env first.")
    return value


@contextmanager
def db_connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        yield conn
