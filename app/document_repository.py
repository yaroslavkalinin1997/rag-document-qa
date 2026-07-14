from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from app.config import settings


def create_document(
    filename: str,
    file_type: str,
    full_text: str,
    content_sha256: str,
    size_bytes: int,
) -> UUID:
    document_id = uuid4()

    query = """
        INSERT INTO documents (
            id,
            filename,
            file_type,
            full_text,
            content_sha256,
            size_bytes,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'processing')
        RETURNING id;
    """

    with psycopg.connect(settings.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    document_id,
                    filename,
                    file_type,
                    full_text,
                    content_sha256,
                    size_bytes,
                ),
            )
            result = cursor.fetchone()

    if result is None:
        raise RuntimeError("PostgreSQL did not return a document ID")

    return result[0]


def list_documents() -> list[dict[str, object]]:
    query = """
        SELECT
            id,
            filename,
            file_type,
            status,
            chunk_count,
            created_at
        FROM documents
        ORDER BY created_at DESC;
    """

    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            documents = cursor.fetchall()

    return documents

def get_document(document_id: UUID) -> dict[str, object] | None:
    query = """
        SELECT
            id,
            filename,
            file_type,
            full_text,
            size_bytes,
            status,
            chunk_count,
            created_at
        FROM documents
        WHERE id = %s;
    """

    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (document_id,))
            document = cursor.fetchone()

    return document

def delete_document(document_id: UUID) -> bool:
    query = """
        DELETE FROM documents
        WHERE id = %s
        RETURNING id;
    """

    with psycopg.connect(settings.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (document_id,))
            deleted_document = cursor.fetchone()

    return deleted_document is not None

def mark_document_failed(
    document_id: UUID,
    error_message: str,
) -> None:
    query = """
        UPDATE documents
        SET
            status = 'failed',
            error_message = %s
        WHERE id = %s;
    """

    with psycopg.connect(settings.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (error_message, document_id),
            )