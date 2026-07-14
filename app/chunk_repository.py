from uuid import UUID, uuid4

from pgvector import Vector

from app.db import get_connection

from psycopg.rows import dict_row


def replace_document_chunks(
    document_id: UUID,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    if not chunks:
        raise ValueError("At least one chunk is required")

    if len(chunks) != len(embeddings):
        raise ValueError("Each chunk must have an embedding")

    rows = [
        (
            uuid4(),
            document_id,
            chunk_index,
            chunk,
            Vector(embedding),
        )
        for chunk_index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings, strict=True)
        )
    ]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM document_chunks
                WHERE document_id = %s;
                """,
                (document_id,),
            )

            cursor.executemany(
                """
                INSERT INTO document_chunks (
                    id,
                    document_id,
                    chunk_index,
                    content,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s);
                """,
                rows,
            )

            cursor.execute(
                """
                UPDATE documents
                SET
                    chunk_count = %s,
                    status = 'ready',
                    error_message = NULL
                WHERE id = %s;
                """,
                (len(chunks), document_id),
            )
            
def search_similar_chunks(
    query_embedding: list[float],
    limit: int = 3,
) -> list[dict[str, object]]:
    if limit <= 0:
        raise ValueError("Limit must be greater than zero")

    query = """
        SELECT
            document_chunks.document_id,
            documents.filename,
            document_chunks.chunk_index,
            document_chunks.content,
            1 - (document_chunks.embedding <=> %s) AS similarity
        FROM document_chunks
        JOIN documents
            ON documents.id = document_chunks.document_id
        WHERE documents.status = 'ready'
        ORDER BY similarity DESC
        LIMIT %s;
    """

    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                (
                    Vector(query_embedding),
                    limit,
                ),
            )
            chunks = cursor.fetchall()

    return chunks