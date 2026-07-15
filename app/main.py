from hashlib import sha256
from pathlib import Path
from uuid import UUID

import psycopg
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.chunk_repository import (
    replace_document_chunks,
    search_similar_chunks,
)
from app.chunking import split_text
from app.config import settings
from app.db import check_database_connection
from app.document_repository import (
    DocumentLimitExceeded,
    create_document,
    delete_document,
    get_document,
    list_documents,
    mark_document_failed,
)
from app.embeddings import embed_documents, embed_query

from app.schemas import (
    AskRequest,
    AskResponse,
    SearchRequest,
    SourceResponse,
)

from app.generation import generate_answer
from app.rate_limiter import (
    RateLimitExceeded,
    consume_ask_limit,
    consume_upload_limit,
    gemini_slot,
    get_client_key,
)


MAX_FILE_SIZE = 1 * 1024 * 1024
MAX_CHUNKS_PER_DOCUMENT = 300
MAX_DOCUMENTS = 30
BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title=settings.app_name)
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
    )


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    database_connected = check_database_connection()

    if not database_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_connected else "degraded",
        "app_name": settings.app_name,
        "database": "connected" if database_connected else "unavailable",
    }

@app.get("/documents")
def get_documents() -> list[dict[str, object]]:
    return list_documents()

@app.post("/documents", status_code=status.HTTP_201_CREATED)
def upload_document(
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, object]:
    filename = Path((file.filename or "").replace("\\", "/")).name

    if Path(filename).suffix.lower() != ".txt":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .txt files are supported",
        )

    content_bytes = file.file.read(MAX_FILE_SIZE + 1)
    file.file.close()

    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is too large",
        )

    try:
        full_text = content_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file must use UTF-8 encoding",
        ) from error

    if not full_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file is empty",
        )

    chunks = split_text(full_text)

    if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "The document produces more than "
                f"{MAX_CHUNKS_PER_DOCUMENT} chunks"
            ),
        )

    with gemini_slot() as acquired:
        if not acquired:
            raise _gemini_busy_http_exception()

        try:
            document_id = create_document(
                filename=filename,
                file_type="txt",
                full_text=full_text,
                content_sha256=sha256(content_bytes).hexdigest(),
                size_bytes=len(content_bytes),
                max_documents=MAX_DOCUMENTS,
            )
        except psycopg.errors.UniqueViolation as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document has already been uploaded",
            ) from error
        except DocumentLimitExceeded as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The database already contains {MAX_DOCUMENTS} documents",
            ) from error

        try:
            consume_upload_limit(get_client_key(request))
        except RateLimitExceeded as error:
            delete_document(document_id)
            raise _rate_limit_http_exception(error) from error

        try:
            embeddings = embed_documents(chunks)

            replace_document_chunks(
                document_id=document_id,
                chunks=chunks,
                embeddings=embeddings,
            )
        except Exception as error:
            mark_document_failed(
                document_id=document_id,
                error_message=str(error)[:2000],
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document processing failed",
            ) from error

    return {
        "id": str(document_id),
        "filename": filename,
        "status": "ready",
        "chunk_count": len(chunks),
    }

@app.post("/search")
def search_documents(
    request: Request,
    payload: SearchRequest,
) -> list[dict[str, object]]:
    with gemini_slot() as acquired:
        if not acquired:
            raise _gemini_busy_http_exception()

        try:
            consume_ask_limit(get_client_key(request))
        except RateLimitExceeded as error:
            raise _rate_limit_http_exception(error) from error

        query_embedding = embed_query(payload.question)

        return search_similar_chunks(
            query_embedding=query_embedding,
            limit=payload.limit,
        )

@app.post("/ask", response_model=AskResponse)
def ask_question(request: Request, payload: AskRequest) -> AskResponse:
    with gemini_slot() as acquired:
        if not acquired:
            raise _gemini_busy_http_exception()

        try:
            consume_ask_limit(get_client_key(request))
        except RateLimitExceeded as error:
            raise _rate_limit_http_exception(error) from error

        query_embedding = embed_query(payload.question)

        chunks = search_similar_chunks(
            query_embedding=query_embedding,
            limit=3,
        )

        answer = generate_answer(
            question=payload.question,
            chunks=chunks,
        )

    sources: list[SourceResponse] = []
    seen_document_ids: set[UUID] = set()

    for chunk in chunks:
        filename = str(chunk["filename"])
        document_id = UUID(str(chunk["document_id"]))
        citation = f"[{filename}]"

        if citation not in answer:
            continue

        if document_id in seen_document_ids:
            continue

        sources.append(
            SourceResponse(
                document_id=document_id,
                filename=filename,
            )
        )
        seen_document_ids.add(document_id)

    clean_answer = answer

    for source in sources:
        clean_answer = clean_answer.replace(
            f" [{source.filename}]",
            "",
        )

    return AskResponse(
        answer=clean_answer,
        sources=sources,
    )


def _rate_limit_http_exception(error: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=error.message,
        headers={"Retry-After": str(error.retry_after)},
    )


def _gemini_busy_http_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Gemini is busy. Try again shortly",
        headers={"Retry-After": "5"},
    )

@app.get("/documents/{document_id}")
def get_document_by_id(document_id: UUID) -> dict[str, object]:
    document = get_document(document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document

@app.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document_by_id(document_id: UUID) -> Response:
    document_deleted = delete_document(document_id)

    if not document_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
