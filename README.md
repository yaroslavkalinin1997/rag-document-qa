# RAG Document Q&A

A small full-stack Retrieval-Augmented Generation (RAG) application for asking
questions about shared text documents. Users can upload UTF-8 `.txt` files,
inspect their contents, and receive short grounded answers with source links.

**Live application:** https://rag-document-qa-86q5.onrender.com

## Project status

The project is a working MVP built to learn the complete RAG lifecycle:

1. accept and validate a document;
2. split it into overlapping chunks;
3. create vector embeddings with Gemini;
4. store text and vectors in PostgreSQL with pgvector;
5. retrieve the most similar chunks for a question;
6. generate a concise answer using only the retrieved context;
7. return the answer together with its source document.

All documents are shared between visitors. Authentication and user accounts are
intentionally outside the current MVP scope.

## Features

- Upload and index UTF-8 `.txt` documents.
- List, open, and delete uploaded documents.
- Semantic search with cosine similarity.
- Short answers grounded in retrieved document chunks.
- Clickable source documents in the answer.
- Duplicate detection using SHA-256.
- Persistent rate-limit counters in PostgreSQL.
- Site-wide Gemini concurrency control with a PostgreSQL advisory lock.
- Docker setup for local development and deployment.
- Health endpoint that verifies the database connection.

## Architecture

```mermaid
flowchart LR
    U[Browser] -->|Upload TXT| API[FastAPI]
    API --> S[LangChain text splitter]
    S --> E[Gemini embeddings]
    E --> DB[(PostgreSQL + pgvector)]

    U -->|Ask question| API
    API --> QE[Gemini query embedding]
    QE --> DB
    DB -->|Top 3 chunks| API
    API --> LLM[Gemini chat model]
    LLM -->|Answer + source| U
```

The original document text and its metadata are stored in `documents`. Individual
chunks and their 768-dimensional embeddings are stored in `document_chunks`.
Usage counters are stored in `rate_limit_counters` so limits survive application
restarts and redeployments.

## Technology stack

- **Python 3.13**
- **FastAPI** and **Uvicorn**
- **LangChain** text splitters and Google Gemini integration
- **Gemini Embedding** for document and query vectors
- **Gemini Flash** for answer generation
- **PostgreSQL 17** with **pgvector**
- **Psycopg 3** and raw SQL
- **Jinja2**, vanilla JavaScript, and CSS
- **uv** for Python dependency management
- **Docker Compose** for the local stack
- **GitHub** and **Render** for deployment

## RAG configuration

| Setting | Value |
| --- | ---: |
| Chunk size | 1,200 characters |
| Chunk overlap | 200 characters |
| Embedding model | `gemini-embedding-001` |
| Embedding dimensions | 768 |
| Similarity metric | Cosine similarity |
| Retrieved chunks | 3 |
| Answer model | `gemini-3.5-flash` |
| Answer length | Up to 500 tokens |
| Question length | Up to 1,000 characters |

## Usage limits

Limits use fixed UTC calendar windows. A rejected request returns HTTP `429` and
a `Retry-After` header. IP addresses are converted to SHA-256 identifiers before
being stored in the database.

### Questions and semantic search

| Limit | Value |
| --- | ---: |
| Questions per UTC day for the entire site | 30 |
| Questions per UTC day from one IP | 15 |
| Questions per minute from one IP | 5 |
| Concurrent Gemini operations for the site | 1 |

The technical `/search` endpoint uses the same question quota because it also
calls the Gemini embedding API.

### Document uploads

| Limit | Value |
| --- | ---: |
| Uploads per UTC day for the entire site | 10 |
| Uploads per UTC day from one IP | 3 |
| Maximum TXT file size | 1 MiB |
| Maximum chunks per document | 300 |
| Maximum documents in the database | 30 |

Invalid files, duplicates, documents over the database capacity, and requests
rejected while Gemini is busy are not counted as successful uploads.

## Project structure

```text
app/
  main.py                 FastAPI routes and document processing workflow
  config.py               Environment-based application settings
  db.py                   PostgreSQL connection helpers
  document_repository.py  Document SQL operations
  chunk_repository.py     Chunk storage and vector similarity search
  chunking.py              LangChain text splitting configuration
  embeddings.py            Gemini embedding client
  generation.py            Grounded answer prompt and Gemini chat client
  rate_limiter.py          Persistent quotas and Gemini concurrency lock
  schemas.py               Request and response models
sql/
  schema.sql               Idempotent database schema
static/                    Browser JavaScript and CSS
templates/                 Jinja2 HTML template
compose.yaml               Local app and pgvector services
Dockerfile                 Production application image
```

## Prerequisites

- Git
- Docker Desktop
- [uv](https://docs.astral.sh/uv/)
- A Gemini API key

## Environment configuration

Create a local `.env` file from the committed example:

```powershell
Copy-Item .env.example .env
```

Set your own values in `.env`:

```dotenv
APP_NAME=RAG Document Q&A

POSTGRES_DB=rag_db
POSTGRES_USER=rag_user
POSTGRES_PASSWORD=choose-a-local-password
DATABASE_URL=postgresql://rag_user:choose-a-local-password@127.0.0.1:5432/rag_db
GEMINI_API_KEY=your-gemini-api-key
```

The real `.env` file is ignored by Git. Do not commit API keys or database
passwords.

## Run the complete stack with Docker

Start PostgreSQL and the application:

```powershell
docker compose up --build -d
```

Apply the database schema after the database becomes healthy:

```powershell
Get-Content sql/schema.sql | docker compose exec -T db psql -U rag_user -d rag_db -v ON_ERROR_STOP=1
```

Open:

- Application: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

Stop the stack without deleting PostgreSQL data:

```powershell
docker compose down
```

## Run FastAPI locally with uv

Start only PostgreSQL:

```powershell
docker compose up -d db
```

Install locked dependencies and run the development server:

```powershell
uv sync --locked
uv run uvicorn app.main:app --reload
```

The local `DATABASE_URL` in `.env` connects FastAPI to PostgreSQL through
`127.0.0.1:5432`. Docker Compose overrides this URL for the containerized app and
uses the `db` service hostname.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Web interface |
| `GET` | `/health` | Application and database health |
| `GET` | `/documents` | List document metadata |
| `POST` | `/documents` | Upload and index a TXT document |
| `GET` | `/documents/{id}` | Read a stored document |
| `DELETE` | `/documents/{id}` | Delete a document and its chunks |
| `POST` | `/search` | Inspect vector retrieval results |
| `POST` | `/ask` | Generate a grounded answer with sources |

Example question request:

```powershell
$body = @{ question = "Where is the generator key stored?" } | ConvertTo-Json
Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8000/ask `
    -ContentType "application/json" `
    -Body $body
```

## Database schema

`sql/schema.sql` is idempotent and creates:

- the pgvector extension;
- `documents` for source text and processing state;
- `document_chunks` for chunks and `VECTOR(768)` embeddings;
- `rate_limit_counters` for atomic fixed-window quotas.

Deleting a document also deletes its chunks through `ON DELETE CASCADE`.

## Deployment on Render

The application is deployed as a Docker Web Service and uses a Render PostgreSQL
database in the same region.

Required Web Service environment variables:

```text
APP_NAME
DATABASE_URL       Render PostgreSQL Internal Database URL
GEMINI_API_KEY
```

The health check path is `/health`. The Docker command binds Uvicorn to
`0.0.0.0` and uses Render's `PORT` environment variable.

Before deploying code that depends on a new table, apply `sql/schema.sql` to the
Render PostgreSQL database. Pushes to the linked `main` branch trigger automatic
deployment.

## Current limitations

- Documents are global and shared by every visitor.
- There is no authentication or administrative role.
- Any visitor can currently delete a document.
- Only English UTF-8 `.txt` documents are supported.
- Retrieval always sends the top three chunks and has no calibrated similarity
  threshold yet.
- Citations are generated as filenames rather than structured chunk references.
- Rate limiting is intentionally small-scale and PostgreSQL-backed; a dedicated
  rate-limit service may be preferable for a high-traffic application.

## Possible next steps

- Build a small RAG evaluation dataset and measure retrieval quality.
- Calibrate a minimum similarity threshold.
- Compare chunk sizes and embedding models.
- Add hybrid vector and PostgreSQL full-text search.
- Return structured citations with chunk identifiers.
- Protect upload and delete operations with an administrator secret.
- Add DOCX or PDF ingestion.
