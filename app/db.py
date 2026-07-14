import psycopg
from pgvector.psycopg import register_vector

from app.config import settings


def get_connection() -> psycopg.Connection:
    connection = psycopg.connect(settings.database_url)
    register_vector(connection)
    return connection


def check_database_connection() -> bool:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                result = cursor.fetchone()

        return result == (1,)
    except psycopg.OperationalError:
        return False